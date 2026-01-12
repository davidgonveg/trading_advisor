import logging
import sys
import pandas as pd
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from config.settings import SYMBOLS
from data.storage.database import Database
from analysis.indicators import TechnicalIndicators

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("scripts.calculate_history")

def run_calculation():
    logger.info("Starting historical indicator calculation...")
    
    db = Database()
    ti = TechnicalIndicators()
    
    for symbol in SYMBOLS:
        try:
            logger.info(f"Processing indicators for {symbol}...")
            
            # 1. Load 1H Data
            query_1h = f'''
                SELECT timestamp, open, high, low, close, volume 
                FROM market_data 
                WHERE symbol = '{symbol}' AND timeframe = '1h'
                ORDER BY timestamp ASC
            '''
            df_1h = pd.read_sql_query(query_1h, db.get_connection(), index_col='timestamp', parse_dates=['timestamp'])
            
            # 2. Load 1D Data (For SMA50)
            query_1d = f'''
                SELECT timestamp, close 
                FROM market_data 
                WHERE symbol = '{symbol}' AND timeframe = '1d'
                ORDER BY timestamp ASC
            '''
            df_1d = pd.read_sql_query(query_1d, db.get_connection(), index_col='timestamp', parse_dates=['timestamp'])
            
            if df_1h.empty:
                logger.warning(f"No 1H data found for {symbol}")
                continue
                
            # Rename columns
            df_1h.columns = [c.capitalize() for c in df_1h.columns]
            
            # 3. Calculate Daily SMA50
            sma50_daily = pd.Series(dtype=float)
            if not df_1d.empty:
                df_1d.columns = [c.capitalize() for c in df_1d.columns]
                # Calculate SMA50 on Daily
                # We can use the TechnicalIndicators class if we want, or simple rolling
                sma50_daily = df_1d['Close'].rolling(window=50).mean()
                
            # 4. Merge Daily SMA into Hourly Data
            # We forward fill the daily SMA value to all hourly candles of that day (or next day?)
            # Strategy: "Price > SMA(50) Daily".
            # Real-time: We compare current price vs yesterday's SMA50 (or current live SMA50).
            # Backtesting: We reindex daily to hourly.
            
            # Resample daily SMA to hourly, ffilling forward
            if not sma50_daily.empty:
                # We reindex to match hourly index, ffilling
                sma50_resampled = sma50_daily.reindex(df_1h.index, method='ffill')
                df_1h['SMA_50'] = sma50_resampled
            else:
                df_1h['SMA_50'] = 0.0
            
            # 5. Calculate other 1H Indicators
            # Note: calculate_all computes local SMA50 (hourly). We want to preserve the Daily one we just added.
            # We should modify calculate_all to NOT overwrite SMA_50 if it exists, or rename it.
            # Strategy calls it "SMA(50) Daily". Let's verify indicators module behavior.
            # indicators.py calculates 'SMA_50'. It will overwrite.
            # Strategy needs 'SMA_50' to be the Daily one.
            # We will calculate others first, then overwrite/inject the daily one?
            
            enriched_df = ti.calculate_all(df_1h)
            
            # Overwrite SMA_50 with the Daily version if we have it
            if not sma50_daily.empty:
                enriched_df['SMA_50'] = sma50_resampled
            
            # 6. Save to DB
            db.save_indicators(symbol, "1h", enriched_df)
            
            logger.info(f"Completed {symbol} (1H data: {len(df_1h)}, 1D data: {len(df_1d)}, SMA50 available: {not sma50_daily.empty})")
            
        except Exception as e:
            logger.error(f"Error calculating {symbol}: {e}")

if __name__ == "__main__":
    run_calculation()
