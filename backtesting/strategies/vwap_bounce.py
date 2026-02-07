from backtesting.core.strategy_interface import StrategyInterface, Signal, SignalSide
import pandas as pd
import numpy as np
import logging
from typing import Dict, Any, List

# Shared Core Logic
from analysis.indicators import TechnicalIndicators
from analysis.patterns import PatternRecognizer
from analysis.logic import check_vwap_bounce
from analysis.signal import SignalType

logger = logging.getLogger("backtesting.strategies.vwap_bounce")

class VWAPBounce(StrategyInterface):
    def setup(self, params: Dict[str, Any]):
        self.risk_pct = params.get("risk_pct", 0.015)
        self.vol_sma_period = params.get("volume_sma", 20)
        
        # ATR Parameters
        self.atr_period = params.get("atr_period", 14)
        self.atr_multiplier_sl = params.get("atr_multiplier_sl", 2.0)
        self.atr_multiplier_tp = params.get("atr_multiplier_tp", 4.0)
        
        # Optimization Parameters (Exposed)
        self.wick_ratio = params.get("wick_ratio", 2.0)
        self.time_stop_hours = params.get("time_stop_hours", 8)
        self.vol_mult = params.get("vol_mult", 1.0)
        
        # New Filters (Toggleable)
        self.use_rsi_filter = params.get("use_rsi_filter", False)
        self.rsi_threshold_long = params.get("rsi_threshold_long", 70)  # max RSI for long
        self.rsi_threshold_short = params.get("rsi_threshold_short", 30) # min RSI for short
        
        self.use_trend_filter = params.get("use_trend_filter", False) # Trade only with trend (EMA200)
        
        self.params = params
        self.indicators_df = None
        
        # Tools
        self.tech_indicators = TechnicalIndicators()
        self.pattern_recognizer = PatternRecognizer()
        
        # State tracking
        self.entry_price = 0.0
        self.sl_price = 0.0
        self.tp_price = 0.0
        self.active_side = None # 'LONG' or 'SHORT'
        self.entry_ts = None
        self.symbol = "asset"
        self.last_indicators = {}

    def get_params(self) -> Dict[str, Any]:
        return self.params

    def _precompute_indicators(self, data: pd.DataFrame):
        """
        Uses the shared TechnicalIndicators and PatternRecognizer to generate features.
        """
        if data.empty:
            return

        # 1. Calculate Standard Indicators
        df = self.tech_indicators.calculate_all(data)
        
        # 2. Calculate Patterns (Wicks, Hammer, etc)
        df = self.pattern_recognizer.detect_patterns(df)
        
        # 3. Add any strategy-specific legacy derivations if not present
        if 'Dist_EMA200' not in df.columns and 'EMA_200' in df.columns:
            df['Dist_EMA200'] = (df['Close'] - df['EMA_200']) / df['EMA_200']
            
        self.indicators_df = df
        logger.info(f"Precomputed indicators for {self.symbol}: {len(df)} rows.")

    def on_bar(self, history: pd.DataFrame, portfolio_context: Dict[str, Any]) -> Signal:
        # Safety check
        if self.indicators_df is None or history.empty:
            return Signal(SignalSide.HOLD)

        bar = history.iloc[-1]
        ts = bar.name
        
        # Access precomputed indicators safely
        if ts not in self.indicators_df.index:
            return Signal(SignalSide.HOLD)

        ind = self.indicators_df.loc[ts]
        if isinstance(ind, pd.DataFrame):
            ind = ind.iloc[0] 

        # Map to internally used variables needed for management
        vwap = ind.get('VWAP')
        vol_sma = ind.get('Volume_SMA_20', ind.get('Vol_SMA', 0))
        atr = ind.get('ATR', 0)
        
        # Update Last Indicators for Audit/UI
        self.last_indicators = {
            "VWAP": round(vwap, 2) if vwap else 0,
            "Volume_SMA": round(vol_sma, 0),
            "ATR": round(atr, 2),
            "Close": round(bar['Close'], 2)
        }
        
        # Get position
        pos_qty = portfolio_context["positions"].get(self.symbol, 0.0)
        
        # --- MANAGEMENT LOGIC ---
        if abs(pos_qty) > 1e-6:
            current_price = bar['Close']
            
            # SL/TP/VWAP/Time Exits
            if self.active_side == 'LONG':
                if current_price <= self.sl_price:
                    self._reset_state()
                    return Signal(SignalSide.SELL, quantity_pct=1.0, tag="SL_EXIT")
                if current_price >= self.tp_price:
                    self._reset_state()
                    return Signal(SignalSide.SELL, quantity_pct=1.0, tag="TP_EXIT")
                if vwap and current_price < vwap:
                    self._reset_state()
                    return Signal(SignalSide.SELL, quantity_pct=1.0, tag="VWAP_EXIT")

            elif self.active_side == 'SHORT':
                if current_price >= self.sl_price:
                    self._reset_state()
                    return Signal(SignalSide.BUY, quantity_pct=1.0, tag="SL_EXIT")
                if current_price <= self.tp_price:
                    self._reset_state()
                    return Signal(SignalSide.BUY, quantity_pct=1.0, tag="TP_EXIT")
                if vwap and current_price > vwap:
                    self._reset_state()
                    return Signal(SignalSide.BUY, quantity_pct=1.0, tag="VWAP_EXIT")
            
            # Time Stop
            if self.entry_ts:
                duration = (ts - self.entry_ts).total_seconds() / 3600
                if duration >= self.time_stop_hours:
                    exit_side = SignalSide.SELL if self.active_side == 'LONG' else SignalSide.BUY
                    self._reset_state()
                    return Signal(exit_side, quantity_pct=1.0, tag="TIME_STOP_EXIT")
            
            # Session Close
            if self.is_market_closing_soon(ts):
                exit_side = SignalSide.SELL if self.active_side == 'LONG' else SignalSide.BUY
                self._reset_state()
                return Signal(exit_side, quantity_pct=1.0, tag="SESSION_CLOSE_EXIT")

        # --- ENTRY LOGIC (Via Shared Library) ---
        if abs(pos_qty) < 1e-6:
            # Check shared logic
            signal_type = check_vwap_bounce(ind, self.params)
            
            if signal_type == SignalType.LONG:
                if pd.isna(atr) or atr == 0: return Signal(SignalSide.HOLD)
                
                self.entry_price = bar['Close']
                self.active_side = 'LONG'
                self.entry_ts = ts
                risk_distance = atr * self.atr_multiplier_sl
                self.sl_price = self.entry_price - risk_distance
                self.tp_price = self.entry_price + (atr * self.atr_multiplier_tp)
                
                if risk_distance == 0: return Signal(SignalSide.HOLD)
                
                qty = (portfolio_context["total_equity"] * self.risk_pct) / risk_distance
                return Signal(SignalSide.BUY, quantity=qty, tag="VWAP_BOUNCE_LONG", metadata={'sl': self.sl_price, 'tp': self.tp_price})

            elif signal_type == SignalType.SHORT:
                if pd.isna(atr) or atr == 0: return Signal(SignalSide.HOLD)
                
                self.entry_price = bar['Close']
                self.active_side = 'SHORT'
                self.entry_ts = ts
                risk_distance = atr * self.atr_multiplier_sl
                self.sl_price = self.entry_price + risk_distance
                self.tp_price = self.entry_price - (atr * self.atr_multiplier_tp)
                
                if risk_distance == 0: return Signal(SignalSide.HOLD)
                
                qty = (portfolio_context["total_equity"] * self.risk_pct) / risk_distance
                return Signal(SignalSide.SELL, quantity=qty, tag="VWAP_BOUNCE_SHORT", metadata={'sl': self.sl_price, 'tp': self.tp_price})

        return Signal(SignalSide.HOLD)

    def _reset_state(self):
        self.entry_price = 0.0
        self.sl_price = 0.0
        self.tp_price = 0.0
        self.active_side = None
        self.entry_ts = None

    def is_market_closing_soon(self, ts: pd.Timestamp) -> bool:
        """Helper to identify EOD in NY time."""
        try:
            ny_ts = ts.tz_convert('America/New_York')
            if ny_ts.weekday() >= 5: return False
            if ny_ts.hour == 15 and ny_ts.minute >= 50: return True
            if ny_ts.hour >= 16: return True
            return False
        except:
            return False
