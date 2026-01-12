import pandas as pd
import numpy as np
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
import pytz

# Use new core logger
logger = logging.getLogger("core.data.quality.detector")

class GapType(Enum):
    """Types of gaps detected"""
    SMALL_GAP = "SMALL_GAP"           # < 4 hours
    OVERNIGHT_GAP = "OVERNIGHT_GAP"   # 8PM - 4AM
    WEEKEND_GAP = "WEEKEND_GAP"       # > 48 hours
    HOLIDAY_GAP = "HOLIDAY_GAP"       # Workday > 24h
    UNKNOWN_GAP = "UNKNOWN_GAP"       # Unclassified
    API_FAILURE = "API_FAILURE"       # Possible API issue

class GapSeverity(Enum):
    """Gap severity for prioritization"""
    LOW = "LOW"           # Normal gap, easy to fill
    MEDIUM = "MEDIUM"     # Significant gap
    HIGH = "HIGH"         # Critical for analysis
    CRITICAL = "CRITICAL" # Breaks backtesting

@dataclass
class Gap:
    """Represents a gap detected in OHLCV data"""
    symbol: str
    start_time: datetime
    end_time: datetime
    duration_minutes: float
    gap_type: GapType
    severity: GapSeverity
    
    # Context
    before_price: float
    after_price: float
    price_change_pct: float
    
    # Metadata
    detection_time: datetime = field(default_factory=datetime.now)
    suggested_strategy: str = "FORWARD_FILL"
    is_fillable: bool = True
    confidence: float = 0.5 

@dataclass
class DataQualityReport:
    """Complete Data Quality Report"""
    symbol: str
    analysis_period: Tuple[datetime, datetime]
    total_data_points: int
    expected_data_points: int
    completeness_pct: float
    
    # Gaps
    gaps_detected: List[Gap]
    total_gaps: int
    gaps_by_type: Dict[str, int]
    gaps_by_severity: Dict[str, int]
    
    # Quality Metrics
    max_gap_duration_hours: float
    avg_gap_duration_minutes: float
    price_anomalies_count: int
    volume_anomalies_count: int
    
    # Scoring
    overall_quality_score: float  # 0-100
    is_suitable_for_backtesting: bool
    recommended_actions: List[str]
    
    # Timestamps
    analysis_time: datetime = field(default_factory=datetime.now)

class GapDetector:
    """
    Main Gap Detector Logic
    """
    
    def __init__(self):
        self.config = {
            'MIN_GAP_MINUTES': 30, # More strict than legacy (60)
            'OVERNIGHT_GAP_HOURS': [20, 4],
            'WEEKEND_GAP_HOURS': 48,
            'HOLIDAY_GAP_HOURS': 24
        }
    
    def detect_gaps(self, data: pd.DataFrame, symbol: str, 
                   expected_interval_minutes: int = 15) -> List[Gap]:
        """
        Detect gaps in an OHLCV DataFrame
        """
        if len(data) < 2:
            return []
        
        # Ensure DatetimeIndex
        if not isinstance(data.index, pd.DatetimeIndex):
            data.index = pd.to_datetime(data.index)
        
        data_sorted = data.sort_index()
        gaps = []
        min_gap = self.config['MIN_GAP_MINUTES']
        
        # Calculate time diffs
        time_diffs = data_sorted.index.to_series().diff()
        
        for i, diff in enumerate(time_diffs[1:], 1):
            if pd.notna(diff):
                gap_minutes = diff.total_seconds() / 60
                
                if gap_minutes > min_gap:
                    # Found a gap
                    gap_start = data_sorted.index[i-1]
                    gap_end = data_sorted.index[i]
                    
                    # Create Gap Object
                    gap = self._create_gap(
                        symbol, gap_start, gap_end, gap_minutes,
                        data_sorted.iloc[i-1], data_sorted.iloc[i],
                        expected_interval_minutes
                    )
                    gaps.append(gap)
                    
        return gaps

    def analyze_quality(self, data: pd.DataFrame, symbol: str, 
                       expected_interval_minutes: int = 15) -> DataQualityReport:
        """
        Full Quality Analysis
        """
        if data.empty:
            raise ValueError(f"No data for {symbol}")
            
        gaps = self.detect_gaps(data, symbol, expected_interval_minutes)
        
        start = data.index.min()
        end = data.index.max()
        
        total_minutes = (end - start).total_seconds() / 60
        expected_points = int(total_minutes / expected_interval_minutes)
        actual_points = len(data)
        
        completeness = min(100.0, (actual_points / max(1, expected_points)) * 100)
        
        # Stats
        max_gap = max([g.duration_minutes for g in gaps], default=0) / 60
        avg_gap = np.mean([g.duration_minutes for g in gaps]) if gaps else 0
        
        # Simple anomaly check
        price_anomalies = 0 # Implement robust check later if needed
        volume_anomalies = 0
        
        # Score calculation (Simplified from legacy)
        score = 100 - (len(gaps) * 2) - (max_gap / 24 * 5)
        score = max(0, min(100, score))
        
        return DataQualityReport(
            symbol=symbol,
            analysis_period=(start, end),
            total_data_points=actual_points,
            expected_data_points=expected_points,
            completeness_pct=completeness,
            gaps_detected=gaps,
            total_gaps=len(gaps),
            gaps_by_type={g.gap_type.value: sum(1 for x in gaps if x.gap_type == g.gap_type) for g in gaps},
            gaps_by_severity={g.severity.value: sum(1 for x in gaps if x.severity == g.severity) for g in gaps},
            max_gap_duration_hours=max_gap,
            avg_gap_duration_minutes=avg_gap,
            price_anomalies_count=price_anomalies,
            volume_anomalies_count=volume_anomalies,
            overall_quality_score=score,
            is_suitable_for_backtesting=score > 85,
            recommended_actions=[]
        )

    def _create_gap(self, symbol, start, end, duration, before, after, interval) -> Gap:
        # Determine Type
        gap_type = GapType.UNKNOWN_GAP
        if duration > self.config['WEEKEND_GAP_HOURS'] * 60:
            gap_type = GapType.WEEKEND_GAP
        elif duration < 4 * 60:
            gap_type = GapType.SMALL_GAP
        else:
            # Check overnight logic simplified
            if start.hour >= 20 or start.hour < 4:
                gap_type = GapType.OVERNIGHT_GAP
        
        # Determine Severity
        severity = GapSeverity.MEDIUM
        intervals_lost = duration / interval
        if intervals_lost < 4: severity = GapSeverity.LOW
        elif intervals_lost > 24: severity = GapSeverity.HIGH
        
        # Price change
        p_before = float(before['Close'])
        p_after = float(after['Open'])
        pct = ((p_after - p_before) / p_before) * 100 if p_before else 0
        
        return Gap(
            symbol=symbol,
            start_time=start, end_time=end, duration_minutes=duration,
            gap_type=gap_type, severity=severity,
            before_price=p_before, after_price=p_after, price_change_pct=pct
        )
