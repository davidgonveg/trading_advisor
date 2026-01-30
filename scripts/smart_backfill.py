import logging
import sys
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
import time

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from config.settings import SYMBOLS, DATA_CONFIG
from data.providers.factory import DataProviderFactory
from data.storage.database import Database
from data.interfaces import Candle

# Setup simple logger
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("smart_backfill")

def smart_backfill_symbol(symbol: str, days_back: int = 730):
    factory = DataProviderFactory() # Now includes Polygon
    db = Database()
    
    timeframes = ["1h"] # Focus on 1h which is critical for strategy
    
    for tf in timeframes:
        logger.info(f"=== Processing {symbol} {tf} ===")
        
        # 1. Identify Bad Data in DB (Optional, but good for metrics)
        try:
            current_data = db.load_market_data(symbol, tf)
            initial_zeros = 0
            if not current_data.empty and 'Volume' in current_data.columns:
                initial_zeros = (current_data['Volume'] <= 0).sum()
                logger.info(f"Current DB Status: {len(current_data)} rows, {initial_zeros} with ZERO volume.")
        except Exception as e:
            logger.warning(f"Could not load current data: {e}")
            current_data = pd.DataFrame()

        # 2. Iterate ALL Providers
        # We bypass factory.get_data() to force checking everyone
        best_dataset = None
        best_score = -1
        
        for provider in factory.providers:
            try:
                logger.info(f"Fetching from {provider.name}...")
                df = provider.fetch_data(symbol, timeframe=tf, days_back=days_back)
                
                if df is None or df.empty:
                    logger.warning(f"  -> No data from {provider.name}")
                    continue
                
                # Evaluation Metric: Density (Rows) + Integrity (Non-Zero Volume)
                rows = len(df)
                non_zeros = (df['Volume'] > 0).sum()
                score = non_zeros # Simple score: more valid volume bars is better
                
                logger.info(f"  -> {provider.name}: {rows} rows, {non_zeros} valid volume bars.")
                
                if best_dataset is None:
                    best_dataset = df
                    best_score = score
                    logger.info("     (New Best)")
                else:
                    # Merge Logic:
                    # If we have a dataset, we want to IMPROVE it.
                    # We can join and coalesce.
                    
                    # Align indexes
                    combined = best_dataset.join(df, rsuffix='_new', how='outer')
                    
                    # Logic: If existing volume is 0/NaN and new volume is >0, take new.
                    # Or simpler: Take new row if Volume > 0
                    
                    # For simplicity in this script, let's just REPLACE if the new provider has dramatically better coverage overall
                    # OR, do a row-by-row patch? Row-by-row is expensive but correct "Cure".
                    
                    # Let's do a smart patch
                    # 1. Update missing rows
                    # 2. Update rows where Volume used to be 0 but now is > 0
                    
                    updates = 0
                    for ts, row in df.iterrows():
                        if ts not in best_dataset.index:
                            # New row
                            best_dataset.loc[ts] = row
                            updates += 1
                        else:
                            # Existing row. Check volume.
                            current_vol = best_dataset.loc[ts, 'Volume']
                            new_vol = row['Volume']
                            
                            if (pd.isna(current_vol) or current_vol <= 0) and (new_vol > 0):
                                best_dataset.loc[ts] = row
                                updates += 1
                                
                    logger.info(f"     Merged {updates} improved bars from {provider.name}")

            except Exception as e:
                logger.error(f"  -> Error with {provider.name}: {e}")
                
        # 3. Save "Cured" Dataset
        if best_dataset is not None and not best_dataset.empty:
            logger.info(f"Saving cured dataset for {symbol}: {len(best_dataset)} rows.")
            
            candles = []
            for index, row in best_dataset.iterrows():
                candles.append(Candle(
                    timestamp=index.to_pydatetime(),
                    open=row['Open'],
                    high=row['High'],
                    low=row['Low'],
                    close=row['Close'],
                    volume=row['Volume']
                ))
            
            # Bulk Save
            chunk_size = 5000
            for i in range(0, len(candles), chunk_size):
                chunk = candles[i:i+chunk_size]
                db.save_bulk_candles(symbol, tf, chunk)
                
            logger.info("Save Complete.")
            
            # Verify Improvement
            final_zeros = (best_dataset['Volume'] <= 0).sum()
            logger.info(f"Final Zero-Volume Count: {final_zeros} (Was: {initial_zeros})")
        else:
            logger.warning("No data retrieved from any provider.")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Single symbol mode
        s = sys.argv[1].upper()
        smart_backfill_symbol(s)
    else:
        # All symbols
        for s in SYMBOLS:
            smart_backfill_symbol(s)
