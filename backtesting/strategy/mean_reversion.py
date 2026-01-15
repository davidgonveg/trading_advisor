import logging
import pandas as pd
from datetime import timedelta

from config.settings import STRATEGY_CONFIG, RISK_CONFIG
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
        # Merge Strategy and Risk Configs for easier access
        self.cfg = {**STRATEGY_CONFIG, **RISK_CONFIG}
        
    def execute(self, ctx: TradingContext):
        # 1. Manage Existing Positions & Orders (and Timeouts)
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
        # 4. ADX < 20 (v2.0)
        
        # SMA 50 Check (Trend Filter)
        daily_stats = ctx.data.daily_indicators.get(symbol, {})
        sma_50 = daily_stats.get('SMA_50', 0.0)
        
        is_uptrend = row['Close'] > sma_50 if sma_50 > 0 else True # Fallback if no SMA yet
        
        is_long = (
            row['RSI'] < self.cfg['RSI_OVERSOLD'] and
            row['RSI'] > prev['RSI'] and
            row['Close'] <= row['BB_lower'] and 
            row['ADX'] < self.cfg['ADX_MAX_THRESHOLD'] and
            is_uptrend
        )
        
        if is_long:
            self.place_long_orders(ctx, symbol, row)

    def place_long_orders(self, ctx: TradingContext, symbol: str, row: pd.Series):
        # Price
        entry_price = row['Close'] # Market order at next Open, essentially.
        atr = row['ATR']
        
        # Sizing (Simple Fixed Risk)
        # Risk 1.5% of Equity (Total Account Value, NOT just available cash)
        capital = ctx.equity 
        risk_per_trade = capital * (self.cfg['RISK_PER_TRADE_PCT'] / 100.0)
        stop_distance = self.cfg['SL_ATR_MULT'] * atr
        
        # Quantity = Risk / Distance
        quantity = risk_per_trade / stop_distance
        
        # Split: E1 50%, E2 30%, E3 20%
        qty_e1 = quantity * 0.50
        qty_e2 = quantity * 0.30
        qty_e3 = quantity * 0.20
        
        # Prices
        p_e1 = entry_price # Market
        p_e2 = entry_price - (self.cfg['ENTRY_2_ATR_DIST'] * atr) # Limit
        p_e3 = entry_price - (self.cfg['ENTRY_3_ATR_DIST'] * atr) # Limit
        
        sl_price = entry_price - stop_distance # Initial SL
        
        # LOG SIGNAL (Telegram Style)
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
            'entry_time': ctx.timestamp,
            'atr': atr,
            'adx_entry': row['ADX'],
            'tp1_hit': False,
            'tp2_hit': False,
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
            # 1. CLEANUP ORPHAN ORDERS (Zombie protection)
            if sym not in active_symbols:
                # Position closed ( SL/TP hit )
                # Cancel any pending orders (E2, E3) to prevent Zombie Re-entries
                for oid, order in list(ctx.active_orders.items()):
                    if order.symbol == sym:
                        logger.info(f"Canceling orphan order {order.tag} for {sym} (Position Closed)")
                        ctx.cancel_order(oid)
                # Stop tracking
                del self.entry_tracker[sym]
                continue

            # 2. MANAGE ACTIVE TRADE
            pos = ctx.positions[sym]
            if pos.quantity == 0: continue
            
            meta = self.entry_tracker[sym]
            current_price = ctx.data.get_price(sym)
            if not current_price: continue
            
            # --- GLOBAL CHECKS FOR PENDING ORDERS (E2/E3) ---
            # Timeout & ADX Cancellation
            time_since_entry = (ctx.timestamp - meta['entry_time']).total_seconds() / 3600
            
            # Get current ADX
            df_curr = self.get_history_df(sym)
            current_adx = df_curr['ADX'].iloc[-1] if not df_curr.empty and 'ADX' in df_curr else 0
            
            cancel_e3 = False
            cancel_all_pending = False
            
            # Rule 4.3.1: ADX Spike > 3 pts -> Cancel E3
            if current_adx > (meta['adx_entry'] + self.cfg['ADX_CANCEL_THRESHOLD']):
                cancel_e3 = True
                
            # Rule 4.3.2: Timeout 4h for E2/E3 (Pending Limit Orders)
            if time_since_entry >= self.cfg['ENTRY_TIMEOUT_HOURS']:
                cancel_all_pending = True
                
            # Rule 4.3.3: TP1 Hit -> Cancel pending (don't average down if winning)
            if meta['tp1_hit']:
                cancel_all_pending = True

            # EXECUTE CANCELLATIONS
            for oid, order in list(ctx.active_orders.items()):
                if order.symbol == sym and order.side == OrderSide.BUY and order.order_type == OrderType.LIMIT:
                     should_cancel = False
                     if cancel_all_pending:
                         should_cancel = True
                     elif cancel_e3 and order.tag == "E3":
                         should_cancel = True
                         
                     if should_cancel:
                         logger.info(f"CANCELING Pending Order {order.tag} for {sym}. Reason: Timeout/ADX/TP1")
                         ctx.cancel_order(oid)

            # --- 3. SL RESIZING (Sync Qty) ---
            sl_order = None
            for o in ctx.active_orders.values():
                if o.symbol == sym and o.tag == "SL":
                    sl_order = o
                    break
            
            if sl_order:
                if sl_order.quantity != pos.quantity:
                    logger.info(f"Adjusting SL for {sym}: {sl_order.quantity} -> {pos.quantity}")
                    ctx.cancel_order(sl_order.id)
                    new_sl = Order(
                        id=f"{sym}_SL_{ctx.timestamp.timestamp()}_UPDATE",
                        symbol=sym,
                        side=OrderSide.SELL,
                        order_type=OrderType.STOP,
                        quantity=pos.quantity,
                        stop_price=sl_order.stop_price,
                        tag="SL"
                    )
                    ctx.submit_order(new_sl)
                    sl_order = new_sl # Update ref
            
            # --- 4. TAKE PROFIT LOGIC ---
            
            # TP1: AvgEntry + 1.5 * ATR
            tp1_target = pos.average_price + (self.cfg['TP1_ATR_MULT'] * meta['atr'])
            # TP2: AvgEntry + 2.5 * ATR
            tp2_target = pos.average_price + (self.cfg['TP2_ATR_MULT'] * meta['atr'])
            
            # Check TP1
            if not meta['tp1_hit'] and current_price >= tp1_target:
                logger.info(f"TP1 HIT {sym} ({current_price:.2f} >= {tp1_target:.2f}). Moving SL to BE.")
                meta['tp1_hit'] = True
                if sl_order:
                    ctx.cancel_order(sl_order.id)
                    be_sl = Order(
                        id=f"{sym}_SL_BE_{ctx.timestamp.timestamp()}",
                        symbol=sym,
                        side=OrderSide.SELL,
                        order_type=OrderType.STOP,
                        quantity=pos.quantity,
                        stop_price=pos.average_price, # Break Even
                        tag="SL"
                    )
                    ctx.submit_order(be_sl)
                    sl_order = be_sl

            # Check TP2 (New v2.0 Logic: SL to 0.3 ATR locked gain)
            if not meta.get('tp2_hit', False) and current_price >= tp2_target:
                logger.info(f"TP2 HIT {sym} ({current_price:.2f} >= {tp2_target:.2f}). Locking Profit.")
                meta['tp2_hit'] = True
                
                secure_price = pos.average_price + (self.cfg['SL_SECURE_ATR'] * meta['atr'])
                
                if sl_order:
                    ctx.cancel_order(sl_order.id)
                    secure_sl = Order(
                        id=f"{sym}_SL_SECURE_{ctx.timestamp.timestamp()}",
                        symbol=sym,
                        side=OrderSide.SELL,
                        order_type=OrderType.STOP,
                        quantity=pos.quantity,
                        stop_price=secure_price, # Locked Profit
                        tag="SL"
                    )
                    ctx.submit_order(secure_sl)
                    sl_order = secure_sl

            # --- 5. TIME STOP (48 Hours) ---
            # Only if not in "winner mode" (TP1 hit)? Strategy says "Si TP1 ni SL alcanzado". 
            # So if TP1 hit, we respect it.
            if not meta['tp1_hit']:
                if time_since_entry >= self.cfg['TIME_STOP_HOURS']:
                    logger.info(f"TIME STOP {sym}: {time_since_entry:.1f}h. Closing Position.")
                    # Close Market
                    close_order = Order(
                        id=f"{sym}_TIME_EXIT_{ctx.timestamp.timestamp()}",
                        symbol=sym,
                        side=OrderSide.SELL,
                        order_type=OrderType.MARKET,
                        quantity=pos.quantity,
                        tag="TIME_STOP"
                    )
                    ctx.submit_order(close_order)
                    
                    # Cancel all pending
                    for oid, order in list(ctx.active_orders.items()):
                        if order.symbol == sym:
                            ctx.cancel_order(oid)
