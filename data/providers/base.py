from abc import ABC, abstractmethod
import pandas as pd
from typing import Optional, Dict, Any

class DataProvider(ABC):
    """
    Abstract Base Class for Data Providers.
    Enforces a common interface for fetching market data.
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}

    @abstractmethod
    def fetch_data(self, symbol: str, timeframe: str, start_date: str = None, end_date: str = None, days: int = None) -> Optional[pd.DataFrame]:
        """
        Fetch OHLCV data for a given symbol.
        
        Args:
            symbol: Ticker symbol (e.g., "AAPL", "^GSPC")
            timeframe: "1m", "5m", "15m", "1h", "1d"
            start_date: Start date string (YYYY-MM-DD)
            end_date: End date string (YYYY-MM-DD)
            days: Number of days to look back (alternative to start/end)

        Returns:
            pd.DataFrame with index as DatetimeIndex (tz-aware) and columns:
            ['Open', 'High', 'Low', 'Close', 'Volume']
            Returns None if fetch fails.
        """
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the provider (e.g., 'YFINANCE', 'TWELVE_DATA')"""
        pass

    @property
    @abstractmethod
    def priority(self) -> int:
        """Priority (Lower is better/primary)"""
        pass
