from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, Iterator, Optional, Dict

@dataclass(frozen=True)
class Candle:
    """
    Atomic unit of OHLCV data.
    Frozen to prevent accidental mutation during backtest.
    """
    timestamp: datetime
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    
    @property
    def typical_price(self) -> float:
        return (self.high + self.low + self.close) / 3.0

@dataclass(frozen=True)
class BarData:
    """
    Container for Multi-Frame synchronized data at a specific timestamp.
    Used to pass "Point-in-Time" data to Strategy.
    """
    timestamp: datetime
    bars: Dict[str, Candle] # Map symbol -> Candle (1H)
    daily_bars: Dict[str, Candle] # Map symbol -> Candle (Daily - Previous Close)
    daily_indicators: Dict[str, Dict[str, float]] # Map symbol -> { 'SMA50': 123.4 }
    
    def get_price(self, symbol: str) -> Optional[float]:
        """Helper to get close price"""
        if symbol in self.bars:
            return self.bars[symbol].close
        return None

class DataFeed(Protocol):
    """
    Interface for Data Feeds.
    Must yield time-aligned data.
    """
    def __iter__(self) -> Iterator[BarData]:
        ...
        
    @property
    def symbols(self) -> list[str]:
        ...
