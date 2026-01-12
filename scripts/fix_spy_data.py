
import logging
import sys
from pathlib import Path
import pandas as pd
import os

# Root execution
sys.path.append(os.getcwd())

from data.providers.factory import DataProviderFactory
from data.storage.database import Database
from data.interfaces import Candle

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fix_spy")

def run():
    symbol = "SPY"
    days_back = 60
    
    factory = DataProviderFactory()
    db = Database()
    
    # 1. Fetch 1H
    logger.info(f"Fetching 1H for {symbol}...")
    df_1h = factory.get_data(symbol, "1h", days_back=days_back)
    
    if df_1h is not None and not df_1h.empty:
        logger.info(f"Fetched {len(df_1h)} rows.")
        # Check volume
        logger.info(f"Volume > 0: {len(df_1h[df_1h['Volume'] > 0])}")
        
        # Save
        candles = []
        for idx, row in df_1h.iterrows():
            candles.append(Candle(
                timestamp=idx.to_pydatetime(),
                open=row['Open'],
                high=row['High'],
                low=row['Low'],
                close=row['Close'],
                volume=row['Volume']
            ))
        db.save_bulk_candles(symbol, "1h", candles)
        logger.info("Saved 1H candles.")
        
    # 2. Fetch 1D
    logger.info(f"Fetching 1D for {symbol}...")
    df_1d = factory.get_data(symbol, "1d", days_back=days_back*2)
    if df_1d is not None and not df_1d.empty:
        # Save
        candles_d = []
        for idx, row in df_1d.iterrows():
            candles_d.append(Candle(
                timestamp=idx.to_pydatetime(),
                open=row['Open'],
                high=row['High'],
                low=row['Low'],
                close=row['Close'],
                volume=row['Volume']
            ))
        db.save_bulk_candles(symbol, "1d", candles_d)
        logger.info("Saved 1D candles.")

    logger.info("Fix Complete.")

if __name__ == "__main__":
    run()
