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

class OrderStatus(Enum):
    SUBMITTED = auto()
    FILLED = auto()
    CANCELED = auto()
    REJECTED = auto()

@dataclass
class Order:
    id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    price: Optional[float] = None # For Limit
    stop_price: Optional[float] = None # For Stop
    timestamp: datetime = field(default_factory=datetime.now)
    status: OrderStatus = OrderStatus.SUBMITTED
    tag: Optional[str] = None
    
    # Fill info
    filled_price: Optional[float] = None
    filled_quantity: float = 0.0
    fill_time: Optional[datetime] = None

@dataclass
class Trade:
    id: str
    order_id: str
    timestamp: datetime
    symbol: str
    side: OrderSide
    quantity: float
    price: float
    commission: float
    slippage: float
    tag: Optional[str] = None
