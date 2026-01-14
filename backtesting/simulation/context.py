from dataclasses import dataclass
from typing import Dict, List, Optional
from datetime import datetime

from backtesting.simulation.broker import Broker, Position, Order
from backtesting.data.schema import BarData

class TradingContext:
    """
    The 'World View' provided to the Strategy at each step.
    Prevents the Strategy from accessing future data or internal engine state.
    """
    def __init__(self, broker: Broker, current_time: datetime, current_data: BarData):
        self._broker = broker
        self.timestamp = current_time
        self.data = current_data
        
    @property
    def capital(self) -> float:
        return self._broker.cash
        
    @property
    def equity(self) -> float:
        return self._broker.equity
        
    @property
    def positions(self) -> Dict[str, Position]:
        return self._broker.positions.copy() # Return copy to prevent mutation
        
    @property
    def active_orders(self) -> Dict[str, Order]:
        return self._broker.active_orders.copy()
        
    def submit_order(self, order: Order):
        return self._broker.submit_order(order)
        
    def cancel_order(self, order_id: str):
        self._broker.cancel_order(order_id)
        
    def get_price(self, symbol: str) -> Optional[float]:
        return self.data.get_price(symbol)
