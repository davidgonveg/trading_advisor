from abc import ABC, abstractmethod
import pandas as pd
from typing import Dict, Any, Optional
from enum import Enum

class SignalSide(Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"

class Signal:
    def __init__(self, side: SignalSide, quantity: Optional[float] = None, quantity_pct: Optional[float] = None, stop_loss: Optional[float] = None, take_profit: Optional[float] = None, tag: Optional[str] = None, metadata: Dict[str, Any] = None):
        self.side = side
        self.quantity = quantity # Fixed number of shares
        self.quantity_pct = quantity_pct # Percentage of available capital
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.tag = tag
        self.metadata = metadata or {}

class StrategyInterface(ABC):
    """
    Abstract Interface that all strategies must implement.
    """
    
    def __init__(self):
        self.last_indicators: Dict[str, Any] = {}
    
    @abstractmethod
    def setup(self, params: Dict[str, Any]):
        """
        Initialization with configurable parameters.
        """
        pass
    
    @abstractmethod
    def on_bar(self, history: pd.DataFrame, portfolio_context: Dict[str, Any]) -> Signal:
        """
        Processes each bar and returns a signal.
        - history: Historical data up to the current bar (inclusive).
        - portfolio_context: Current state of the portfolio (cash, positions, etc.).
        """
        pass
    
    @abstractmethod
    def get_params(self) -> Dict[str, Any]:
        """
        Returns the configurable parameters of the strategy.
        """
        pass
