import pandas as pd
import logging
from typing import Dict, List
from datetime import timedelta

from analysis.scanner import Scanner
from analysis.risk import RiskManager
from analysis.indicators import TechnicalIndicators
from analysis.signal import Signal
from trading.manager import TradeManager, TradePlan
from backtesting.account import Account

logger = logging.getLogger("core.backtesting.engine")

class BacktestEngine:
    def __init__(self, initial_capital: float = 10000.0):
        self.account = Account(initial_capital)
        self.scanner = Scanner()
        self.indicators = TechnicalIndicators()
        self.risk_manager = RiskManager()
        self.trade_manager = TradeManager()
        
        # Data
        self.market_data: Dict[str, pd.DataFrame] = {}
        self.daily_data: Dict[str, pd.DataFrame] = {}
        
    def load_data(self, data_map: Dict[str, pd.DataFrame]):
        """Load 1H data"""
        self.market_data = data_map

    def load_daily_data(self, daily_map: Dict[str, pd.DataFrame]):
        """Load Daily data"""
        self.daily_data = daily_map

    def run(self, start_date=None, end_date=None, data_manager=None):
        """
        Main Event Loop.
        1. Pre-Scan all signals (Optimization: Instead of scanning every hour, scan full DF first).
        2. Iterate timestamps.
        """
        logger.info("Starting Backtest...")
        
        # 1. Generate Signals for all symbols
        all_signals: List[Signal] = []
        
        for symbol, df_raw in self.market_data.items():
            logger.info(f"Scanning {symbol}...")
            
            # Fetch Daily Data for this symbol
            df_daily = self.daily_data.get(symbol, pd.DataFrame())
            
            # CALCULATE INDICATORS
            # The Scanner expects a DataFrame with columns: RSI, ADX, BB_*, etc.
            # We calculate them on the full dataset at once (vectorized) for speed
            try:
                df = self.indicators.calculate_all(df_raw)
                # Update market data with analyzed version so 'process_candle' has access if needed?
                # Actually process_candle uses OHLC which are preserved.
                self.market_data[symbol] = df # Save back
            except Exception as e:
                logger.error(f"Failed to calculate indicators for {symbol}: {e}")
                continue

            # Run Scanner
            try:
                # Passing df_daily for SMA trend filter
                signals = self.scanner.find_signals(symbol, df, df_daily) 
                all_signals.extend(signals)
            except Exception as e:
                logger.error(f"Failed to scan {symbol}: {e}")
                # import traceback
                # logger.error(traceback.format_exc())
            
        # Sort signals by time
        all_signals.sort(key=lambda s: s.timestamp)
        logger.info(f"Generated {len(all_signals)} potential signals.")
        
        if not all_signals:
            logger.warning("No signals found. Check preconditions or data.")
            return

        # 2. Setup Timeline
        # Merge all indices to get master timeline
        all_indices = [df.index for df in self.market_data.values()]
        if not all_indices:
            full_timeline = pd.DatetimeIndex([])
        else:
            from functools import reduce
            full_timeline = reduce(lambda x, y: x.union(y), all_indices).sort_values().unique()
        
        # 3. Event Loop
        signal_idx = 0
        
        for timestamp in full_timeline:
            # A. Update Market Data for ALL symbols (Process pending orders)
            for symbol, df in self.market_data.items():
                if timestamp in df.index:
                    row = df.loc[timestamp]
                    self.account.process_candle(
                        symbol, timestamp, 
                        row['Open'], row['High'], row['Low'], row['Close']
                    )

            # B. Process Signals at this timestamp
            # (Signal timestamp usually means "Close of candle when signal appeared")
            # We assume we can trade at NEXT Open (which is processed in next loop step?)
            # Or we place orders NOW to be filled NEXT.
            
            while signal_idx < len(all_signals) and all_signals[signal_idx].timestamp <= timestamp:
                sig = all_signals[signal_idx]
                signal_idx += 1
                
                if sig.timestamp < timestamp:
                    continue # Skip old signals
                
                # Check Constraints
                # Max 4 Positions
                if len(self.account.positions) >= 4:
                    continue
                
                if sig.symbol in self.account.positions:
                    continue # Already in position
                
                try:
                    # Sizing
                    capital = self.account.get_available_capital()
                    # Risk Logic: size is quantity
                    # self.risk_manager.calculate_size(price, atr, capital)
                    size_qty = self.risk_manager.calculate_size(
                        sig.price, sig.atr_value, capital
                    )
                    
                    if size_qty <= 0:
                        continue
                        
                    # Create Plan
                    plan = self.trade_manager.create_trade_plan(sig, size_qty)
                    
                    # Submit Entry Orders
                    for order in plan.entry_orders:
                        self.account.submit_order(order)
                    
                    # Submit Stop Loss Order
                    logger.info(f"[SL] Submitting SL order for {sig.symbol}: {plan.stop_loss_order.side} @ {plan.stop_loss_order.price:.2f} (qty: {plan.stop_loss_order.quantity})")
                    self.account.submit_order(plan.stop_loss_order)
                    
                    # Submit Take Profit Orders
                    for tp_order in plan.take_profits:
                        logger.info(f"[TP] Submitting TP order for {sig.symbol}: {tp_order.tag} @ {tp_order.price:.2f} (qty: {tp_order.quantity})")
                        self.account.submit_order(tp_order)
                except Exception as e:
                    logger.error(f"SKIPPING SIGNAL {sig.symbol} at {sig.timestamp} due to error: {e}")
                    continue
                    
        # End
        logger.info(f"Backtest Finished. Equity: {self.account.equity:.2f}")
        return self.make_report()

    def make_report(self):
        return {
            "final_equity": self.account.equity,
            "trades": self.account.closed_trades,
            "positions": self.account.positions
        }
