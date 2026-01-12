from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Union
from dataclasses import dataclass
from datetime import datetime
import pandas as pd

@dataclass
class Candle:
    """Standardized OHLCV Candle structure"""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    def to_dict(self) -> Dict:
        return {
            "timestamp": self.timestamp,
            "Open": self.open,
            "High": self.high,
            "Low": self.low,
            "Close": self.close,
            "Volume": self.volume
        }

class IDataProvider(ABC):
    """
    Interface for all Data Providers.
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @property
    @abstractmethod
    def priority(self) -> int:
        pass

    @abstractmethod
    def fetch_data(self, 
                   symbol: str, 
                   timeframe: str, 
                   start_date: Optional[str] = None, 
                   end_date: Optional[str] = None, 
                   days_back: int = 30) -> Optional[pd.DataFrame]:
        """
        Fetch historical data.
        Returns DataFrame with DatetimeIndex (tz-aware) and columns:
        [Open, High, Low, Close, Volume]
        """
        pass
