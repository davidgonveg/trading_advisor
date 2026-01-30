import logging
import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from config.settings import SYMBOLS, DATA_CONFIG
from data.providers.factory import DataProviderFactory
from data.storage.database import Database
from data.quality.detector import GapDetector
from data.quality.repair import GapRepair
from data.interfaces import Candle

# Setup simple logger
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("scripts.backfill")

def run_backfill():
    days_back = DATA_CONFIG.get("BACKFILL_DAYS", 730)
    logger.info(f"Starting backfill for {len(SYMBOLS)} symbols. Target: {days_back} days history.")
    
    factory = DataProviderFactory()
    db = Database()
    detector = GapDetector()
    repair = GapRepair()
    
    for symbol in SYMBOLS:
        try:
            logger.info(f"Processing {symbol}...")
            
            # 1. Fetch Max History for both timeframes
            # Strategy requires 1H for signals and 1D for Trend Filter (SMA50)
            timeframes = ["1h", "1d"]
            
            for tf in timeframes:
                logger.info(f"Fetching {tf} data for {symbol}...")
                days = days_back if tf == "1h" else days_back * 2 # get more daily context
                
                # Dynamic interval for gap detection
                # 1h -> 60 min, 1d -> 1440 min (24 * 60)
                expected_interval = 60 if tf == "1h" else 1440
                
                df = factory.get_data(symbol, timeframe=tf, days_back=days)
                
                if df is None or df.empty:
                    logger.warning(f"Failed to fetch {tf} data for {symbol}")
                    continue
                
                logger.info(f"fetched {len(df)} rows. Range: {df.index.min()} -> {df.index.max()}")
                
                # 2. Detect & Repair Gaps
                gaps = detector.detect_gaps(df, symbol, expected_interval_minutes=expected_interval)
                if gaps:
                    logger.info(f"Detected {len(gaps)} gaps for {tf} (interval={expected_interval}m). Repairing...")
                    df = repair.fill_gaps(df, gaps, freq=tf)
                
                # 3. Store
                candles = []
                for index, row in df.iterrows():
                    candles.append(Candle(
                        timestamp=index.to_pydatetime(),
                        open=row['Open'],
                        high=row['High'],
                        low=row['Low'],
                        close=row['Close'],
                        volume=row['Volume']
                    ))
                
                # Bulk save
                chunk_size = 5000
                for i in range(0, len(candles), chunk_size):
                    chunk = candles[i:i + chunk_size]
                    db.save_bulk_candles(symbol, tf, chunk)
                    logger.info(f"Saved chunk {i}-{i+len(chunk)}")
                
            logger.info(f"Completed {symbol}")
            
        except Exception as e:
            logger.error(f"Error backfilling {symbol}: {e}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", type=str, help="Specific symbol to backfill (optional)")
    args = parser.parse_args()
    
    if args.symbol:
        # Override the global SYMBOLS list for this run
        logging.info(f"Overriding symbol list with single target: {args.symbol}")
        # We need to monkeypath run_backfill's iteration or change how run_backfill works.
        # Since run_backfill uses global SYMBOLS from import, we can patch the list in the module scope
        # BUT run_backfill imports SYMBOLS directly from config.settings inside the function? No, at top level.
        # Line 9: from config.settings import SYMBOLS
        # So 'SYMBOLS' is a local variable in the module now.
        # We can just update it.
        SYMBOLS.clear()
        SYMBOLS.append(args.symbol.upper())
        
    run_backfill()
