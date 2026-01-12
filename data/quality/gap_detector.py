import pandas as pd
import logging
from typing import List, Optional
from datetime import timedelta
from dataclasses import dataclass

logger = logging.getLogger("core.data.quality.gap_detector")

@dataclass
class Gap:
    symbol: str
    start_time: pd.Timestamp
    end_time: pd.Timestamp
    duration_minutes: float
    
    @property
    def is_fillable(self) -> bool:
        # Simple rule: < 72 hours (weekend) is fillable.
        # > 72 hours might be missing data chunks.
        return self.duration_minutes < (72 * 60)

class GapDetector:
    """
    Detects gaps in time-series data.
    """
    
    def __init__(self, expected_interval_minutes: int = 60):
        self.interval = expected_interval_minutes

    def detect_gaps(self, df: pd.DataFrame, symbol: str) -> List[Gap]:
        """
        Detects time gaps in DataFrame index.
        Assumes DF has DatetimeIndex.
        """
        if df.empty or len(df) < 2:
            return []
            
        gaps = []
        
        # Calculate time diffs
        # Shift index to compare current with previous
        # We need to sort just in case
        df = df.sort_index()
        
        # Series of timestamps
        timestamps = df.index.to_series()
        diffs = timestamps.diff()
        
        # Threshold: 2 * interval (buffer for small glitches)
        # For 1H data, gap if diff > 65 min? No, normally exactly 60.
        # But allow minimal jitter. 
        # Actually, let's say gap if > 1.1 * interval.
        threshold = timedelta(minutes=self.interval * 1.5)
        
        for i, delta in enumerate(diffs):
            if pd.isna(delta):
                continue
                
            if delta > threshold:
                gap_end = timestamps.iloc[i]     # Current candle time
                gap_start = timestamps.iloc[i-1] # Previous candle time
                
                # Check if it's just overnight/weekend?
                # For Crypto (24/7) any gap is bad.
                # For Stocks, overnight gaps are normal if we only have market hours.
                # IF the data is supposed to include extended hours or we are 24/7, then logic differs.
                # Assuming Market Hours specific logic is handled by "Business Days" or ignored for now 
                # and we rely on 'fill' logic which fills forward.
                
                duration_min = delta.total_seconds() / 60
                
                # Filter out normal overnight gap (e.g. 16:00 to 09:30 = 17.5 hours = 1050 min)
                # Filter out weekend gap (Friday 16:00 to Mon 09:30 = ~65 hours)
                # If we want to FILL these gaps for continuity (indicators often need continuity),
                # we return them as gaps to be filled.
                
                gaps.append(Gap(
                    symbol=symbol,
                    start_time=gap_start,
                    end_time=gap_end,
                    duration_minutes=duration_min
                ))
                
        return gaps
