from abc import ABC, abstractmethod
from typing import Dict, Deque
from collections import deque
import pandas as pd
import logging

from backtesting.simulation.context import TradingContext

logger = logging.getLogger("backtesting.strategy.base")

class Strategy(ABC):
    def __init__(self, symbols: list[str], lookback: int = 200):
        self.symbols = symbols
        self.lookback = lookback
        
        # History Buffer: Map symbol -> List of dictionaries (records)
        # We use this to rebuild a DataFrame for indicator calculation at each step.
        # Optimization: append to list is fast. DataFrame creation is slow-ish but acceptable for 1H backtest.
        self._history: Dict[str, Deque] = {
            s: deque(maxlen=lookback) for s in symbols
        }
        
    def on_bar(self, ctx: TradingContext):
        """
        Called on every time step.
        """
        # 1. Update History
        for sym in self.symbols:
            # We only have current candle in ctx.data.bars[sym]
            if sym in ctx.data.bars:
                c = ctx.data.bars[sym]
                record = {
                    "timestamp": c.timestamp,
                    "Open": c.open,
                    "High": c.high,
                    "Low": c.low,
                    "Close": c.close,
                    "Volume": c.volume
                }
                # Unpack pre-calculated indicators
                if c.indicators:
                    record.update(c.indicators)
                    
                self._history[sym].append(record)
                
        # 2. Execute Logic
        self.execute(ctx)
        
    @abstractmethod
    def execute(self, ctx: TradingContext):
        """
        User implementation goes here.
        """
        pass

    def get_history_df(self, symbol: str) -> pd.DataFrame:
        """
        Returns the Lookback Window as a DataFrame.
        """
        data = list(self._history[symbol])
        if not data:
            return pd.DataFrame()
            
        df = pd.DataFrame(data)
        df.set_index("timestamp", inplace=True)
        return df
