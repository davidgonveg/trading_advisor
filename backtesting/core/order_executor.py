import logging
import uuid
import pandas as pd
from typing import Dict, List, Optional
from backtesting.core.schema import Order, OrderSide, OrderType, OrderStatus, Trade

logger = logging.getLogger("backtesting.core.order_executor")

class OrderExecutor:
    def __init__(self, commission_pct: float = 0.001, slippage_pct: float = 0.0005):
        self.commission_pct = commission_pct
        self.slippage_pct = slippage_pct
        self.active_orders: Dict[str, Order] = {}
        
    def submit_order(self, order: Order):
        self.active_orders[order.id] = order
        logger.info(f"[ORDER SUBMITTED] {order.order_type.value} {order.side.value} | {order.quantity} {order.symbol} @ {order.price if order.price else 'MKT'} | Tag: {order.tag}")
        
    def cancel_order(self, order_id: str):
        if order_id in self.active_orders:
            order = self.active_orders[order_id]
            order.status = OrderStatus.CANCELED
            del self.active_orders[order_id]
            logger.info(f"[ORDER CANCELED] {order.id} | {order.symbol} {order.side.value}")

    def process_bar(self, bar: pd.Series, symbol: str) -> List[Trade]:
        """
        Matches active orders against the current bar.
        """
        import pandas as pd # Ensure accessible
        trades = []
        filled_ids = []
        
        open_p = bar['Open']
        high_p = bar['High']
        low_p = bar['Low']
        close_p = bar['Close']
        ts = bar.name # Timestamp (index)
        
        for oid, order in self.active_orders.items():
            if order.symbol != symbol:
                continue
            
            logger.debug(f"[DEBUG] Processing {order.id} against bar {ts} | Range: {low_p}-{high_p}")
                
            fill_price = None
            
            if order.order_type == OrderType.MARKET:
                fill_price = open_p
                logger.debug(f"[DEBUG] Market order {order.id} matches Open: {open_p}")
                
            elif order.order_type == OrderType.LIMIT:
                if order.side == OrderSide.BUY:
                    if low_p <= order.price:
                        fill_price = min(open_p, order.price)
                        logger.debug(f"[DEBUG] Limit Buy {order.id} triggered. Low {low_p} <= Limit {order.price}. Fill: {fill_price}")
                else: # SELL
                    if high_p >= order.price:
                        fill_price = max(open_p, order.price)
                        logger.debug(f"[DEBUG] Limit Sell {order.id} triggered. High {high_p} >= Limit {order.price}. Fill: {fill_price}")
                        
            elif order.order_type == OrderType.STOP:
                if order.side == OrderSide.BUY:
                    if high_p >= order.stop_price:
                        fill_price = max(open_p, order.stop_price)
                        logger.debug(f"[DEBUG] Stop Buy {order.id} triggered. High {high_p} >= Stop {order.stop_price}. Fill: {fill_price}")
                else: # SELL
                    if low_p <= order.stop_price:
                        fill_price = min(open_p, order.stop_price)
                        logger.debug(f"[DEBUG] Stop Sell {order.id} triggered. Low {low_p} <= Stop {order.stop_price}. Fill: {fill_price}")
            
            if fill_price is not None:
                # Apply Slippage
                slippage_amount = fill_price * self.slippage_pct
                if order.side == OrderSide.BUY:
                    final_price = fill_price + slippage_amount
                else:
                    final_price = fill_price - slippage_amount
                
                logger.debug(f"[DEBUG] Applying Slippage: Base {fill_price} -> Final {final_price:.4f} (Pct: {self.slippage_pct})")

                # Calculate Commission
                commission = final_price * order.quantity * self.commission_pct
                
                trade = Trade(
                    id=str(uuid.uuid4()),
                    order_id=order.id,
                    timestamp=ts,
                    symbol=symbol,
                    side=order.side,
                    quantity=order.quantity,
                    price=final_price,
                    commission=commission,
                    slippage=slippage_amount,
                    tag=order.tag
                )
                
                # Update Order
                order.status = OrderStatus.FILLED
                order.filled_price = final_price
                order.filled_quantity = order.quantity
                order.fill_time = ts
                
                logger.info(f"[FILL] {order.side.value} {order.symbol} | Qty: {order.quantity} @ {final_price:.2f} | Comm: ${commission:.2f}")
                
                trades.append(trade)
                filled_ids.append(oid)
                
        # Cleanup
        for oid in filled_ids:
            del self.active_orders[oid]
            
        return trades
