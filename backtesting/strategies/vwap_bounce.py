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
        """Vectorized pre-calculation of all necessary indicators including ATR and context for ML."""
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

        # 5. Passive Indicators for ML Context
        # RSI 14
        delta = data['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))

        # Price distance to EMA 200 (Trend Context)
        ema200 = data['Close'].ewm(span=200, adjust=False).mean()
        dist_ema200 = (data['Close'] - ema200) / ema200
        
        # ===== PHASE 1: CORE INDICATORS =====
        
        # MACD (Moving Average Convergence Divergence)
        ema12 = data['Close'].ewm(span=12, adjust=False).mean()
        ema26 = data['Close'].ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        macd_signal = macd.ewm(span=9, adjust=False).mean()
        macd_hist = macd - macd_signal
        
        # Bollinger Bands
        bb_sma = data['Close'].rolling(window=20).mean()
        bb_std = data['Close'].rolling(window=20).std()
        bb_upper = bb_sma + (2 * bb_std)
        bb_lower = bb_sma - (2 * bb_std)
        bb_width = (bb_upper - bb_lower) / data['Close']
        bb_pctb = (data['Close'] - bb_lower) / (bb_upper - bb_lower + 1e-10)
        
        # Stochastic Oscillator
        low_14 = data['Low'].rolling(window=14).min()
        high_14 = data['High'].rolling(window=14).max()
        stoch_k = 100 * (data['Close'] - low_14) / (high_14 - low_14 + 1e-10)
        stoch_d = stoch_k.rolling(window=3).mean()
        
        # Williams %R
        williams_r = -100 * (high_14 - data['Close']) / (high_14 - low_14 + 1e-10)
        
        # Rate of Change
        roc = ((data['Close'] - data['Close'].shift(10)) / data['Close'].shift(10)) * 100
        
        # Volume Indicators
        volume_ratio = data['Volume'] / (vol_sma + 1e-10)
        
        # OBV (On-Balance Volume)
        obv = (np.sign(data['Close'].diff()) * data['Volume']).fillna(0).cumsum()
        obv_ema = obv.ewm(span=20, adjust=False).mean()
        
        # EMA Distances
        ema20 = data['Close'].ewm(span=20, adjust=False).mean()
        ema50 = data['Close'].ewm(span=50, adjust=False).mean()
        ema100 = data['Close'].ewm(span=100, adjust=False).mean()
        dist_ema20 = (data['Close'] - ema20) / (ema20 + 1e-10)
        dist_ema50 = (data['Close'] - ema50) / (ema50 + 1e-10)
        dist_ema100 = (data['Close'] - ema100) / (ema100 + 1e-10)
        
        # ATR as percentage of price
        atr_pct = atr / (data['Close'] + 1e-10)
        
        # VWAP Distance
        vwap_dist_pct = (data['Close'] - vwap) / (vwap + 1e-10)
        
        # Time features
        hour = data.index.hour
        day_of_week = data.index.dayofweek
        
        # 6. ===== NEW ROBUST INDICATORS (Phase 2) =====
        
        # Log Returns (Stationary Price Dynamics)
        log_returns = np.log(data['Close'] / data['Close'].shift(1)).fillna(0)
        
        # Historical Volatility (20 period rolling std of returns)
        hist_vol = log_returns.rolling(window=20).std().fillna(0)
        
        # Slope (Regression-like of Log Prices for stationarity) -> 5 periods
        # Slope of ln(price) is approx % change per bar
        slope = np.log(data['Close']).diff(5) / 5
        slope = slope.fillna(0)
        
        # Acceleration
        acceleration = slope.diff().fillna(0)
        
        # Donchian Channels (Breakout Context)
        donchian_high = data['High'].rolling(window=20).max()
        donchian_low = data['Low'].rolling(window=20).min()
        donchian_pos = (data['Close'] - donchian_low) / (donchian_high - donchian_low + 1e-10)
        
        # Keltner Channels (Volatility Context vs Bollinger)
        kc_mid = data['Close'].ewm(span=20, adjust=False).mean()
        kc_upper = kc_mid + (2 * atr)
        kc_lower = kc_mid - (2 * atr)
        kc_pos = (data['Close'] - kc_lower) / (kc_upper - kc_lower + 1e-10)
        
        # CCI (Commodity Channel Index)
        # TP was calculated above
        sma_tp = tp.rolling(window=20).mean()
        mean_dev = (tp - sma_tp).abs().rolling(window=20).mean()
        cci = (tp - sma_tp) / (0.015 * mean_dev + 1e-10)
        
        self.indicators_df = pd.DataFrame({
            # Original indicators
            'VWAP': vwap,
            'Vol_SMA': vol_sma,
            'Body': body,
            'LowerWick': lower_wick,
            'UpperWick': upper_wick,
            'ATR': atr,
            'RSI': rsi,
            'Dist_EMA200': dist_ema200,
            
            # Phase 1: MACD
            'MACD': macd,
            'MACD_Signal': macd_signal,
            'MACD_Hist': macd_hist,
            
            # Phase 1: Bollinger Bands
            'BB_Upper': bb_upper,
            'BB_Lower': bb_lower,
            'BB_Width': bb_width,
            'BB_PctB': bb_pctb,
            
            # Phase 1: Stochastic
            'Stoch_K': stoch_k,
            'Stoch_D': stoch_d,
            
            # Phase 1: Other Momentum
            'Williams_R': williams_r,
            'ROC': roc,
            
            # Phase 1: Volume
            'Volume_Ratio': volume_ratio,
            'OBV': obv,
            'OBV_EMA': obv_ema,
            
            # Phase 1: EMA Distances
            'Dist_EMA20': dist_ema20,
            'Dist_EMA50': dist_ema50,
            'Dist_EMA100': dist_ema100,
            
            # Phase 1: Volatility
            'ATR_Pct': atr_pct,
            'VWAP_Dist_Pct': vwap_dist_pct,
            
            # Phase 1: Time
            'Hour': hour,
            'Day_Of_Week': day_of_week,
            
            # Phase 2: Robust Indicators
            'Log_Return': log_returns,
            'Hist_Vol': hist_vol,
            'Slope': slope,
            'Acceleration': acceleration,
            'Donchian_Pos': donchian_pos,
            'Keltner_Pos': kc_pos,
            'CCI': cci
            
        }, index=data.index)

    def on_bar(self, history: pd.DataFrame, portfolio_context: Dict[str, Any]) -> Signal:
        bar = history.iloc[-1]
        ts = bar.name
        
        # Access precomputed indicators
        ind = self.indicators_df.loc[ts]
        if isinstance(ind, pd.DataFrame):
            ind = ind.iloc[0] # Handle duplicates
            
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
            "UpperWick": round(upper_wick, 2),
            "RSI": round(ind['RSI'], 2),
            "Dist_EMA200": round(ind['Dist_EMA200'], 4),
            "Close": round(bar['Close'], 2),  # Added for ML Feature Normalization
            "Open": round(bar['Open'], 2),
            "High": round(bar['High'], 2),
            "Low": round(bar['Low'], 2),
            "Volume": bar['Volume'],
            
            # New Phase 2 Indicators
            "Log_Return": ind['Log_Return'],
            "Hist_Vol": ind['Hist_Vol'],
            "Slope": ind['Slope'],
            "Acceleration": ind['Acceleration'],
            "Donchian_Pos": ind['Donchian_Pos'],
            "Keltner_Pos": ind['Keltner_Pos'],
            "CCI": ind['CCI']
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
                if duration >= self.time_stop_hours:
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
                # Core Logic
                valid_wick = lower_wick > (self.wick_ratio * body)
                valid_vol = bar['Volume'] > (vol_sma * self.vol_mult)
                
                # Optional Filters
                valid_rsi = True
                if self.use_rsi_filter:
                    valid_rsi = ind['RSI'] < self.rsi_threshold_long
                    
                valid_trend = True
                if self.use_trend_filter:
                    # Dist_EMA200 > 0 means Close > EMA200 (Uptrend)
                    valid_trend = ind['Dist_EMA200'] > 0
                
                if valid_wick and valid_vol and valid_rsi and valid_trend:
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
                # Core Logic
                valid_wick = upper_wick > (self.wick_ratio * body)
                valid_vol = bar['Volume'] > (vol_sma * self.vol_mult)
                
                # Optional Filters
                valid_rsi = True
                if self.use_rsi_filter:
                    valid_rsi = ind['RSI'] > self.rsi_threshold_short
                    
                valid_trend = True
                if self.use_trend_filter:
                    # Dist_EMA200 < 0 means Close < EMA200 (Downtrend)
                    valid_trend = ind['Dist_EMA200'] < 0

                if valid_wick and valid_vol and valid_rsi and valid_trend:
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
