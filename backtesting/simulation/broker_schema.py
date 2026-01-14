from dataclasses import dataclass, field
from enum import Enum, auto
from datetime import datetime
from typing import Optional, List

class OrderSide(Enum):
    BUY = "BUY"
    SELL = "SELL"

class OrderType(Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT" # Not used yet but good to have

class OrderStatus(Enum):
    CREATED = auto() # Internal
    SUBMITTED = auto() # Sent to Broker
    ACCEPTED = auto() # Acknowledged by Exchange (Pending)
    FILLED = auto() 
    CANCELED = auto()
    REJECTED = auto()
    EXPIRED = auto()

@dataclass
class Order:
    id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    price: Optional[float] = None # For Limit
    stop_price: Optional[float] = None # For Stop
    
    timestamp: datetime = field(default_factory=datetime.now) # Creation time
    status: OrderStatus = OrderStatus.CREATED
    filled_price: Optional[float] = None
    filled_quantity: float = 0.0
    fill_time: Optional[datetime] = None
    tag: Optional[str] = None # E.g. "E1", "SL", "TP1"

@dataclass
class Trade:
    """A record of a single execution fill."""
    id: str
    order_id: str
    timestamp: datetime
    symbol: str
    side: OrderSide
    quantity: float
    price: float
    commission: float = 0.0

@dataclass
class Position:
    symbol: str
    quantity: float = 0.0
    average_price: float = 0.0
    
    # Realism: Needed for calculating accurate PnL
    realized_pnl: float = 0.0
    
    def update(self, trade: Trade):
        """
        Updates position based on a new trade fill.
        Handles weighted average price and PnL realization.
        """
        if trade.symbol != self.symbol:
            return

        # Simple case: Long only or Short only logic for now?
        # Let's handle generic Long/Short math.
        
        # 0. Initial state
        if self.quantity == 0:
            self.quantity = trade.quantity if trade.side == OrderSide.BUY else -trade.quantity
            self.average_price = trade.price
            return

        is_buy = trade.side == OrderSide.BUY
        trade_qty_signed = trade.quantity if is_buy else -trade.quantity
        
        # 1. Increasing Position (Adding)
        # Same sign
        if (self.quantity > 0 and is_buy) or (self.quantity < 0 and not is_buy):
            total_cost = (self.quantity * self.average_price) + (trade_qty_signed * trade.price)
            self.quantity += trade_qty_signed
            self.average_price = total_cost / self.quantity
            
        # 2. Reducing/Closing Position
        else:
            # PnT Calculation: (Exit Price - Entry Price) * Qty
            # Logic: We are closing 'trade.quantity' amount.
            # Determine closed qty (min of remaining vs trade)
            
            # Simplified: Assume FIFO or Weighted Average PnL.
            # Using Weighted Average is standard for simple backtests.
            
            closing_qty = min(abs(self.quantity), trade.quantity)
            
            # PnL on the closed portion
            if self.quantity > 0: # Long closing
                pnl = (trade.price - self.average_price) * closing_qty
            else: # Short closing
                pnl = (self.average_price - trade.price) * closing_qty
                
            self.realized_pnl += pnl
            
            self.quantity += trade_qty_signed # This reduces the magnitude
            
            if abs(self.quantity) < 1e-9: # Floating point zero
                self.quantity = 0.0
                self.average_price = 0.0
            # Note: Average price doesn't change when reducing position size in Weighted Average method.
