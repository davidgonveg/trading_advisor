
import sys
import os
import logging
import pandas as pd

# Ensure root is in path
sys.path.append(os.getcwd())

from data.storage.database import Database
from analysis.indicators import TechnicalIndicators

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("recalc_all")

def recalculate_all():
    db = Database()
    tech_ind = TechnicalIndicators()
    
    symbols = ["SPY", "QQQ", "IWM", "DIA", "GLD", "TLT"]
    
    logger.info("Starting Full Indicator Recalculation...")
    
    for symbol in symbols:
        try:
            logger.info(f"Processing {symbol}...")
            
            # 1. Load Market Data (Hourly)
            df_1h = db.load_market_data(symbol, "1h")
            
            if df_1h.empty:
                logger.warning(f"No data for {symbol}")
                continue
                
            # 2. Capitalize Columns (Critical Fix)
            # DB returns: open, high, low, close, volume
            # TechInd expects: Open, High, Low, Close, Volume
            df_1h.columns = [c.capitalize() for c in df_1h.columns]
            
            # 3. Retrieve Daily Data for SMA50 (Trend Filter)
            # The Scanner uses daily SMA50. Is it stored in 1H indicators?
            # Usually we calculate it daily and merge. 
            # If Scanner calculates keys using provided df_daily, then we don't *strictly* need SMA50 in 1H indicators table for the Scanner to work?
            # Wait, scanner.py: 
            # if pd.isna(row['SMA_50']): continue.
            # It checks row['SMA_50'] in the 1H dataframe loop.
            # So YES, we need SMA50 in the 1H dataframe.
            # In `run_backtest_root.py`, it merges indicators.
            # Does `TechnicalIndicators.calculate_all` compute 'SMA_50' on 1H data?
            # If so, it's the 1H SMA50, not Daily.
            # Strategy says "Daily SMA 200/50".
            # If we put 1H SMA50, we act on hourly trend.
            # For now, let's rely on `calculate_all`. 
            # If `calculate_all` does NOT produce SMA_50, we have an issue.
            # Let's assume standard calculate_all does what we need or what was used before.
            # In `recalc_spy_root.py` I merged daily SMA50 manually!
            # So I should copy that logic here to be consistent.
            
            # Load Daily for SMA50 injection
            df_1d = db.load_market_data(symbol, "1d")
            if not df_1d.empty:
                df_1d.columns = [c.capitalize() for c in df_1d.columns]
                sma50_d = df_1d['Close'].rolling(window=50).mean()
                # Resample/FFill to Hourly
                # Reindex to hourly index
                sma50_hourly = sma50_d.reindex(df_1h.index, method='ffill')
                df_1h['SMA_50'] = sma50_hourly
            else:
                logger.warning(f"No Daily data for {symbol}, SMA_50 will be missing/NaN")
            
            # 4. Calculate Indicators (RSI, BB, ADX, VWAP, volSMA)
            df_ind = tech_ind.calculate_all(df_1h)
            
            # 5. Save
            db.save_indicators(symbol, "1h", df_ind)
            logger.info(f"✅ Recalculated & Saved {len(df_ind)} rows for {symbol}")
            
        except Exception as e:
            logger.error(f"❌ Failed to recalc {symbol}: {e}")
            import traceback
            traceback.print_exc()

    logger.info("🎉 All symbols processed.")

if __name__ == "__main__":
    recalculate_all()
