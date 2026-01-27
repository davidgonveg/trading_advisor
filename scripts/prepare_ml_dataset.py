import json
import os
import pandas as pd
from glob import glob
from datetime import datetime
import logging

try:
    from tqdm import tqdm
except ImportError:
    def tqdm(iterable, **kwargs):
        return iterable

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def prepare_dataset(audit_dir="backtesting/logs", output_file="data/ml/training_data.csv"):
    """
    Parses audit logs and trades to create a training dataset.
    Features: Indicators at signal time.
    Label: Success (Profit > 0) or Failure.
    """
    all_rows = []
    
    # 1. Find all audit files
    audit_files = glob(os.path.join(audit_dir, "audit_*.json"))
    
    if not audit_files:
        logger.warning(f"No audit files found in {audit_dir}")
        return

    logger.info(f"Processing {len(audit_files)} audit files...")

    # Using tqdm for progress tracking
    for file_path in tqdm(audit_files, desc="Parsing Audit Logs", unit="file"):
        try:
            with open(file_path, 'r') as f:
                # Optimized: We might want to check file size before reading huge corrupted files
                # but for now, we just catch the exception
                try:
                    audit_data = json.load(f)
                except json.JSONDecodeError as jde:
                    # Specific handling for truncated files
                    logger.debug(f"Skipping corrupted/incomplete JSON: {os.path.basename(file_path)} ({jde})")
                    continue

            metadata = audit_data.get('metadata', {})
            symbol = metadata.get('symbol', 'unknown')
            strategy = metadata.get('strategy', 'unknown')
            
            trade_list = audit_data.get('trades', [])
            bars_dict = {b['timestamp']: b for b in audit_data.get('bars', [])}
            
            processed_entries = set()
            for i, trade in enumerate(trade_list):
                tag = trade.get('tag', '') or ''
                # Handle cases where tag might be None
                if not tag or "EXIT" in tag or "SL" in tag or "TP" in tag:
                    continue
                
                entry_id = trade.get('id')
                if entry_id in processed_entries:
                    continue
                
                # This is an entry. Find the corresponding exit.
                exit_trade = None
                for j in range(i + 1, len(trade_list)):
                    if trade_list[j].get('symbol') == trade.get('symbol'):
                        exit_tag = trade_list[j].get('tag', '') or ''
                        if "EXIT" in exit_tag or "SL" in exit_tag or "TP" in exit_tag:
                            exit_trade = trade_list[j]
                            break
                
                if exit_trade:
                    # Calculate P&L
                    entry_price = trade['price']
                    exit_price = exit_trade['price']
                    side = trade['side']
                    
                    if side == "BUY" or "BUY" in str(side):
                        pnl = (exit_price - entry_price) / entry_price
                    else:
                        pnl = (entry_price - exit_price) / entry_price
                    
                    # Get indicators at entry
                    entry_ts = trade['timestamp']
                    entry_bar = bars_dict.get(entry_ts)
                    
                    if entry_bar and entry_bar.get('indicators'):
                        row = {
                            "symbol": symbol,
                            "strategy": strategy,
                            "timestamp": entry_ts,
                            "side": str(side),
                            "pnl": pnl,
                            "label": 1 if pnl > 0 else 0
                        }
                        row.update(entry_bar['indicators'])
                        all_rows.append(row)
                        processed_entries.add(entry_id)

        except Exception as e:
            # General logger for unexpected errors, but don't stop the loop
            logger.debug(f"Error processing {file_path}: {e}")

    if all_rows:
        df = pd.DataFrame(all_rows)
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        df.to_csv(output_file, index=False)
        logger.info(f"Dataset saved to {output_file} with {len(df)} samples.")
        print(f"\nDataset Summary:")
        print(df['label'].value_counts(normalize=True))
        print(f"Symbols found: {df['symbol'].unique()}")
    else:
        logger.warning("No samples collected. Ensure backtests have run with audit logs enabled and produced trades.")

if __name__ == "__main__":
    prepare_dataset()
