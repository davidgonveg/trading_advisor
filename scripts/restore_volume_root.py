
import sys
import os
import logging
import pandas as pd
import yfinance as yf
from datetime import datetime

# Ensure root is in path
sys.path.append(os.getcwd())

from data.storage.database import Database
from data.interfaces import Candle
from analysis.indicators import TechnicalIndicators

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("volume_restore")

def restore_volume():
    db = Database()
    tech_ind = TechnicalIndicators()
    
    symbols = ["SPY", "QQQ", "IWM", "DIA", "GLD", "TLT"]
    
    # 1. Fetch 2 Years of 1H data (Max for YFinance)
    logger.info("Starting Full Volume Restoration (Last 730 Days)...")
    
    for symbol in symbols:
        try:
            logger.info(f"Downloading 2y 1h data for {symbol}...")
            # period="730d" is max for 1h
            ticker = yf.Ticker(symbol)
            df = ticker.history(period="730d", interval="1h")
            
            if df.empty:
                logger.warning(f"No data found for {symbol}")
                continue
                
            logger.info(f"Downloaded {len(df)} candles for {symbol}. Range: {df.index.min()} -> {df.index.max()}")
            
            # 2. Convert to Candles
            candles = []
            is_filled = []
            
            for idx, row in df.iterrows():
                # YFinance index is TZ-aware usually
                ts = idx.to_pydatetime()
                c = Candle(
                    timestamp=ts,
                    open=row['Open'],
                    high=row['High'],
                    low=row['Low'],
                    close=row['Close'],
                    volume=row['Volume']
                )
                candles.append(c)
                is_filled.append(True) # Real data
                
            # 3. Save Market Data (Overwrite existing zeroes)
            db.save_bulk_candles(symbol, "1h", candles, is_filled)
            
            # 4. Recalculate Indicators
            logger.info(f"Recalculating Indicators for {symbol}...")
            
            # Load fresh data from DB to ensure consistency
            df_db = db.load_market_data(symbol, "1h")
            
            # Calculate
            df_ind = tech_ind.calculate_all(df_db)
            
            # Save Indicators
            db.save_indicators(symbol, "1h", df_ind)
            logger.info(f"✅ Restoration Complete for {symbol}")
            
        except Exception as e:
            logger.error(f"❌ Failed to restore {symbol}: {e}")

    logger.info("🎉 All symbols processed.")

if __name__ == "__main__":
    restore_volume()
