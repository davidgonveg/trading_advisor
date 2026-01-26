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
        
        # 1. Increasing Position (Adding) - Same sign or zero
        if self.quantity == 0 or (self.quantity > 0 and is_buy) or (self.quantity < 0 and not is_buy):
            total_cost = (self.quantity * self.average_price) + (trade_qty_signed * trade.price)
            self.quantity += trade_qty_signed
            # Avoid division by zero if quantity miraculously is 0 (though covered by if)
            if abs(self.quantity) > 1e-9:
                self.average_price = abs(total_cost / self.quantity) # Price is always positive
            else:
                self.quantity = 0.0
                self.average_price = 0.0
            
        # 2. Reducing or Flipping Position
        else:
            # We are going in opposite direction
            
            # Check if we are flipping
            # Current: +10. Trade: -20. Result: -10.
            remaining_qty = self.quantity + trade_qty_signed
            
            # Case A: Flipping (Sign changes)
            if (self.quantity > 0 and remaining_qty < 0) or (self.quantity < 0 and remaining_qty > 0):
                # 1. Close the current position fully
                closed_qty = abs(self.quantity)
                
                if self.quantity > 0: # Long closing
                    pnl = (trade.price - self.average_price) * closed_qty
                else: # Short closing
                    pnl = (self.average_price - trade.price) * closed_qty
                self.realized_pnl += pnl
                
                # 2. Open the new position with the remainder
                self.quantity = remaining_qty
                self.average_price = trade.price # New price for the new direction
                
            # Case B: Reducing (Sign stays same or becomes zero)
            else:
                closed_qty = abs(trade_qty_signed)
                
                if self.quantity > 0: # Long reducing
                    pnl = (trade.price - self.average_price) * closed_qty
                else: # Short reducing
                    pnl = (self.average_price - trade.price) * closed_qty
                self.realized_pnl += pnl
                
                self.quantity += trade_qty_signed
                
                if abs(self.quantity) < 1e-9:
                   self.quantity = 0.0
                   self.average_price = 0.0
                # Average price does not change when just reducing
