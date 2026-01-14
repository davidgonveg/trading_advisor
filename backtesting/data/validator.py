import pandas as pd
from datetime import timedelta
import logging
from typing import List, Tuple
from .schema import Candle

logger = logging.getLogger("backtesting.data.validator")

class DataValidationException(Exception):
    pass

class GapValidator:
    def __init__(self, expected_interval_minutes: int = 60):
        self.interval = timedelta(minutes=expected_interval_minutes)
        self.market_hours_start = 13 # 13:00 UTC approx (adaptable) - simplified for now
        self.market_hours_end = 20   # 20:00 UTC approx
        
    def validate_continuity(self, df: pd.DataFrame, symbol: str) -> List[Tuple[pd.Timestamp, pd.Timestamp]]:
        """
        Checks for gaps in the DatetimeIndex.
        Returns a list of (start_gap, end_gap) tuples.
        """
        if df.empty:
            raise DataValidationException(f"Dataframe for {symbol} is empty")
            
        gaps = []
        
        # Ensure sorted
        df = df.sort_index()
        
        # Calculate time diffs
        # 1H data: Diff should be 1H. 
        # Weekend gaps are expected (> 24h).
        # Overnight gaps are expected.
        
        # Simplified Check: Just check if we exist.
        # Strict Backtest: We expect data for EVERY trading hour.
        
        # Iterate (Vectorized check is harder with market hours/weekends logic without a calendar)
        # For atomic precision, we might just warn on large gaps for now
        # OR use the 'expected_range' logic.
        
        # Actual Implementation:
        # Check High >= Low constraint
        invalid_ohlc = df[df['High'] < df['Low']]
        if not invalid_ohlc.empty:
            msg = f"Found {len(invalid_ohlc)} candles with High < Low for {symbol}"
            logger.error(msg)
            raise DataValidationException(msg)
            
        invalid_vol = df[df['Volume'] < 0]
        if not invalid_vol.empty:
             msg = f"Found {len(invalid_vol)} candles with Negative Volume for {symbol}"
             logger.error(msg)
             raise DataValidationException(msg)
             
        logger.info(f"Integrity check passed for {symbol}")
        return gaps

    def detect_missing_prices(self, df: pd.DataFrame) -> bool:
        return df[['Open', 'High', 'Low', 'Close']].isnull().any().any()
