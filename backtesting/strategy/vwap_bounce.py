from backtesting.strategy.base import Strategy
from backtesting.simulation.context import TradingContext
from backtesting.simulation.broker_schema import Order, OrderSide, OrderType
from backtesting.strategy.indicators import IndicatorCalculator
from backtesting.simulation.analytics import RoundTrip
from analysis.patterns import PatternRecognizer
import pandas as pd
import logging

logger = logging.getLogger("backtesting.strategy.vwap_bounce")

class VWAPBounceStrategy(Strategy):
    """
    VWAP Bounce Strategy Implementation.
    
    Rules (Long):
    1. Low <= VWAP and Close > VWAP (Bounce from below or touch)
    2. Lower Wick > 2 * Body (Bullish Rejection)
    3. Volume > VolumeSMA20
    
    Rules (Short):
    1. High >= VWAP and Close < VWAP (Bounce from above or touch)
    2. Upper Wick > 2 * Body (Bearish Rejection)
    3. Volume > VolumeSMA20
    
    Exit:
    - SL: 0.4% fixed initially.
    - TP1: 0.8% (Close 60%, Move SL to BE).
    - TP2: 1.2% (Close remainder).
    - Time Stop: Intraday (Close all at EOD 15:55 or similar? Docs say 2-8 hours. We'll close at session end for safety in V1).
    """
    
    def __init__(self, symbols: list[str]):
        super().__init__(symbols, lookback=50) # Lookback sufficient for Ind calc
        self.pattern_recognizer = PatternRecognizer()
        
        # State Management for Positions
        # We need to track 'Trade State' because the Broker is simple/manual.
        # Structure: { symbol: { 'state': 'OPEN'|'TP1_HIT', 'entry_price': float, 'sl': float, 'tp1': float, 'tp2': float } }
        self.trade_state = {} 
        
        # Parameters
        self.sl_pct = 0.004
        self.tp1_pct = 0.008
        self.tp2_pct = 0.012
        self.tp1_ratio = 0.6
        
        self.risk_per_trade = 0.015 # 1.5% capital
        
        # Signal Logger/Collector
        self.signals = []
        self.completed_trades: list[RoundTrip] = []
        self.active_round_trips: dict[str, RoundTrip] = {}

    def execute(self, ctx: TradingContext):
        # We iterate over symbols
        for symbol in self.symbols:
            if symbol not in ctx.data.bars:
                continue
                
            candle = ctx.data.bars[symbol]
            current_price = candle.close
            indicators = candle.indicators # Pre-calculated dict
            
            # 1. Manage Open Positions
            # Use ctx.positions which returns a copy of the dictionary
            positions = ctx.positions
            if symbol in positions:
                self._manage_positions(ctx, symbol, current_price, candle.timestamp, positions[symbol])
            
            # 2. Check for New Entries (only if no position)
            # Assumption: One trade per symbol at a time.
            if symbol not in positions:
                # OPTIMIZATION: Use pre-calculated indicators from Feed
                # No need to rebuild history DF or calculate indicators on the fly.
                
                # We need VWAP, VolumeSMA, Patterns from 'indicators'
                if not indicators:
                    continue
                    
                vwap = indicators.get('VWAP')
                vol_sma = indicators.get('Volume_SMA_20')
                
                if not vwap or not vol_sma: 
                    continue

                # --- ENTRY LOGIC ---
                signal_side = None
                
                # Check Filters
                # 1. Volume Confirmation
                # Note: candle.volume is distinct from indicators
                vol_ok = candle.volume > vol_sma
                
                if vol_ok:
                    # Long Setup
                    # Low <= VWAP and Close > VWAP
                    bounce_long = (candle.low <= vwap) and (candle.close > vwap)
                    # Wick Rejection
                    wick_bull = indicators.get('pat_wick_bull', 0) > 0
                    
                    if bounce_long and wick_bull:
                        signal_side = OrderSide.BUY
                        
                    # Short Setup
                    # High >= VWAP and Close < VWAP
                    bounce_short = (candle.high >= vwap) and (candle.close < vwap)
                    wick_bear = indicators.get('pat_wick_bear', 0) < 0
                    
                    if bounce_short and wick_bear:
                        signal_side = OrderSide.SELL
                        
                if signal_side:
                    self._execute_entry(ctx, symbol, signal_side, current_price)
                    
    def _execute_entry(self, ctx, symbol, side, price):
        # Risk Management
        capital = ctx.equity
        risk_amount = capital * self.risk_per_trade
        
        # Stop Loss Distance
        # SL is fixed % logic: Price * 0.004
        sl_dist = price * self.sl_pct
        
        # Quantity = Risk / SL_Dist
        if sl_dist == 0: return
        
        qty = int(risk_amount / sl_dist)
        if qty <= 0: return
        
        # Submit Order
        order = Order(
            id=f"ORD_{symbol}_{ctx.data.timestamp.timestamp()}",
            symbol=symbol,
            side=side,
            order_type=OrderType.MARKET,
            quantity=qty,
            tag="ENTRY"
        )
        if ctx.submit_order(order):
            logger.info(f"SIGNAL {side.value} {symbol} @ {price} | Qty: {qty} | Risk: {risk_amount:.2f}")
            
            # Initialize Trade State
            # Note: We assume fill happens next tick or same tick. 
            # Ideally we check 'active_orders' or listen to fills?
            # For backtesting simplicity, we assume fill and set state.
            # But Broker might reject.
            # Better: Set state ONLY when position exists? 
            # Or assume success.
            # Problem: self._manage_positions only runs if 'symbol in positions'.
            # So we can set the TARGET state now.
            
            sl_price = price * (1 - self.sl_pct) if side == OrderSide.BUY else price * (1 + self.sl_pct)
            tp1_price = price * (1 + self.tp1_pct) if side == OrderSide.BUY else price * (1 - self.tp1_pct)
            tp2_price = price * (1 + self.tp2_pct) if side == OrderSide.BUY else price * (1 - self.tp2_pct)
            
            self.trade_state[symbol] = {
                'state': 'OPEN',
                'entry_price': price,
                'sl': sl_price,
                'tp1': tp1_price,
                'tp2': tp2_price,
                'original_qty': qty
            }
            
            # Start RoundTrip tracking
            rt = RoundTrip(
                id=f"RT_{symbol}_{ctx.data.timestamp.timestamp()}",
                symbol=symbol,
                direction="LONG" if side == OrderSide.BUY else "SHORT",
                entry_time=ctx.data.timestamp,
                max_quantity=qty,
                avg_entry_price=price,
                atr_at_entry=ctx.data.bars[symbol].indicators.get('ATR', 0),
                adx_at_entry=ctx.data.bars[symbol].indicators.get('ADX', 0),
                initial_sl=sl_price,
                tp1_target=tp1_price,
                tp2_target=tp2_price,
                entry_snapshot=ctx.data.bars[symbol].indicators
            )
            rt.tags.append("E1")
            self.active_round_trips[symbol] = rt

    def _manage_positions(self, ctx, symbol, current_price, timestamp, pos):
        # Logic to handle SL, TP1, TP2 based on self.trade_state[symbol]
        
        if symbol not in self.trade_state:
            return
            
        state = self.trade_state[symbol]
        quantity = pos.quantity # Current quantity (signed)
        is_long = quantity > 0
        
        # Check Exits
        
        # 1. Stop Loss
        hit_sl = False
        if is_long:
            if current_price <= state['sl']:
                hit_sl = True
        else: # Short
            if current_price >= state['sl']:
                hit_sl = True
                
        if hit_sl:
            logger.info(f"SL HIT {symbol} @ {current_price}. Closing.")
            self._close_position(ctx, symbol, "SL", abs(quantity))
            
            # Close RoundTrip
            if symbol in self.active_round_trips:
                rt = self.active_round_trips[symbol]
                rt.close(timestamp)
                rt.exit_reason = "SL"
                rt.avg_exit_price = current_price
                rt.exit_snapshot = ctx.data.bars[symbol].indicators
                # Calculate PnL
                if rt.direction == "LONG":
                    rt.gross_pnl = (rt.avg_exit_price - rt.avg_entry_price) * rt.max_quantity
                else:
                    rt.gross_pnl = (rt.avg_entry_price - rt.avg_exit_price) * rt.max_quantity
                rt.net_pnl = rt.gross_pnl # Simplified
                rt.return_pct = (rt.net_pnl / (rt.avg_entry_price * rt.max_quantity)) * 100 if rt.avg_entry_price else 0
                
                self.completed_trades.append(rt)
                del self.active_round_trips[symbol]
                
            del self.trade_state[symbol]
            return

        # 2. TP1
        if state['state'] == 'OPEN':
            hit_tp1 = False
            if is_long and current_price >= state['tp1']:
                hit_tp1 = True
            elif not is_long and current_price <= state['tp1']:
                hit_tp1 = True
                
            if hit_tp1:
                # Close 60%
                qty_to_close = int(state['original_qty'] * self.tp1_ratio)
                if qty_to_close > 0:
                    logger.info(f"TP1 HIT {symbol} @ {current_price}. Closing {qty_to_close}.")
                    self._close_partial(ctx, symbol, qty_to_close, "TP1", quantity)
                    if symbol in self.active_round_trips:
                        self.active_round_trips[symbol].tags.append("TP1")
                
                # Move SL to BE
                state['sl'] = state['entry_price']
                state['state'] = 'TP1_HIT'
                logger.info(f"Moved SL to BE for {symbol}: {state['sl']}")
                return

        # 3. TP2
        if state['state'] == 'TP1_HIT':
            hit_tp2 = False
            if is_long and current_price >= state['tp2']:
                hit_tp2 = True
            elif not is_long and current_price <= state['tp2']:
                hit_tp2 = True
                
            if hit_tp2:
                logger.info(f"TP2 HIT {symbol} @ {current_price}. Closing data.")
                self._close_position(ctx, symbol, "TP2", abs(quantity))
                
                # Close RoundTrip
                if symbol in self.active_round_trips:
                    rt = self.active_round_trips[symbol]
                    rt.close(timestamp)
                    rt.exit_reason = "TP2"
                    rt.tags.append("TP2")
                    rt.avg_exit_price = current_price # Simplified
                    rt.exit_snapshot = ctx.data.bars[symbol].indicators
                    
                    # Calculate PnL (Weighted average properly would be better, but for now...)
                    if rt.direction == "LONG":
                        rt.gross_pnl = (rt.avg_exit_price - rt.avg_entry_price) * rt.max_quantity
                    else:
                        rt.gross_pnl = (rt.avg_entry_price - rt.avg_exit_price) * rt.max_quantity
                    rt.net_pnl = rt.gross_pnl
                    rt.return_pct = (rt.net_pnl / (rt.avg_entry_price * rt.max_quantity)) * 100 if rt.avg_entry_price else 0

                    self.completed_trades.append(rt)
                    del self.active_round_trips[symbol]
                    
                del self.trade_state[symbol]
                return
                
        # 4. End of Day Exit (Optional safety)
        # If timestamp.hour >= 16? (Market close usually 16:00 EST)
        # Assuming data is in market time or UTC? 
        # Strategy says "2-8 hours".
        pass

    def _close_position(self, ctx, symbol, tag, qty):
        """Close entire position"""
        # Note: We need side (Sell if long, Buy if short) which depends on current position
        # But we already know current pos from 'pos' arg or 'qty' sign?
        # Passed 'qty' as abs.
        # Need to know side.
        # We can look up position again or pass is_long/side.
        # Let's look up position safely.
        positions = ctx.positions
        if symbol not in positions: return
        pos = positions[symbol]
        
        side = OrderSide.SELL if pos.quantity > 0 else OrderSide.BUY
        
        order = Order(
            id=f"CLOSE_{symbol}_{ctx.data.timestamp.timestamp()}",
            symbol=symbol,
            side=side,
            order_type=OrderType.MARKET,
            quantity=qty,
            tag=tag
        )
        ctx.submit_order(order)
        
    def _close_partial(self, ctx, symbol, qty, tag, current_pos_qty):
        """Close partial quantity"""
        side = OrderSide.SELL if current_pos_qty > 0 else OrderSide.BUY
        
        order = Order(
            id=f"PARTIAL_{symbol}_{ctx.data.timestamp.timestamp()}",
            symbol=symbol,
            side=side,
            order_type=OrderType.MARKET,
            quantity=qty,
            tag=tag
        )
        ctx.submit_order(order)
