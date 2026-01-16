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
        
        # SMA 200 Check (Trend Filter v3.1)
        daily_stats = ctx.data.daily_indicators.get(symbol, {})
        sma_200 = daily_stats.get('SMA_200', 0.0)
        
        is_uptrend = row['Close'] > sma_200 if sma_200 > 0 else True # Fallback
        
        # Calculate Volume Mult based on ADX (v3.1)
        
        # Calculate Volume Mult based on ADX (v3.1)
        adx_val = row['ADX']
        vol_mult = 1.0
        if adx_val < 20: vol_mult = 1.0
        elif adx_val < 30: vol_mult = 1.2
        else: vol_mult = 1.5
        
        vol_ok = row['Volume'] > (row.get('Volume_SMA_20', 0) * vol_mult)
        
        is_long = (
            row['CRSI'] < self.cfg['CRSI_OVERSOLD'] and
            # row['CRSI'] > prev['CRSI'] and # Turn removed in v3.1 simplification
            row['Close'] <= row['BB_Lower'] and 
            # row['ADX'] < self.cfg['ADX_MAX_THRESHOLD'] and # Removed strict ADX max, replaced by regime vol check
            is_uptrend and
            vol_ok
        )
        
        if is_long:
            self.place_long_orders(ctx, symbol, row)
        else:

            # DEBUG: Log near-misses
            if row['CRSI'] < 25:
                # logger.debug is not standard python logging level without setup, usually use info or debug
                logger.info(
                    f"{symbol} REJECT: CRSI={row['CRSI']:.1f}/{self.cfg['CRSI_OVERSOLD']}, "
                    f"BB_Cond={row['Close'] <= row['BB_Lower']}, "
                    f"ADX={row['ADX']:.1f}, VolOK={vol_ok}, Trend={is_uptrend}"
                )

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
        
        # v3.1 Fixed Take Profits (calculated at Entry)
        # TP1: BB Middle
        # TP2: BB Upper (Opposite)
        tp1_price = row['BB_Middle']
        tp2_price = row['BB_Upper']
        
        # If BB Middle is below entry (impossible for Long at Lower Band usually, but check), clamp?
        # Typically Entry <= Lower Band < Middle Band < Upper Band.
        # So TP1 > Entry. Correct.
        
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

            notes=f"CRSI={row['CRSI']:.1f}. Trend(SMA200)={sma_200:.2f}" if 'sma_200' in locals() else "Trend OK"
        )
        
        # Store metadata for Management (Time Stop / TP)
        # v3.1: Store Fixed TP levels
        self.entry_tracker[symbol] = {
            'entry_time': ctx.timestamp,
            'atr': atr,
            'adx_entry': row['ADX'],
            'tp1_hit': False,
            'tp2_hit': False,
            'tp1_price': tp1_price,
            'tp2_price': tp2_price,
            'initial_sl': sl_price
        }

        # E1 - Limit (v3.1 Fix: Avoid paying above TP if gap up)
        o1 = Order(
            id=f"{symbol}_E1_{ctx.timestamp.timestamp()}",
            symbol=symbol,
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            price=p_e1,
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
            pos = ctx.positions.get(sym)
            is_in_position = (pos is not None and pos.quantity > 0)
            
            # Check for Pending E1 (Waiting for Entry)
            has_pending_e1 = False
            for order in ctx.active_orders.values():
                if order.symbol == sym and order.tag == "E1":
                    has_pending_e1 = True
                    break

            # 1. CLEANUP ORPHAN ORDERS (Zombie protection)
            # Only cleanup if NO Position AND NO Pending E1
            if not is_in_position and not has_pending_e1:
                # Position closed ( SL/TP hit )
                # Cancel any pending orders (E2, E3) to prevent Zombie Re-entries
                for oid, order in list(ctx.active_orders.items()):
                    if order.symbol == sym:
                        logger.info(f"Canceling orphan order {order.tag} for {sym} (Position Closed)")
                        ctx.cancel_order(oid)
                # Stop tracking
                del self.entry_tracker[sym]
                continue

            # 2. MANAGE ACTIVE TRADE / PENDING ENTRY
            # Use 'entry_tracker' meta for timeouts/cancellation rules
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
            
            # Rule 4.3.1: ADX Spike > 3 pts -> Cancel E3 (unchanged)
            if current_adx > (meta['adx_entry'] + self.cfg['ADX_CANCEL_THRESHOLD']):
                cancel_e3 = True
                
            # Rule 4.3.2: Timeout 4h for E2/E3 (Pending Limit Orders) (unchanged)
            if time_since_entry >= self.cfg['ENTRY_TIMEOUT_HOURS']:
                cancel_all_pending = True
                
            # Rule 4.3.3: TP1 Hit -> Cancel pending (don't average down if winning)
            if meta['tp1_hit']:
                cancel_all_pending = True

            # v3.1 NEW CANCELLATION RULES
            # 1. Alivio estadistico: CRSI > 25 (Long)
            # 2. Reversion inicial: Close > BB Middle
            
            # Use df_curr last row
            if not df_curr.empty:
                # v3.1 CRITICAL FIX: Must calculate indicators to check CRSI/BB
                try:
                    df_curr = IndicatorCalculator.calculate(df_curr)
                except Exception as e:
                    logger.error(f"Indicator Calc Error {sym}: {e}")
                    continue

                last_row = df_curr.iloc[-1]
                # if last_row.get('CRSI', 50) > 25: # v3.1 CRSI Exit Long threshold (Safe get)
                #     cancel_all_pending = True
                #     logger.info(f"Smart Cancel {sym}: CRSI > 25")
                    
                # if last_row['Close'] > last_row['BB_Middle']:
                #      cancel_all_pending = True
                #      logger.info(f"Smart Cancel {sym}: Price > BB Middle")

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
            # Only resize SL if we have an active position
            if is_in_position:
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
            
            # --- 4. TAKE PROFIT LOGIC (v3.1 FIXED) ---
            
            # TP1: Fixed Price at Entry (BB Middle)
            tp1_target = meta['tp1_price']
            # TP2: Fixed Price at Entry (BB Upper)
            tp2_target = meta['tp2_price']
            
            # Check TP1 (Only if in position)
            if is_in_position and not meta['tp1_hit'] and current_price >= tp1_target:
                logger.info(f"TP1 HIT {sym} ({current_price:.2f} >= {tp1_target:.2f}). EXIT 60%. Mov SL BE.")
                meta['tp1_hit'] = True
                
                # Execute Partial Exit (60% of CURRENT Position) -> Strategy says "60%".
                # If we have 10 shares, close 6.
                qty_to_close = int(pos.quantity * 0.60)
                if qty_to_close > 0:
                    exit_order = Order(
                        id=f"{sym}_TP1_{ctx.timestamp.timestamp()}",
                        symbol=sym,
                        side=OrderSide.SELL,
                        order_type=OrderType.MARKET, # Simulating Limit Fill
                        quantity=qty_to_close,
                        tag="TP1"
                    )
                    ctx.submit_order(exit_order)
                
                # Move remaining SL to Breakeven
                if sl_order:
                    ctx.cancel_order(sl_order.id)
                    be_sl = Order(
                        id=f"{sym}_SL_BE_{ctx.timestamp.timestamp()}",
                        symbol=sym,
                        side=OrderSide.SELL,
                        order_type=OrderType.STOP,
                        quantity=pos.quantity - qty_to_close, # Remaining
                        stop_price=pos.average_price, # Break Even
                        tag="SL"
                    )
                    ctx.submit_order(be_sl)
                    sl_order = be_sl

            # Check TP2 (Close Remainder)
            if not meta.get('tp2_hit', False) and current_price >= tp2_target:
                logger.info(f"TP2 HIT {sym} ({current_price:.2f} >= {tp2_target:.2f}). EXIT ALL.")
                meta['tp2_hit'] = True
                
                # Close All
                close_order = Order(
                    id=f"{sym}_TP2_{ctx.timestamp.timestamp()}",
                    symbol=sym,
                    side=OrderSide.SELL,
                    order_type=OrderType.MARKET,
                    quantity=pos.quantity, # Close remaining
                    tag="TP2"
                )
                ctx.submit_order(close_order)
                
                # Cancel SL
                if sl_order:
                    ctx.cancel_order(sl_order.id)

            # --- 5. TIME STOP (5 Days / 120 Hours) ---
            # Only if not in "winner mode" (TP1 hit)? Strategy says "Si TP1 ni SL alcanzado". 
            # So if TP1 hit, we respect it.
            if not meta['tp1_hit']:
                if time_since_entry >= self.cfg['TIME_STOP_HOURS']:
                    # Check if we already have a pending TIME_EXIT order
                    pending_exit = None
                    for o in ctx.active_orders.values():
                        if o.symbol == sym and o.tag == "TIME_STOP":
                            pending_exit = o
                            break
                    
                    if pending_exit:
                         # Already trying to close, do nothing (wait for fill)
                         logger.info(f"Waiting for TIME STOP fill for {sym}...")
                    else:
                        logger.info(f"TIME STOP {sym}: {time_since_entry:.1f}h. Closing Position.")
                        
                        # CRITICAL: Cancel ALL other pending orders FIRST to free up margin/state
                        # This prevents "Margin Call" on the Sell order if broker is strict, 
                        # and ensures we don't have dangling orders.
                        for oid, order in list(ctx.active_orders.items()):
                            if order.symbol == sym:
                                logger.info(f"Canceling {order.tag} to force TIME EXIT for {sym}")
                                ctx.cancel_order(oid)
                        
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
