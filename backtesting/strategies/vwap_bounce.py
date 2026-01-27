from backtesting.core.strategy_interface import StrategyInterface, Signal, SignalSide
import pandas as pd
import numpy as np
from typing import Dict, Any, List

class VWAPBounce(StrategyInterface):
    def setup(self, params: Dict[str, Any]):
        self.risk_pct = params.get("risk_pct", 0.015)
        self.vol_sma_period = params.get("volume_sma", 20)
        
        # ATR Parameters
        self.atr_period = params.get("atr_period", 14)
        self.atr_multiplier_sl = params.get("atr_multiplier_sl", 2.0)
        self.atr_multiplier_tp = params.get("atr_multiplier_tp", 4.0)
        
        self.params = params
        self.indicators_df = None
        
        # State tracking for the current trade
        self.entry_price = 0.0
        self.sl_price = 0.0
        self.tp_price = 0.0
        self.active_side = None # 'LONG' or 'SHORT'
        self.entry_ts = None

        self.last_indicators = {}
        self.symbol = "asset"

    def get_params(self) -> Dict[str, Any]:
        return self.params

    def _precompute_indicators(self, data: pd.DataFrame):
        """Vectorized pre-calculation of all necessary indicators including ATR."""
        # 1. VWAP (NY Reset)
        ny_index = data.index.tz_convert('America/New_York')
        
        # Typical Price
        tp = (data['High'] + data['Low'] + data['Close']) / 3
        v = data['Volume']
        
        # Calculate daily cumulative sums
        vwap = (tp * v).groupby(ny_index.date).cumsum() / v.groupby(ny_index.date).cumsum()
        
        # 2. Volume SMA
        vol_sma = data['Volume'].rolling(window=self.vol_sma_period).mean()
        
        # 3. Candle Patterns (for logic)
        body = (data['Close'] - data['Open']).abs()
        lower_wick = data[['Open', 'Close']].min(axis=1) - data['Low']
        upper_wick = data['High'] - data[['Open', 'Close']].max(axis=1)
        
        # 4. ATR (Average True Range)
        high_low = data['High'] - data['Low']
        high_close = (data['High'] - data['Close'].shift()).abs()
        low_close = (data['Low'] - data['Close'].shift()).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        atr = tr.rolling(window=self.atr_period).mean()
        
        self.indicators_df = pd.DataFrame({
            'VWAP': vwap,
            'Vol_SMA': vol_sma,
            'Body': body,
            'LowerWick': lower_wick,
            'UpperWick': upper_wick,
            'ATR': atr
        }, index=data.index)

    def on_bar(self, history: pd.DataFrame, portfolio_context: Dict[str, Any]) -> Signal:
        bar = history.iloc[-1]
        ts = bar.name
        
        # Access precomputed indicators
        ind = self.indicators_df.loc[ts]
        if isinstance(ind, pd.DataFrame):
            ind = ind.iloc[0] # Handle duplicates by taking first match
            
        vwap = ind['VWAP']
        vol_sma = ind['Vol_SMA']
        body = ind['Body']
        lower_wick = ind['LowerWick']
        upper_wick = ind['UpperWick']
        atr = ind['ATR']
        
        self.last_indicators = {
            "VWAP": round(vwap, 2),
            "Volume_SMA": round(vol_sma, 0),
            "ATR": round(atr, 2),
            "LowerWick": round(lower_wick, 2),
            "UpperWick": round(upper_wick, 2)
        }
        
        # Get position for THIS symbol
        pos_qty = portfolio_context["positions"].get(self.symbol, 0.0)
        
        # --- MANAGEMENT LOGIC (If in a trade) ---
        if abs(pos_qty) > 1e-6:
            current_price = bar['Close']
            
            if self.active_side == 'LONG':
                # 1. SL Check
                if current_price <= self.sl_price:
                    self._reset_state()
                    return Signal(SignalSide.SELL, quantity_pct=1.0, tag="SL_EXIT")
                
                # 2. TP Check
                if current_price >= self.tp_price:
                    self._reset_state()
                    return Signal(SignalSide.SELL, quantity_pct=1.0, tag="TP_EXIT")
                
                # 3. VWAP Exit (Worsening Conditions)
                if current_price < vwap:
                    self._reset_state()
                    return Signal(SignalSide.SELL, quantity_pct=1.0, tag="VWAP_EXIT")
            
            elif self.active_side == 'SHORT':
                # 1. SL Check
                if current_price >= self.sl_price:
                    self._reset_state()
                    return Signal(SignalSide.BUY, quantity_pct=1.0, tag="SL_EXIT")
                
                # 2. TP Check
                if current_price <= self.tp_price:
                    self._reset_state()
                    return Signal(SignalSide.BUY, quantity_pct=1.0, tag="TP_EXIT")
                
                # 3. VWAP Exit
                if current_price > vwap:
                    self._reset_state()
                    return Signal(SignalSide.BUY, quantity_pct=1.0, tag="VWAP_EXIT")

            # 4. Time Stop (8 hours)
            if self.entry_ts:
                duration = (ts - self.entry_ts).total_seconds() / 3600
                if duration >= 8:
                    exit_side = SignalSide.SELL if self.active_side == 'LONG' else SignalSide.BUY
                    self._reset_state()
                    return Signal(exit_side, quantity_pct=1.0, tag="TIME_STOP_EXIT")

            # 5. Session Close
            if self.is_market_closing_soon(ts):
                exit_side = SignalSide.SELL if self.active_side == 'LONG' else SignalSide.BUY
                self._reset_state()
                return Signal(exit_side, quantity_pct=1.0, tag="SESSION_CLOSE_EXIT")

        # --- ENTRY LOGIC ---
        if abs(pos_qty) < 1e-6:
            # LONG ENTRY
            if bar['Low'] <= vwap and bar['Close'] > vwap:
                if lower_wick > 2 * body and bar['Volume'] > vol_sma:
                    if pd.isna(atr): return Signal(SignalSide.HOLD)
                    
                    self.entry_price = bar['Close']
                    self.active_side = 'LONG'
                    self.entry_ts = ts
                    risk_distance = atr * self.atr_multiplier_sl
                    self.sl_price = self.entry_price - risk_distance
                    self.tp_price = self.entry_price + (atr * self.atr_multiplier_tp)
                    qty = (portfolio_context["total_equity"] * self.risk_pct) / risk_distance
                    return Signal(SignalSide.BUY, quantity=qty, tag="VWAP_BOUNCE_LONG")

            # SHORT ENTRY
            if bar['High'] >= vwap and bar['Close'] < vwap:
                if upper_wick > 2 * body and bar['Volume'] > vol_sma:
                    if pd.isna(atr): return Signal(SignalSide.HOLD)
                    
                    self.entry_price = bar['Close']
                    self.active_side = 'SHORT'
                    self.entry_ts = ts
                    risk_distance = atr * self.atr_multiplier_sl
                    self.sl_price = self.entry_price + risk_distance
                    self.tp_price = self.entry_price - (atr * self.atr_multiplier_tp)
                    qty = (portfolio_context["total_equity"] * self.risk_pct) / risk_distance
                    return Signal(SignalSide.SELL, quantity=qty, tag="VWAP_BOUNCE_SHORT")

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
