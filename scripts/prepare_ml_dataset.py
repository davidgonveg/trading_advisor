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

def prepare_dataset(audit_dir="backtesting/logs", output_file="data/ml/training_data.csv", lookback_bars=5):
    """
    Parses audit logs and trades to create a training dataset.
    Features: Indicators at signal time + indicators from last N bars.
    Label: Success (Profit > 0) or Failure (0).
    """
    all_rows = []
    
    # 1. Find all audit files
    audit_files = glob(os.path.join(audit_dir, "audit_*.json"))
    
    if not audit_files:
        logger.warning(f"No audit files found in {audit_dir}")
        return

    logger.info(f"Processing {len(audit_files)} audit files with lookback={lookback_bars}...")

    # Using tqdm for progress tracking
    for file_path in tqdm(audit_files, desc="Parsing Audit Logs", unit="file"):
        try:
            with open(file_path, 'r') as f:
                try:
                    audit_data = json.load(f)
                except json.JSONDecodeError:
                    continue

            metadata = audit_data.get('metadata', {})
            symbol = metadata.get('symbol', 'unknown')
            strategy = metadata.get('strategy', 'unknown')
            
            trade_list = audit_data.get('trades', [])
            bars_list = audit_data.get('bars', [])
            
            # Map timestamp to index and indicators
            bars_by_ts = {}
            for idx, bar in enumerate(bars_list):
                bars_by_ts[bar['timestamp']] = (idx, bar.get('indicators', {}))
            
            processed_entries = set()
            for i, trade in enumerate(trade_list):
                tag = trade.get('tag', '') or ''
                if not tag or any(x in tag for x in ["EXIT", "SL", "TP"]):
                    continue
                
                entry_id = trade.get('id')
                if entry_id in processed_entries:
                    continue
                
                # Find matching exit for P&L
                exit_trade = None
                for j in range(i + 1, len(trade_list)):
                    if trade_list[j].get('symbol') == trade.get('symbol'):
                        exit_tag = trade_list[j].get('tag', '') or ''
                        if any(x in exit_tag for x in ["EXIT", "SL", "TP"]):
                            exit_trade = trade_list[j]
                            break
                
                if exit_trade:
                    entry_ts = trade['timestamp']
                    if entry_ts not in bars_by_ts:
                        continue
                        
                    idx, current_indicators = bars_by_ts[entry_ts]
                    
                    # Prepare row with basic info
                    entry_price = trade['price']
                    exit_price = exit_trade['price']
                    side = trade['side']
                    pnl = (exit_price - entry_price) / entry_price if "BUY" in str(side) else (entry_price - exit_price) / entry_price
                    
                    row = {
                        "symbol": symbol,
                        "strategy": strategy,
                        "timestamp": entry_ts,
                        "side": str(side),
                        "pnl": pnl,
                        "label": 1 if pnl > 0 else 0
                    }
                    
                    # Add current indicators
                    row.update(current_indicators)
                    
                    # Add historical indicators (L1, L2, ...)
                    for lb in range(1, lookback_bars + 1):
                        hist_idx = idx - lb
                        if hist_idx >= 0:
                            hist_indicators = bars_list[hist_idx].get('indicators', {})
                            for key, val in hist_indicators.items():
                                row[f"{key}_L{lb}"] = val
                        else:
                            # Fill with zeros or NaNs if not enough history
                            # We'll use 0 for now as it's common in RF
                            # but ideally we should only take signals with full history
                            pass
                    
                    all_rows.append(row)
                    processed_entries.add(entry_id)

        except Exception as e:
            logger.debug(f"Error processing {file_path}: {e}")

    if all_rows:
        df = pd.DataFrame(all_rows)
        # Drop rows with too many missing historical features if needed
        # Or fill them
        df = df.fillna(0)
        
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        df.to_csv(output_file, index=False)
        logger.info(f"Dataset saved to {output_file} with {len(df)} samples and context.")
        print(f"Features in one row sample: {list(df.columns[-10:])}...")
    else:
        logger.warning("No samples collected.")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--lookback", type=int, default=5, help="Number of historical bars to include")
    args = parser.parse_args()
    prepare_dataset(lookback_bars=args.lookback)
