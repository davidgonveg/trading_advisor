import logging
import uuid
from typing import List, Dict, Optional
from datetime import datetime

from .broker_schema import Order, OrderType, OrderSide, OrderStatus, Trade, Position
from backtesting.data.schema import BarData

logger = logging.getLogger("backtesting.simulation.broker")

class Broker:
    def __init__(self, initial_cash: float):
        self.initial_cash = initial_cash
        self.cash = initial_cash
        self.equity = initial_cash
        
        self.positions: Dict[str, Position] = {}
        self.active_orders: Dict[str, Order] = {} # Orders waiting to be filled
        self.trades: List[Trade] = []
        
        # Configuration
        self.commission_per_share = 0.005 # Example: IBKR Pro Lite
        self.min_commission = 1.0
        
    def submit_order(self, order: Order) -> bool:
        """
        Receives an order from Strategy. 
        Validates basic checks (negative qty, etc).
        DOES NOT check purchasing power yet (checked at fill time for Limit, or now for Market?).
        
        Realism: Market orders check cash NOW. Limit orders check cash LATER (or reserve it).
        For simplicity V1: Check cash at Fill Time.
        """
        if order.quantity <= 0:
            logger.warning(f"Order rejected: Qty {order.quantity} <= 0")
            return False
            
        order.status = OrderStatus.ACCEPTED
        self.active_orders[order.id] = order
        logger.info(f"Order Accepted: {order.side.value} {order.quantity} {order.symbol} @ {order.price if order.price else 'MKT'} [{order.tag}]")
        return True

    def cancel_order(self, order_id: str):
        if order_id in self.active_orders:
            self.active_orders[order_id].status = OrderStatus.CANCELED
            del self.active_orders[order_id]
            logger.info(f"Order Canceled: {order_id}")

    def process_bar(self, current_data: BarData):
        """
        The Matching Engine.
        Checks all active orders against the current bar's High/Low.
        """
        filled_order_ids = []
        
        for order_id, order in self.active_orders.items():
            symbol = order.symbol
            if symbol not in current_data.bars:
                continue
                
            candle = current_data.bars[symbol]
            
            # Execution Logic
            execution_price = None
            
            if order.order_type == OrderType.MARKET:
                # Market fills at Open of this bar (assuming decision was made on previous Close)
                # OR fills at Close? 
                # Standard Backtesting: Signals generated on Close of Bar T-1.
                # Orders submitted "At Market" execute at Open of Bar T.
                # So here, we should fill at Open.
                execution_price = candle.open
                
            elif order.order_type == OrderType.LIMIT:
                # Buy Limit: Low <= Price
                if order.side == OrderSide.BUY:
                    if candle.low <= order.price:
                        # Realistic Fill: If open < limit, we filled at Open!
                        # Otherwise we filled at Limit.
                        execution_price = min(candle.open, order.price) if candle.open < order.price else order.price
                # Sell Limit: High >= Price
                else:
                    if candle.high >= order.price:
                        execution_price = max(candle.open, order.price) if candle.open > order.price else order.price

            elif order.order_type == OrderType.STOP:
                # Buy Stop: High >= Price (Breakout)
                if order.side == OrderSide.BUY:
                    if candle.high >= order.stop_price:
                        # Stop triggers Market order.
                        # Fill at Stop Price + Slippage? Or max(Open, Stop)?
                        execution_price = max(candle.open, order.stop_price)
                # Sell Stop: Low <= Price (Stop Loss)
                else:
                    if candle.low <= order.stop_price:
                        execution_price = min(candle.open, order.stop_price)

            # --- EXECUTE IF MATCHED ---
            if execution_price:
                if self._try_execute_trade(order, execution_price, candle.timestamp):
                    filled_order_ids.append(order_id)
        
        # Cleanup filled
        for oid in filled_order_ids:
            del self.active_orders[oid]
            
        # Update Equity (Mark to Market)
        self._update_equity(current_data)

    def _try_execute_trade(self, order: Order, price: float, timestamp: datetime) -> bool:
        """
        Atomic Execution Step.
        1. Calculate Cost + Comm
        2. Check Cash (Buying Power)
        3. Deduct Cash
        4. Create Trade
        5. Update Position
        """
        cost = price * order.quantity
        commission = max(self.min_commission, order.quantity * self.commission_per_share)
        
        required_cash = 0.0
        
        # Capital Check logic
        if order.side == OrderSide.BUY:
            required_cash = cost + commission
            
            if self.cash < required_cash:
                # BEST EFFORT FILL:
                # Try to fill partial quantity with available cash
                
                # Estimate affordable qty: (Cash - MinComm) / (Price + CommPerShare)
                # Formula: Cash = Q * Price + Max(MinComm, Q*CommPerShare)
                # Approximation:
                safe_cash = self.cash - self.min_commission
                if safe_cash <= 0:
                     logger.warning(f"MARGIN CALL / INSUFFICIENT FUNDS: Needed {required_cash:.2f}, Has {self.cash:.2f}. Canceling Order {order.id}")
                     order.status = OrderStatus.REJECTED
                     return True
                     
                max_affordable_qty = int(safe_cash / price)
                
                # Re-check with precise comm calculation
                while max_affordable_qty > 0:
                    test_cost = max_affordable_qty * price
                    test_comm = max(self.min_commission, max_affordable_qty * self.commission_per_share)
                    if (test_cost + test_comm) <= self.cash:
                        break
                    max_affordable_qty -= 1
                    
                if max_affordable_qty > 0:
                    logger.warning(f"PARTIAL FILL {order.symbol}: Requested {order.quantity}, Funds for {max_affordable_qty}. Adjusting.")
                    order.quantity = max_affordable_qty
                    # Update Loop Variables
                    cost = price * order.quantity
                    commission = max(self.min_commission, order.quantity * self.commission_per_share)
                else:
                    logger.warning(f"MARGIN CALL / INSUFFICIENT FUNDS: Needed {required_cash:.2f}, Has {self.cash:.2f}. Canceling Order {order.id}")
                    order.status = OrderStatus.REJECTED
                    return True # Treat as "handled" (removed from queue)
        else:
            # Check for Sell availability (Long Only enforcement)
            current_pos_qty = self.positions.get(order.symbol, Position(symbol=order.symbol)).quantity
            
            if current_pos_qty < order.quantity:
                 logger.warning(f"REJECTED SELL {order.symbol}: Needed {order.quantity}, Has {current_pos_qty}. (Short Selling disabled)")
                 order.status = OrderStatus.REJECTED
                 return True
                 
            # If closing, no cash needed strictly.
            pass 

        # Execute
        self.cash -= commission
        if order.side == OrderSide.BUY:
            self.cash -= cost
        else:
            self.cash += cost # Short selling adds cash? Technically yes, sets margin liability. 
                              # Simplified: Cash Balance increases, but Position value is negative.
        
        trade = Trade(
            id=str(uuid.uuid4()),
            order_id=order.id,
            timestamp=timestamp,
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            price=price,
            commission=commission
        )
        
        order.status = OrderStatus.FILLED
        order.filled_price = price
        order.filled_quantity = order.quantity
        order.fill_time = timestamp
        
        self.trades.append(trade)
        
        # Update Position
        pos = self.positions.get(order.symbol, Position(symbol=order.symbol))
        pos.update(trade)
        self.positions[order.symbol] = pos
        
        # Remove zero positions
        if pos.quantity == 0:
            del self.positions[order.symbol]
            
        logger.info(f"FILLED {order.side.value} {order.symbol}: {order.quantity} @ {price:.2f} (Comm: {commission:.2f})")
        return True

    def _update_equity(self, data: BarData):
        """Recalculate Total Equity based on current prices."""
        pos_value = 0.0
        for sym, pos in self.positions.items():
            price = data.get_price(sym)
            if price:
                pos_value += pos.quantity * price
            else:
                # If no price (gap), use last known Average Price roughly?
                # Or keep strictly last known market price.
                pos_value += pos.quantity * pos.average_price # Fallback
                
        self.equity = self.cash + pos_value
