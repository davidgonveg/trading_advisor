from backtesting.core.strategy_interface import StrategyInterface, Signal, SignalSide
import pandas as pd
import numpy as np
import ta
from typing import Dict, Any, List, Optional
from backtesting.core.data_loader import DataLoader
import logging

logger = logging.getLogger("backtesting.strategies.ema_pullback")

class EMAPullback(StrategyInterface):
    def setup(self, params: Dict[str, Any]):
        self.risk_pct = params.get("risk_pct", 0.015)
        self.ema_fast_period = params.get("ema_fast", 20)
        self.ema_slow_daily_period = params.get("ema_slow_daily", 100)
        self.adx_threshold = params.get("adx_threshold", 25)
        self.vol_sma_period = params.get("volume_sma", 20)
        self.atr_period = params.get("atr_period", 14)
        self.sl_atr_mult = params.get("sl_atr_mult", 1.5)
        self.tp1_pct = params.get("tp1_pct", 0.012)
        self.trailing_atr_mult = params.get("trailing_atr_mult", 1.0)
        
        self.params = params
        self.indicators_df = None
        
        # State tracking for the current trade
        self.entry_price = 0.0
        self.sl_price = 0.0
        self.tp1_price = 0.0
        self.tp1_hit = False
        self.active_side = None # 'LONG' or 'SHORT'
        self.trailing_stop_active = False
        self.last_indicators = {}

    def get_params(self) -> Dict[str, Any]:
        return self.params

    def _precompute_indicators(self, data: pd.DataFrame):
        """
        Calculates indicators for 1H and merges 1D bias data.
        """
        # Note: BacktestEngine passes the data but doesn't explicitly pass the symbol.
        # We can extract it if needed or assume it's part of the engine state if we had access.
        # However, for now, we'll try to find the symbol in the dataframe name or similar if possible, 
        # but the engine currently doesn't provide it easily to the strategy.
        # Wait, the main.py loop has the symbol. 
        # Let's check how VWAPBounce gets it. It doesn't.
        # I'll modify BacktestEngine to set the symbol on the strategy if it can.
        
        # For now, let's assume we can get it from an attribute if we set it in set_strategy or similar.
        symbol = getattr(self, "symbol", "SPY") # Default to SPY if not set
        
        logger.info(f"Computing indicators for {symbol}...")
        
        # 1. Calculate 1H Indicators
        # EMA 20 (1H)
        ema20 = ta.trend.ema_indicator(data['Close'], window=self.ema_fast_period)
        
        # ATR 14 (1H)
        atr = ta.volatility.average_true_range(data['High'], data['Low'], data['Close'], window=self.atr_period)
        
        # Volume SMA 20 (1H)
        vol_sma = ta.trend.sma_indicator(data['Volume'], window=self.vol_sma_period)
        
        # 2. Get 1D Bias Data
        loader = DataLoader()
        start_date = data.index[0]
        end_date = data.index[-1]
        
        df_daily = loader.load_data(
            symbol=symbol,
            interval="1d",
            start_date=start_date,
            end_date=end_date
        )
        
        if not df_daily.empty:
            # EMA 100 (Daily)
            df_daily['EMA100_daily'] = ta.trend.ema_indicator(df_daily['Close'], window=self.ema_slow_daily_period)
            
            # ADX and DI (Daily)
            adx_obj = ta.trend.ADXIndicator(df_daily['High'], df_daily['Low'], df_daily['Close'], window=14)
            df_daily['ADX_daily'] = adx_obj.adx()
            df_daily['DI_pos_daily'] = adx_obj.adx_pos()
            df_daily['DI_neg_daily'] = adx_obj.adx_neg()
            df_daily['Close_daily'] = df_daily['Close']
            
            # Shift daily indicators by 1 day so 1H see the data from the PREVIOUS day
            daily_bias = df_daily[['EMA100_daily', 'ADX_daily', 'DI_pos_daily', 'DI_neg_daily', 'Close_daily']].shift(1)
            
            # Reindex to 1H index and forward fill
            daily_bias_1h = daily_bias.reindex(data.index, method='ffill')
        else:
            logger.warning(f"Could not load daily data for {symbol}, bias filter will be disabled.")
            daily_bias_1h = pd.DataFrame(index=data.index)
            for col in ['EMA100_daily', 'ADX_daily', 'DI_pos_daily', 'DI_neg_daily', 'Close_daily']:
                daily_bias_1h[col] = np.nan

        self.indicators_df = pd.DataFrame({
            'EMA20': ema20,
            'ATR': atr,
            'Vol_SMA': vol_sma,
            'EMA100_daily': daily_bias_1h['EMA100_daily'],
            'ADX_daily': daily_bias_1h['ADX_daily'],
            'DI_pos_daily': daily_bias_1h['DI_pos_daily'],
            'DI_neg_daily': daily_bias_1h['DI_neg_daily'],
            'Close_daily': daily_bias_1h['Close_daily']
        }, index=data.index)

    def on_bar(self, history: pd.DataFrame, portfolio_context: Dict[str, Any]) -> Signal:
        bar = history.iloc[-1]
        ts = bar.name
        
        if self.indicators_df is None or ts not in self.indicators_df.index:
            return Signal(SignalSide.HOLD)
            
        ind = self.indicators_df.loc[ts]
        
        # Indicators
        ema20 = ind['EMA20']
        atr = ind['ATR']
        vol_sma = ind['Vol_SMA']
        
        # Bias (Daily)
        ema100_d = ind['EMA100_daily']
        adx_d = ind['ADX_daily']
        di_pos_d = ind['DI_pos_daily']
        di_neg_d = ind['DI_neg_daily']
        close_d = ind['Close_daily']
        
        self.last_indicators = {
            "EMA20": round(ema20, 2) if not pd.isna(ema20) else 0,
            "ADX_D": round(adx_d, 2) if not pd.isna(adx_d) else 0,
            "ATR": round(atr, 2) if not pd.isna(atr) else 0
        }
        
        pos_qty = sum(portfolio_context["positions"].values())
        
        # --- MANAGEMENT LOGIC (If in a trade) ---
        if pos_qty > 0:
            current_price = bar['Close']
            
            if self.active_side == 'LONG':
                # TP1 Check (+1.2%)
                if not self.tp1_hit and current_price >= self.tp1_price:
                    self.tp1_hit = True
                    self.trailing_stop_active = True
                    # Partial close 50%
                    return Signal(SignalSide.SELL, quantity_pct=0.5, tag="EMA_PULLBACK_TP1")
                
                # Update Trailing Stop
                if self.trailing_stop_active:
                    new_sl = current_price - (self.trailing_atr_mult * atr)
                    if new_sl > self.sl_price:
                        self.sl_price = new_sl
                
                if current_price <= self.sl_price:
                    self._reset_state()
                    return Signal(SignalSide.SELL, quantity_pct=1.0, tag="EMA_PULLBACK_SL_EXIT")

            elif self.active_side == 'SHORT':
                # TP1 Check (-1.2%)
                if not self.tp1_hit and current_price <= self.tp1_price:
                    self.tp1_hit = True
                    self.trailing_stop_active = True
                    return Signal(SignalSide.BUY, quantity_pct=0.5, tag="EMA_PULLBACK_TP1")
                
                # Update Trailing Stop
                if self.trailing_stop_active:
                    new_sl = current_price + (self.trailing_atr_mult * atr)
                    if new_sl < self.sl_price:
                        self.sl_price = new_sl
                
                if current_price >= self.sl_price:
                    self._reset_state()
                    return Signal(SignalSide.BUY, quantity_pct=1.0, tag="EMA_PULLBACK_SL_EXIT")

        # --- ENTRY LOGIC ---
        if pos_qty == 0:
            if pd.isna(ema100_d) or pd.isna(adx_d) or pd.isna(ema20) or pd.isna(atr):
                return Signal(SignalSide.HOLD)
            
            # LONG ENTRY
            if close_d > ema100_d and adx_d >= self.adx_threshold and di_pos_d > di_neg_d:
                if bar['Low'] <= ema20 and bar['Close'] > ema20:
                    if bar['Volume'] > vol_sma:
                        self.entry_price = bar['Close']
                        self.active_side = 'LONG'
                        self.tp1_hit = False
                        self.trailing_stop_active = False
                        
                        risk_distance = self.sl_atr_mult * atr
                        self.sl_price = self.entry_price - risk_distance
                        self.tp1_price = self.entry_price * (1 + self.tp1_pct)
                        
                        risk_amount = portfolio_context["total_equity"] * self.risk_pct
                        qty = risk_amount / risk_distance
                        
                        # Safety: Cap position size to 95% of total equity
                        max_qty = (portfolio_context["total_equity"] * 0.95) / bar['Close']
                        qty = min(qty, max_qty)
                        
                        return Signal(SignalSide.BUY, quantity=qty, tag="EMA_PULLBACK_LONG")

            # SHORT ENTRY
            if close_d < ema100_d and adx_d >= self.adx_threshold and di_neg_d > di_pos_d:
                if bar['High'] >= ema20 and bar['Close'] < ema20:
                    if bar['Volume'] > vol_sma:
                        self.entry_price = bar['Close']
                        self.active_side = 'SHORT'
                        self.tp1_hit = False
                        self.trailing_stop_active = False
                        
                        risk_distance = self.sl_atr_mult * atr
                        self.sl_price = self.entry_price + risk_distance
                        self.tp1_price = self.entry_price * (1 - self.tp1_pct)
                        
                        risk_amount = portfolio_context["total_equity"] * self.risk_pct
                        qty = risk_amount / risk_distance
                        
                        # Safety: Cap position size to 95% of total equity
                        max_qty = (portfolio_context["total_equity"] * 0.95) / bar['Close']
                        qty = min(qty, max_qty)
                        
                        return Signal(SignalSide.SELL, quantity=qty, tag="EMA_PULLBACK_SHORT")

        return Signal(SignalSide.HOLD)

    def _reset_state(self):
        self.entry_price = 0.0
        self.sl_price = 0.0
        self.tp1_price = 0.0
        self.tp1_hit = False
        self.active_side = None
        self.trailing_stop_active = False
