from abc import ABC, abstractmethod
from datetime import datetime
import pytz

class TimeProvider(ABC):
    """
    Abstract interface for providing the current time.
    Used to decouple components from system time for backtesting.
    """
    @abstractmethod
    def now(self, tz: pytz.timezone = None) -> datetime:
        pass

class RealTimeProvider(TimeProvider):
    """
    Standard provider using system clock.
    """
    def now(self, tz: pytz.timezone = None) -> datetime:
        # Default to UTC if no timezone provided for consistency
        dt = datetime.now(tz if tz else pytz.UTC)
        return dt

class BacktestTimeProvider(TimeProvider):
    """
    Mock provider for backtesting.
    Controlled manually by the backtest engine.
    """
    def __init__(self, start_time: datetime = None):
        self._current_time = start_time or datetime.now(pytz.UTC)
    
    def set_time(self, new_time: datetime):
        self._current_time = new_time
        
    def now(self, tz: pytz.timezone = None) -> datetime:
        if tz:
            return self._current_time.astimezone(tz)
        return self._current_time
