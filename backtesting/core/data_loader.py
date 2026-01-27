import pandas as pd
import logging
from datetime import datetime
from typing import List, Optional
from data.storage.database import Database

logger = logging.getLogger("backtesting.core.data_loader")

class DataLoader:
    def __init__(self, db_path: Optional[str] = None):
        self.db = Database() # Uses default config/database
        
    def load_data(self, symbol: str, interval: str, start_date: datetime, end_date: datetime) -> pd.DataFrame:
        """
        Loads OHLCV data from the database and performs validation.
        """
        logger.info(f"[DATA LOAD START] Loading {symbol} | Interval: {interval} | Range: {start_date.date()} to {end_date.date()}")
        
        df = self.db.load_market_data(symbol, interval)
        
        if df.empty:
            logger.error(f"[DATA ERROR] No data found for {symbol} in DB.")
            return pd.DataFrame()
            
        # Ensure index is datetime
        df.index = pd.to_datetime(df.index)
        df = df.sort_index()
        
        # Filter by date
        df = df[(df.index >= start_date) & (df.index <= end_date)]
        
        if df.empty:
            logger.warning(f"[DATA WARNING] No data in specified range for {symbol}.")
            return df
            
        logger.info(f"[DATA LOADED] {len(df)} bars loaded for {symbol}.")
        self._validate_data(df, symbol)
        
        return df
        
    def _validate_data(self, df: pd.DataFrame, symbol: str):
        """
        Performs technical validation on the data.
        """
        logger.info(f"[VALIDATION START] Validating {symbol} integrity...")
        issues_found = 0
        
        # 1. Check for duplicates
        if df.index.duplicated().any():
            dup_count = df.index.duplicated().sum()
            logger.warning(f"[VALIDATION WARNING] {symbol}: Found {dup_count} duplicated timestamps. Keeping first.")
            df = df[~df.index.duplicated(keep='first')]
            issues_found += 1
            
        # 2. Check for impossible values
        invalid_high_low = df[df['High'] < df['Low']]
        if not invalid_high_low.empty:
            logger.error(f"[VALIDATION ERROR] {symbol}: Found {len(invalid_high_low)} bars where High < Low!")
            issues_found += 1
            
        invalid_prices = df[(df['Open'] <= 0) | (df['Close'] <= 0) | (df['High'] <= 0) | (df['Low'] <= 0)]
        if not invalid_prices.empty:
            logger.warning(f"[VALIDATION WARNING] {symbol}: Found {len(invalid_prices)} bars with zero/negative prices.")
            issues_found += 1
            
        # 3. Check for gaps
        expected_intervals = df.index.to_series().diff().value_counts()
        if not expected_intervals.empty:
            most_common_interval = expected_intervals.idxmax()
            gaps = df.index.to_series().diff() > most_common_interval * 1.5
            gap_count = gaps.sum()
            if gap_count > 0:
                logger.warning(f"[VALIDATION WARNING] {symbol}: Detected {gap_count} potential data gaps.")
                issues_found += 1
            
        if issues_found == 0:
            logger.info(f"[VALIDATION PASSED] {symbol} data is clean.")
        else:
            logger.info(f"[VALIDATION COMPLETE] Found {issues_found} potential issues in {symbol}.")
            
        return df
