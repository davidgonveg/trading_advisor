import logging
import pandas as pd
from typing import Dict, Any, List, Type, Optional
from backtesting.core.strategy_interface import StrategyInterface, Signal, SignalSide
from backtesting.core.data_loader import DataLoader
from backtesting.core.order_executor import OrderExecutor
from backtesting.core.portfolio import Portfolio
from backtesting.core.schema import Order, OrderSide, OrderType, OrderStatus
from backtesting.core.logger import AuditTrail
from backtesting.core.ml_filter import MLFilter
import uuid
from collections import deque

logger = logging.getLogger("backtesting.core.backtester")

class BacktestEngine:
    def __init__(self, initial_capital: float = 10000.0, commission: float = 0.001, slippage: float = 0.0005, config: Dict[str, Any] = None, timestamp: str = None, symbol: str = "asset", strategy_name: str = "strat"):
        self.initial_capital = initial_capital
        self.portfolio = Portfolio(initial_capital)
        self.executor = OrderExecutor(commission_pct=commission, slippage_pct=slippage)
        self.strategy: Optional[StrategyInterface] = None
        self.data: pd.DataFrame = pd.DataFrame()
        self.symbol = symbol
        self.config = config or {}
        self.audit = AuditTrail(self.config, timestamp or "test", symbol=symbol, strategy=strategy_name)
        self.debug_mode = self.config.get("debug", {}).get("enabled", False)
        self.ml_filter = MLFilter(self.config)
        self.lookback_bars = self.config.get("ml_filter", {}).get("lookback", 5)
        self.indicator_history = deque(maxlen=self.lookback_bars)
        
    def set_strategy(self, strategy: StrategyInterface, params: Dict[str, Any]):
        self.strategy = strategy
        self.strategy.setup(params)
        
    def run(self, symbol: str, data: pd.DataFrame):
        """
        The Main Event Loop. Processes data bar by bar.
        """
        if self.strategy is None:
            raise ValueError("Strategy not set.")
            
        self.symbol = symbol
        self.data = data
        
        # Performance Hook: Strategy Pre-calculation
        if hasattr(self.strategy, "_precompute_indicators"):
            # Ensure strategy knows the symbol for multi-timeframe data loading
            self.strategy.symbol = symbol
            self.strategy._precompute_indicators(data)
            
        logger.info(f"[BACKTEST START] Strategy: {self.strategy.__class__.__name__} | Symbol: {symbol} | Bars: {len(data)}")
        self.audit.set_metadata({
            "strategy": self.strategy.__class__.__name__,
            "symbol": symbol,
            "period": f"{data.index[0]} to {data.index[-1]}",
            "initial_capital": self.initial_capital
        })
        
        # Progress bar (disabled for cleaner logs in parallel runs)
        iterator = range(len(data))
            
        for i in iterator:
            current_bar = data.iloc[i]
            ts = data.index[i]
            
            # 1. PROCESS ORDERS
            trades = self.executor.process_bar(current_bar, symbol)
            for trade in trades:
                self.portfolio.apply_trade(trade)
                self.audit.log_trade(trade.__dict__)
                if self.debug_mode and self.config.get("debug", {}).get("pause_on_trade", True):
                    try:
                        input(f"\n[DEBUG] Trade executed on {ts}. Press Enter to continue...")
                    except EOFError:
                        self.debug_mode = False
                
            # 2. RECORD SNAPSHOT
            self.portfolio.record_snapshot(ts, {symbol: current_bar['Close']})
            
            # 3. STRATEGY STEP
            history = data.iloc[:i+1]
            portfolio_ctx = self.portfolio.get_context()
            
            # Audit bar before signal
            bar_audit = {
                "index": i,
                "timestamp": ts,
                "ohlc": current_bar[['Open', 'High', 'Low', 'Close']].to_dict(),
                "indicators": getattr(self.strategy, 'last_indicators', {}),
                "portfolio_before": portfolio_ctx.copy()
            }
            
            signal = self.strategy.on_bar(history, portfolio_ctx)
            current_indicators = getattr(self.strategy, 'last_indicators', {}).copy()
            bar_audit["indicators"] = current_indicators
            bar_audit["signal"] = signal.side.value if signal else "HOLD"
            
            # 4. HANDLE SIGNAL
            if signal and signal.side != SignalSide.HOLD:
                # ML Filter check (if enabled)
                ml_cfg = self.config.get("ml_filter", {})
                if ml_cfg.get("enabled", False) and self.ml_filter.enabled:
                    # History is currently [t-1, t-2, ... t-N] because we haven't pushed current bar yet
                    prob = self.ml_filter.predict_proba(current_indicators, list(self.indicator_history), self.symbol)
                    threshold = ml_cfg.get("threshold", 0.5)
                    bar_audit["ml_confidence"] = prob
                    
                    if prob < threshold:
                        logger.info(f"[ML FILTER] Signal REJECTED (Confidence: {prob:.2f} < {threshold})")
                        signal = None # Reject signal
                    else:
                        logger.info(f"[ML FILTER] Signal ACCEPTED (Confidence: {prob:.2f} >= {threshold})")

                if signal:
                    logger.info(f"[SIGNAL] {ts} | {signal.side.value} | Tag: {signal.tag}")
                    self._handle_signal(signal, ts, current_bar['Close'])
                    if self.debug_mode and self.config.get("debug", {}).get("pause_on_signal", True):
                        print(f"\n[DEBUG] BAR {i} | {ts} | Close: {current_bar['Close']:.2f}")
                        print(f" INDICATORS: {bar_audit['indicators']}")
                        if "ml_confidence" in bar_audit:
                            print(f" ML CONFIDENCE: {bar_audit['ml_confidence']:.2f}")
                        print(f" PORTFOLIO: Equity ${portfolio_ctx['total_equity']:.2f} | Cash ${portfolio_ctx['cash']:.2f}")
                        
                        try:
                            cmd = input("[DEBUG] Signal generated. Press Enter to continue, 's' to skip debug, 'q' to quit: ")
                            if cmd == 's': self.debug_mode = False
                            if cmd == 'q': break
                        except EOFError:
                            self.debug_mode = False
                    
            # 5. Record context for next bar
            self.indicator_history.appendleft(current_indicators)
            self.audit.log_bar(bar_audit)
                
        logger.info(f"[BACKTEST END] {symbol} finished. Final Equity: ${self.portfolio.equity_curve[-1]['total_equity']:.2f}")
        
        return {
            "trades": self.portfolio.trades,
            "equity_curve": pd.DataFrame(self.portfolio.equity_curve),
            "final_equity": self.portfolio.equity_curve[-1]['total_equity'] if self.portfolio.equity_curve else self.initial_capital,
            "audit": self.audit
        }

    def _handle_signal(self, signal: Signal, timestamp: pd.Timestamp, current_price: float):
        """
        Converts Strategy signals into Broker orders.
        """
        side = OrderSide.BUY if signal.side == SignalSide.BUY else OrderSide.SELL
        current_pos = self.portfolio.positions.get(self.symbol, 0.0)
        
        qty = 0.0
        if signal.quantity is not None:
            qty = abs(signal.quantity)  # Safety: ensure positive
        elif signal.quantity_pct is not None:
            # If closing: use position pct. If opening: use cash pct.
            is_closing = (signal.side == SignalSide.BUY and current_pos < -1e-6) or \
                         (signal.side == SignalSide.SELL and current_pos > 1e-6)
            
            if is_closing:
                # Validate that we actually have a position to close
                if abs(current_pos) < 1e-6:
                    logger.warning(f"[SIGNAL IGNORED] Attempted to close position with zero quantity for {self.symbol}")
                    return
                qty = abs(current_pos * signal.quantity_pct)  # Safety: ensure positive
            else:
                available_cash = self.portfolio.cash * signal.quantity_pct
                if available_cash < 0:
                    logger.warning(f"[ORDER REJECTED] Negative cash: ${available_cash:.2f} for {self.symbol}")
                    return
                qty = (available_cash * 0.99) / current_price 
        else:
            # Default: Close full position or open full potential
            is_closing = (signal.side == SignalSide.BUY and current_pos < -1e-6) or \
                         (signal.side == SignalSide.SELL and current_pos > 1e-6)
            
            if is_closing:
                # Validate that we actually have a position to close
                if abs(current_pos) < 1e-6:
                    logger.warning(f"[SIGNAL IGNORED] Attempted to close position with zero quantity for {self.symbol}")
                    return
                qty = abs(current_pos)
            else:
                if self.portfolio.cash < 0:
                    logger.warning(f"[ORDER REJECTED] Negative cash: ${self.portfolio.cash:.2f} for {self.symbol}")
                    return
                qty = (self.portfolio.cash * 0.99) / current_price
            
        # Final validation with better error messages
        if qty <= 0:
            if qty < 0:
                logger.error(f"[BUG] Negative quantity calculated: {qty:.4f} for {self.symbol} | pos={current_pos:.4f} | cash=${self.portfolio.cash:.2f}")
            else:
                logger.warning(f"[ORDER REJECTED] Zero quantity for {self.symbol} | cash=${self.portfolio.cash:.2f} | price=${current_price:.2f}")
            return
        
        # Safety: ensure qty is always positive
        qty = abs(qty)

        order = Order(
            id=str(uuid.uuid4())[:8],
            symbol=self.symbol,
            side=side,
            order_type=OrderType.MARKET,
            quantity=round(qty, 4), # Professional rounding
            timestamp=timestamp,
            tag=signal.tag
        )
        
        self.executor.submit_order(order)
        
        if signal.stop_loss:
            sl_order = Order(
                id=f"SL-{order.id}",
                symbol=self.symbol,
                side=OrderSide.SELL if side == OrderSide.BUY else OrderSide.BUY,
                order_type=OrderType.STOP,
                stop_price=signal.stop_loss,
                quantity=order.quantity,
                timestamp=timestamp,
                tag=f"{signal.tag}_SL" if signal.tag else "SL"
            )
            self.executor.submit_order(sl_order)
            
        if signal.take_profit:
            tp_order = Order(
                id=f"TP-{order.id}",
                symbol=self.symbol,
                side=OrderSide.SELL if side == OrderSide.BUY else OrderSide.BUY,
                order_type=OrderType.LIMIT,
                price=signal.take_profit,
                quantity=order.quantity,
                timestamp=timestamp,
                tag=f"{signal.tag}_TP" if signal.tag else "TP"
            )
            self.executor.submit_order(tp_order)
