import logging
import pandas as pd
from typing import Dict, List, Any, Optional
from backtesting.core.schema import Trade, Order, OrderSide, OrderStatus, OrderType
logger = logging.getLogger("backtesting.core.portfolio")

class Portfolio:
    def __init__(self, initial_capital: float):
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.positions: Dict[str, float] = {} # symbol -> quantity
        self.trades: List[Trade] = []
        self.open_trades: List[Trade] = [] # Tracks entry fills not yet fully closed
        self.equity_curve: List[Dict[str, Any]] = []
        self.max_equity = initial_capital
        
    def apply_trade(self, trade: Trade):
        """
        Updates cash and positions based on a trade execution.
        Handles both opening and closing of Long and Short positions.
        """
        self.trades.append(trade)
        
        current_qty = self.positions.get(trade.symbol, 0.0)
        
        # Calculate cash impact
        impact = trade.price * trade.quantity
        commission = trade.commission
        
        # 1. Cash adjustment
        if trade.side == OrderSide.BUY:
            self.cash -= (impact + commission)
        else:
            self.cash += (impact - commission)
            
        # 2. Position and FIFO adjustment
        # Logic: If the trade is in the SAME direction as current position, it's an opening trade.
        # If it's in the OPPOSITE direction, it's a closing trade.
        
        is_closing = False
        if current_qty > 0 and trade.side == OrderSide.SELL:
            is_closing = True
        elif current_qty < 0 and trade.side == OrderSide.BUY:
            is_closing = True
            
        if is_closing:

            # Closing trade logic (FIFO)
            qty_to_close = trade.quantity
            total_entry_cost = 0.0
            new_open_trades = []
            
            # Store SL for R calc
            trade_sl = None
            entry_price_avg = 0.0
            total_closed_qty = 0.0
            
            for ot in self.open_trades:
                if ot["symbol"] == trade.symbol and qty_to_close > 0:
                    closed = min(qty_to_close, ot["quantity"])
                    total_entry_cost += closed * ot["price"]
                    ot["quantity"] -= closed
                    qty_to_close -= closed
                    
                    # Capture SL from the first chunk we fully or partially close
                    if trade_sl is None and 'metadata' in ot:
                         trade_sl = ot['metadata'].get('sl')
                    
                    total_closed_qty += closed

                    if ot["quantity"] > 1e-6:
                        new_open_trades.append(ot)
                else:
                    new_open_trades.append(ot)
                    
            self.open_trades = new_open_trades
            
            # P&L calculation
            if total_entry_cost > 0:
                # For long: P&L = exit_value - entry_cost
                # For short: P&L = entry_value (at sell) - exit_cost (at buy)
                # impact = trade.price * trade.quantity. We closed 'trade.quantity - qty_to_close'
                closed_qty = trade.quantity - qty_to_close
                closed_impact = trade.price * closed_qty
                
                entry_avg = total_entry_cost / closed_qty if closed_qty > 0 else 0
                
                if current_qty > 0: # Closing Long
                    pnl = closed_impact - total_entry_cost - commission
                    # R calc: (Exit - Entry) / (Entry - SL)
                    if trade_sl and abs(entry_avg - trade_sl) > 1e-6:
                        risk_per_share = abs(entry_avg - trade_sl)
                        r_multiple = (trade.price - entry_avg) / risk_per_share
                    else:
                        r_multiple = 0.0
                        
                else: # Closing Short
                    pnl = total_entry_cost - closed_impact - commission
                    # R calc: (Entry - Exit) / (SL - Entry)
                    if trade_sl and abs(trade_sl - entry_avg) > 1e-6:
                        risk_per_share = abs(trade_sl - entry_avg)
                        r_multiple = (entry_avg - trade.price) / risk_per_share
                    else:
                         r_multiple = 0.0
                    
                pnl_pct = (pnl / total_entry_cost) * 100 if total_entry_cost != 0 else 0
                
                outcome_str = "(WIN)" if pnl > 0 else "(LOSS)" if pnl < 0 else "(FLAT)"
                logger.info(f"--- [CLOSED] {trade.symbol} {outcome_str} | P&L: ${pnl:.2f} ({r_multiple:+.2f}R) | Reason: {trade.tag} | Cash: ${self.cash:.2f}")
            
            # If there's remaining quantity, it becomes an opening trade in the opposite direction
            if qty_to_close > 1e-6:
                side_str = "BUY" if trade.side == OrderSide.BUY else "SELL"
                logger.info(f"[PORTFOLIO] Reversing position {trade.symbol} with {qty_to_close} remaining")
                self.open_trades.append({
                    "price": trade.price,
                    "quantity": qty_to_close,
                    "symbol": trade.symbol,
                    "timestamp": trade.timestamp,
                    "tag": trade.tag
                })
        else:
            # Opening trade logic
            self.open_trades.append({
                "price": trade.price,
                "quantity": trade.quantity,
                "symbol": trade.symbol,
                "timestamp": trade.timestamp,
                "tag": trade.tag,
                "metadata": trade.metadata
            })
            side_str = "LONG" if trade.side == OrderSide.BUY else "SHORT"
            logger.info(f"+++ [OPEN] {side_str} {trade.symbol} | Qty: {trade.quantity:.4f} @ {trade.price:.2f}")

        # Update position quantity
        if trade.side == OrderSide.BUY:
            self.positions[trade.symbol] = current_qty + trade.quantity
        else:
            self.positions[trade.symbol] = current_qty - trade.quantity
            
        # Clean up zero positions
        if abs(self.positions.get(trade.symbol, 0.0)) < 1e-9:
            self.positions.pop(trade.symbol, None)

    def record_snapshot(self, timestamp: pd.Timestamp, current_prices: Dict[str, float]):
        """
        Records the current state for the equity curve.
        """
        position_value = 0.0
        for symbol, qty in self.positions.items():
            price = current_prices.get(symbol)
            if price is not None:
                position_value += qty * price
                
        total_equity = self.cash + position_value
        self.max_equity = max(self.max_equity, total_equity)
        drawdown = (total_equity / self.max_equity - 1) if self.max_equity != 0 else 0
        
        if drawdown < -0.15: # 15% warning threshold
            logger.warning(f"[WARNING] Large Drawdown: {drawdown*100:.2f}% at {timestamp}")

        self.equity_curve.append({
            "timestamp": timestamp,
            "cash": self.cash,
            "position_value": position_value,
            "total_equity": total_equity,
            "drawdown": drawdown
        })
        
        logger.debug(f"[DEBUG] Snapshot {timestamp} | Equity: ${total_equity:.2f} | Cash: ${self.cash:.2f}")

    def get_context(self) -> Dict[str, Any]:
        """
        Returns the data used by the strategy to make decisions.
        """
        current_equity = self.equity_curve[-1]['total_equity'] if self.equity_curve else self.initial_capital
        return {
            "cash": self.cash,
            "positions": self.positions.copy(),
            "open_trades": [
                {"timestamp": t['timestamp'], "price": t['price'], "quantity": t['quantity'], "symbol": t['symbol'], "tag": t['tag']} 
                for t in self.open_trades
            ],
            "total_equity": current_equity,
            "unrealized_pnl": current_equity - self.initial_capital 
        }
