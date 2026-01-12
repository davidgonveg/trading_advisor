import logging
import time
from datetime import datetime, timedelta
from typing import List, Optional
import pandas as pd

from config.settings import SYMBOLS
from data.providers.factory import DataProviderFactory
from data.storage.database import Database
from data.quality.detector import GapDetector, Gap
from data.quality.repair import GapRepair
from data.interfaces import Candle

logger = logging.getLogger("core.data.quality.continuous")

class ContinuousCollector:
    """
    Service to collect data continuously, detect gaps, and repair them.
    Ensures data integrity for the strategy.
    """
    
    def __init__(self):
        self.provider_factory = DataProviderFactory()
        self.db = Database()
        self.detector = GapDetector()
        self.repair = GapRepair()
        self.symbols = SYMBOLS
        
    def run_cycle(self):
        """
        Run a single collection cycle for all symbols.
        1. Fetch latest data.
        2. Detect Gaps.
        3. Repair if needed.
        4. Store in DB.
        """
        logger.info("Starting collection cycle...")
        
        for symbol in self.symbols:
            try:
                self._process_symbol(symbol)
            except Exception as e:
                logger.error(f"Error processing {symbol}: {e}")
                
        logger.info("Cycle completed.")
        
    def _process_symbol(self, symbol: str):
        # 1. Fetch Data (last 30 days to ensure continuity checks)
        # In production, we might fetch less, but for gap detection we need context.
        df = self.provider_factory.get_data(symbol, timeframe="1h", days_back=30)
        
        if df is None or df.empty:
            logger.warning(f"No data fetched for {symbol}")
            return

        # 2. Detect Gaps
        gaps = self.detector.detect_gaps(df, symbol, expected_interval_minutes=60)
        
        if gaps:
            logger.info(f"Found {len(gaps)} gaps for {symbol}")
            # 3. Repair Gaps
            df = self.repair.fill_gaps(df, gaps)
            
        # 4. Convert and Store
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
            
        # Store (Upsert)
        # Note: Optimization - only store new or changed candles? 
        # For now, bulk saving 30 days every cycle is heavy. 
        # Ideally we only save the last X candles or the repaired ones.
        # But this ensures the DB is always in sync with the "Repaired" reality.
        # Let's limit to last 5 days for efficiency in this loop unless backfilling.
        
        recent_cutoff = datetime.now(df.index.tz) - timedelta(days=5)
        recent_candles = [c for c in candles if c.timestamp >= recent_cutoff]
        
        self.db.save_bulk_candles(symbol, "1h", recent_candles)
        logger.info(f"Saved {len(recent_candles)} candles for {symbol}")

if __name__ == "__main__":
    # Simple standalone run
    logging.basicConfig(level=logging.INFO)
    collector = ContinuousCollector()
    collector.run_cycle()
