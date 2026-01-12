import logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from datetime import datetime

from trading.manager import TradeOrder

logger = logging.getLogger("core.backtesting.account")

@dataclass
class BacktestPosition:
    symbol: str
    quantity: int
    avg_entry_price: float
    current_price: float = 0.0
    highest_price: float = 0.0 # For trailing logic if needed
    entry_time: datetime = datetime.min
    
    @property
    def market_value(self) -> float:
        return self.quantity * self.current_price
        
    @property
    def unrealized_pnl(self) -> float:
        return (self.current_price - self.avg_entry_price) * self.quantity

    @property
    def pnl_pct(self) -> float:
        if self.avg_entry_price == 0: return 0.0
        return (self.current_price - self.avg_entry_price) / self.avg_entry_price * 100

class Account:
    """
    Simulates a Trading Account (Broker).
    Tracks: Balance, Equity, Positions, Pending Orders.
    Executes: Orders against OHLC data.
    """
    
    def __init__(self, initial_capital: float = 10000.0):
        self.initial_balance = initial_capital
        self.balance = initial_capital # Cash (Realized)
        self.positions: Dict[str, BacktestPosition] = {} # Symbol -> Position
        self.pending_orders: List[TradeOrder] = []
        self.closed_trades: List[Dict] = []
        
        # State
        self.equity = initial_capital
        
    def update_equity(self):
        """Recalculate Equity = Cash + Unrealized PnL"""
        unrealized = sum(p.unrealized_pnl for p in self.positions.values())
        self.equity = self.balance + unrealized

    def get_available_capital(self) -> float:
        """
        Conservative approach: Use Equity.
        Or use Balance - Margin.
        For simplicity in Mean Reversion: Use Equity.
        """
        return self.equity

    def submit_order(self, order: TradeOrder):
        """Append order to pending list"""
        order.status = "PENDING"
        self.pending_orders.append(order)
        # logger.debug(f"Order Submitted: {order}")

    def process_candle(self, symbol: str, timestamp: datetime, 
                      open_: float, high: float, low: float, close: float):
        """
        Core Simulation Logic:
        1. Update price of open position for this symbol.
        2. Check pending orders against High/Low.
        """
        # 1. Update Position
        if symbol in self.positions:
            pos = self.positions[symbol]
            pos.current_price = close
            if high > pos.highest_price:
                pos.highest_price = high
        
        # 2. Process Orders
        # Create a copy list to iterate safely while modifying
        active_orders = [o for o in self.pending_orders if o.symbol == symbol and o.status == "PENDING"]
        
        for order in active_orders:
            executed = False
            fill_price = 0.0
            
            # --- MARKET ORDERS ---
            if order.type == "MARKET":
                # Assume fill at OPEN if it's a new candle, or CLOSE if we are processing 'after' the signal candle?
                # Usually Backtesters run: Signal at T (Close). Market Entry at T+1 (Open).
                # Here we receive T+1 candle. Fill Market at Open.
                fill_price = open_
                executed = True
                
            # --- LIMIT ORDERS (Buy Limit) ---
            elif order.type == "LIMIT" and order.side == "BUY":
                # Buy Limit executes if Low <= Price
                if low <= order.price:
                    # Fill at Order Price (or Open if Open < Price - Gap Down)
                    # Conservative: Order Price. 
                    # Realistic Gap: min(Open, Order Price) -> Better fill!
                    fill_price = min(open_, order.price)
                    executed = True

            # --- LIMIT ORDERS (Sell Limit - TP) ---
            elif order.type == "LIMIT" and order.side == "SELL":
                # Sell Limit executes if High >= Price
                if high >= order.price:
                    fill_price = max(open_, order.price)
                    executed = True

            # --- STOP ORDERS (Sell Stop - SL) ---
            elif order.type == "STOP" and order.side == "SELL":
                # Sell Stop (SL) executes if Low <= Price
                if low <= order.price:
                    # SL Slippage usually happens.
                    # Fill at Price (Simulated) or Open if Open < Price (Gap Down).
                    # If Gap Down, we sell at Open! (Worse price).
                    fill_price = min(open_, order.price)
                    executed = True
            
            # --- EXECUTION ---
            if executed:
                logger.info(f"[FILL] ORDER FILLED: {order.tag} {order.side} {order.symbol} @ {fill_price:.2f} (qty: {order.quantity}) [Type: {order.type}]")
                self._execute_trade(order, fill_price, timestamp)
        
        self.update_equity()

    def _execute_trade(self, order: TradeOrder, price: float, timestamp: datetime):
        """Internal execution handler"""
        order.status = "FILLED"
        order.price = price # Update with actual fill price
        
        cost = price * order.quantity
        
        # DEBUG: Track balance changes
        balance_before = self.balance
        logger.info(f"[EXEC] Executing {order.side} {order.quantity} {order.symbol} @ {price:.2f} | Balance before: {balance_before:.2f}")
        
        if order.side == "BUY":
            # BUYING (Long Entry OR Short Cover)
            
            # CAPITAL VALIDATION: Check if we have enough balance
            if cost > self.balance:
                logger.warning(f"INSUFFICIENT FUNDS: Need {cost:.2f} but only have {self.balance:.2f}. Rejecting {order.tag} for {order.symbol}")
                order.status = "REJECTED"
                return  # Don't execute this order
            
            self.balance -= cost
            
            # Check if we are COVERING a Short
            if order.symbol in self.positions and self.positions[order.symbol].quantity < 0:
                pos = self.positions[order.symbol]
                # We are covering. 
                # PnL = (Entry - Exit) * Qty
                trade_pnl = (pos.avg_entry_price - price) * order.quantity
                
                self.closed_trades.append({
                    "symbol": order.symbol,
                    "side": "BUY (Cover)",
                    "qty": order.quantity,
                    "entry": pos.avg_entry_price,
                    "exit": price,
                    "pnl": trade_pnl,
                    "time": timestamp,
                    "tag": order.tag
                })
                
                # Update Position
                pos.quantity += order.quantity # -10 + 10 = 0
                if pos.quantity == 0:
                    del self.positions[order.symbol]
                elif pos.quantity > 0:
                    # Flip to Long? (Should shouldn't happen in strict strategies but possible)
                    # Reset entry price for the remainder?
                    # Simplify: If flip, treat as separate? 
                    # Complex. Let's assume net-out.
                    pos.avg_entry_price = price 
                    
            else:
                # LONG ENTRY (Add or New)
                if order.symbol in self.positions:
                    pos = self.positions[order.symbol]
                    total_qty = pos.quantity + order.quantity
                    new_avg = ((pos.avg_entry_price * pos.quantity) + (price * order.quantity)) / total_qty
                    pos.quantity = total_qty
                    pos.avg_entry_price = new_avg
                else:
                    self.positions[order.symbol] = BacktestPosition(
                        symbol=order.symbol,
                        quantity=order.quantity,
                        avg_entry_price=price,
                        current_price=price,
                        entry_time=timestamp
                    )
                
        elif order.side == "SELL":
            # SELLING (Long Exit OR Short Entry)
            self.balance += cost
            
            # Check if we are CLOSING a Long
            if order.symbol in self.positions and self.positions[order.symbol].quantity > 0:
                pos = self.positions[order.symbol]
                # PnL = (Exit - Entry) * Qty
                trade_pnl = (price - pos.avg_entry_price) * order.quantity
                
                self.closed_trades.append({
                    "symbol": order.symbol,
                    "side": "SELL (Close)",
                    "qty": order.quantity,
                    "entry": pos.avg_entry_price,
                    "exit": price,
                    "pnl": trade_pnl,
                    "time": timestamp,
                    "tag": order.tag
                })
                
                pos.quantity -= order.quantity
                if pos.quantity == 0:
                    del self.positions[order.symbol]
                    
            else:
                # SHORT ENTRY (New or Add)
                # Use NEGATIVE quantity for Short
                qty_short = -order.quantity
                
                if order.symbol in self.positions:
                    # Adding to Short
                    pos = self.positions[order.symbol]
                    # Weighted Avg for Short
                    # current: -10 @ 100. New: -10 @ 110. Total -20.
                    # Value: (-10*100) + (-10*110) = -1000 - 1100 = -2100.
                    # Avg = -2100 / -20 = 105. Correct.
                    total_qty = pos.quantity + qty_short # -10 + -10 = -20
                    # Note: We use Cost (Price * Qty) logic usually.
                    total_val = (pos.avg_entry_price * pos.quantity) + (price * qty_short)
                    new_avg = total_val / total_qty
                    
                    pos.quantity = total_qty
                    pos.avg_entry_price = new_avg
                else:
                    self.positions[order.symbol] = BacktestPosition(
                        symbol=order.symbol,
                        quantity=qty_short, # NEGATIVE
                        avg_entry_price=price,
                        current_price=price,
                        entry_time=timestamp
                    )

        # Cleanup Filled order
        # (It's already marked FILLED, loop will skip it next time or we remove it)
        # Better to remove it from pending list to keep clean.
        self.pending_orders.remove(order)
        
        # DEBUG: Track balance changes
        balance_after = self.balance
        balance_delta = balance_after - balance_before
        logger.info(f"[EXEC] Balance after: {balance_after:.2f} | Delta: {balance_delta:+.2f}")

