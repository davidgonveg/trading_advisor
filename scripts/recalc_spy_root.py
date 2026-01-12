
import logging
import sys
import pandas as pd
import os
from pathlib import Path

# Root execution
sys.path.append(os.getcwd())

from data.storage.database import Database
from analysis.indicators import TechnicalIndicators

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("recalc_spy")

def run():
    symbol = "SPY"
    
    db = Database()
    ti = TechnicalIndicators()
    
    logger.info(f"Loading 1H data for {symbol}...")
    # Load 1H
    query_1h = f"SELECT * FROM market_data WHERE symbol='{symbol}' AND timeframe='1h' ORDER BY timestamp ASC"
    df_1h = pd.read_sql_query(query_1h, db.get_connection(), index_col='timestamp', parse_dates=['timestamp'])
    
    # Load 1D for SMA50
    query_1d = f"SELECT * FROM market_data WHERE symbol='{symbol}' AND timeframe='1d' ORDER BY timestamp ASC"
    df_1d = pd.read_sql_query(query_1d, db.get_connection(), index_col='timestamp', parse_dates=['timestamp'])
    
    if df_1h.empty:
        logger.error("No 1H data.")
        return

    # Capitalize
    df_1h.columns = [c.capitalize() for c in df_1h.columns]
    if not df_1d.empty:
        df_1d.columns = [c.capitalize() for c in df_1d.columns]
        
    # Calculate Indicators
    logger.info("Calculating Indicators...")
    
    # Need daily SMA50 mapped to hourly
    # Calculate daily SMA50 first
    if not df_1d.empty:
        sma50_d = df_1d['Close'].rolling(window=50).mean()
        # Resample to hourly to merge
        # Be careful with forward fill to avoid lookahead.
        # Shift 1 day? The signal usually uses "Yesterday's Close > SMA50" or "Current Close > SMA50"?
        # Usually we want the SMA50 of the *current daily candle* (which is forming) or the *previous*?
        # Standard: SMA50 of daily. If we are at 10:00 AM, the daily close is not final. 
        # We should probably use the PREVIOUS day's SMA50 or the current live calculation.
        # Simpler: ffill the daily values.
        
        sma50_reindexed = sma50_d.reindex(df_1h.index, method='ffill')
        df_1h['SMA_50'] = sma50_reindexed
    
    # Calculate other indicators on 1H
    df_calculated = ti.calculate_all(df_1h)
    
    # Save
    logger.info("Saving indicators...")
    db.save_indicators(symbol, "1h", df_calculated)
    logger.info("Done.")

if __name__ == "__main__":
    run()
