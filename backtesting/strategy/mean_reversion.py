import logging
import pandas as pd
from datetime import timedelta

from backtesting.strategy.base import Strategy
from backtesting.strategy.indicators import IndicatorCalculator
from backtesting.simulation.context import TradingContext
from backtesting.simulation.broker import Order, OrderSide, OrderType

logger = logging.getLogger("backtesting.strategy.mean_reversion")

from backtesting.simulation.signal_logger import SignalLogger # Import Logger

class MeanReversionStrategy(Strategy):
    def __init__(self, symbols: list[str]):
        super().__init__(symbols, lookback=200)
        self.entry_tracker = {} # Track active "Alerts" or Trade States per symbol
        self.signal_logger = SignalLogger() # Use default path
        
    def execute(self, ctx: TradingContext):
        # 1. Manage Existing Positions & Orders
        self.manage_positions(ctx)
        
        # 2. Check for NEW Signals
        for symbol in self.symbols:
            # Skip if already in position (simplified, max 4 trades total check)
            if symbol in ctx.positions and ctx.positions[symbol].quantity != 0:
                continue
            
            # Skip if we already have active orders (pending entry)
            # Optimization: check 'active_orders' for this symbol
            has_orders = any(o.symbol == symbol for o in ctx.active_orders.values())
            if has_orders:
                continue
                
            self.check_entry(ctx, symbol)

    def check_entry(self, ctx: TradingContext, symbol: str):
        # 1. Get Data
        df = self.get_history_df(symbol)
        if len(df) < 50:
            return
            
        # 2. Calculate Indicators
        df = IndicatorCalculator.calculate(df)
        
        # 3. Check Conditions (Logic from estrategia.md)
        row = df.iloc[-1]
        prev = df.iloc[-2]
        
        # --- LONG Logic ---
        # 1. RSI < 35
        # 2. RSI Turning Up (Current > Prev)
        # 3. Price <= BB Lower
        # 4. ADX < 22
        
        # SMA 50 Check (Trend Filter)
        daily_stats = ctx.data.daily_indicators.get(symbol, {})
        sma_50 = daily_stats.get('SMA_50', 0.0)
        
        is_uptrend = row['Close'] > sma_50 if sma_50 > 0 else True # Fallback if no SMA yet
        
        is_long = (
            row['RSI'] < 35 and
            row['RSI'] > prev['RSI'] and
            row['Close'] <= row['BB_lower'] and 
            row['ADX'] < 22 and
            is_uptrend
        )
        
        if is_long:
            self.place_long_orders(ctx, symbol, row)

    def place_long_orders(self, ctx: TradingContext, symbol: str, row: pd.Series):
        # Price
        entry_price = row['Close'] # Market order at next Open, essentially.
        atr = row['ATR']
        
        # Sizing (Simple Fixed Risk)
        # Risk 1.5% of Capital
        capital = ctx.capital 
        risk_per_trade = capital * 0.015
        stop_distance = 2 * atr
        
        # Quantity = Risk / Distance
        quantity = risk_per_trade / stop_distance
        
        # Split: E1 50%, E2 30%, E3 20%
        qty_e1 = quantity * 0.50
        qty_e2 = quantity * 0.30
        qty_e3 = quantity * 0.20
        
        # Prices
        p_e1 = entry_price # Market
        p_e2 = entry_price - (0.5 * atr) # Limit
        p_e3 = entry_price - (1.0 * atr) # Limit
        
        sl_price = entry_price - (2.0 * atr) # Initial SL
        
        # LOG SIGNAL (Telegram Style)
        # logger.info(f"SIGNAL LONG {symbol}: ATR={atr:.2f} Qty={quantity:.2f}")
        self.signal_logger.log_signal(
            timestamp=ctx.timestamp,
            symbol=symbol,
            direction="LONG",
            entry_price=entry_price,
            sl_price=sl_price,
            e1_price=p_e1,
            e1_qty=int(qty_e1),
            e2_price=p_e2,
            e2_qty=int(qty_e2),
            e3_price=p_e3,
            e3_qty=int(qty_e3),
            atr=atr,
            notes=f"RSI+BB+ADX. Trend(SMA50)={sma_50:.2f}" if 'sma_50' in locals() else "Trend OK"
        )
        
        # Store metadata for Management (Time Stop / TP)
        # We assume E1 will fill next bar approx.
        self.entry_tracker[symbol] = {
            'entry_time': ctx.timestamp, # Approx, effectively signal time
            'atr': atr,
            'tp1_hit': False,
            'initial_sl': sl_price
        }

        # E1 - Market
        o1 = Order(
            id=f"{symbol}_E1_{ctx.timestamp.timestamp()}",
            symbol=symbol,
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=int(qty_e1), 
            tag="E1"
        )
        ctx.submit_order(o1)
        
        # E2 - Limit
        o2 = Order(
            id=f"{symbol}_E2_{ctx.timestamp.timestamp()}",
            symbol=symbol,
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=int(qty_e2),
            price=p_e2,
            tag="E2"
        )
        ctx.submit_order(o2)
        
        # E3 - Limit 
        o3 = Order(
            id=f"{symbol}_E3_{ctx.timestamp.timestamp()}",
            symbol=symbol,
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=int(qty_e3),
            price=p_e3,
            tag="E3"
        )
        ctx.submit_order(o3)
        
        # Stop Loss (For E1 initially)
        sl_order = Order(
            id=f"{symbol}_SL_{ctx.timestamp.timestamp()}",
            symbol=symbol,
            side=OrderSide.SELL,
            order_type=OrderType.STOP,
            quantity=int(qty_e1),
            stop_price=sl_price,
            tag="SL"
        )
        ctx.submit_order(sl_order)

    def manage_positions(self, ctx: TradingContext):
        # Clean tracker for closed positions
        active_symbols = set(ctx.positions.keys())
        tracked_symbols = list(self.entry_tracker.keys())
        for sym in tracked_symbols:
            if sym not in active_symbols:
                # Position closed ( SL/TP hit )
                # CRITICAL: Cancel any pending orders (E2, E3) to prevent Zombie Re-entries
                for oid, order in list(ctx.active_orders.items()):
                    if order.symbol == sym:
                        logger.info(f"Canceling orphan order {order.tag} for {sym} (Position Closed)")
                        ctx.cancel_order(oid)
                
                # Stop tracking
                del self.entry_tracker[sym]

        for symbol, pos in ctx.positions.items():
            if pos.quantity == 0:
                continue
                
            # Need Metadata
            if symbol not in self.entry_tracker:
                 # Recover state if possible or skip
                 continue
                 
            meta = self.entry_tracker[symbol]
            current_price = ctx.data.get_price(symbol)
            if not current_price:
                continue
                
            # --- 1. SL Resizing (Sync Qty) ---
            sl_order = None
            for o in ctx.active_orders.values():
                if o.symbol == symbol and o.tag == "SL":
                    sl_order = o
                    break
            
            if sl_order:
                # Resize if needed
                if sl_order.quantity != pos.quantity:
                    logger.info(f"Adjusting SL for {symbol}: {sl_order.quantity} -> {pos.quantity}")
                    ctx.cancel_order(sl_order.id)
                    new_sl = Order(
                        id=f"{symbol}_SL_{ctx.timestamp.timestamp()}_UPDATE",
                        symbol=symbol,
                        side=OrderSide.SELL,
                        order_type=OrderType.STOP,
                        quantity=pos.quantity,
                        stop_price=sl_order.stop_price,
                        tag="SL"
                    )
                    ctx.submit_order(new_sl)
                    sl_order = new_sl # Update ref
            
            # --- 2. Take Profit 1 (Move SL to BE) ---
            # TP1 = AvgEntry + 1.5 * ATR
            tp1_price = pos.average_price + (1.5 * meta['atr'])
            
            if not meta['tp1_hit'] and current_price >= tp1_price:
                logger.info(f"TP1 HIT {symbol} ({current_price:.2f} >= {tp1_price:.2f}). Moving SL to BE.")
                meta['tp1_hit'] = True
                
                # Move SL to Average Entry (Break Even)
                if sl_order:
                    ctx.cancel_order(sl_order.id)
                    be_sl = Order(
                        id=f"{symbol}_SL_BE_{ctx.timestamp.timestamp()}",
                        symbol=symbol,
                        side=OrderSide.SELL,
                        order_type=OrderType.STOP,
                        quantity=pos.quantity,
                        stop_price=pos.average_price, # Break Even
                        tag="SL"
                    )
                    ctx.submit_order(be_sl)
            
            # --- 3. Time Stop (48 Hours) ---
            # Close if > 48h and NOT in huge profit? 
            # "Si despues de 48h no se ha alcanzado TP1 ni SL -> Cerrar"
            # If TP1 hit, we don't close by time? Strategy says "TP1 ni SL".
            # So if TP1 hit, we respect the trade.
            
            if not meta['tp1_hit']:
                hours_open = (ctx.timestamp - meta['entry_time']).total_seconds() / 3600
                if hours_open >= 48:
                    logger.info(f"TIME STOP {symbol}: {hours_open:.1f}h. Closing Position.")
                    # Close Market
                    close_order = Order(
                        id=f"{symbol}_TIME_EXIT_{ctx.timestamp.timestamp()}",
                        symbol=symbol,
                        side=OrderSide.SELL,
                        order_type=OrderType.MARKET,
                        quantity=pos.quantity,
                        tag="TIME_STOP"
                    )
                    ctx.submit_order(close_order)
                    
                    # Cancel Pending E2/E3 if any
                    for oid, order in list(ctx.active_orders.items()):
                        if order.symbol == symbol and order.side == OrderSide.BUY:
                            ctx.cancel_order(oid)
                    # Cancel SL
                    if sl_order:
                        ctx.cancel_order(sl_order.id)
