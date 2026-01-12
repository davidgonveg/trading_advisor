import pandas as pd
import numpy as np
import logging
from typing import Dict, Optional

# Try to import talib, fallback to pandas
try:
    import talib
    HAS_TALIB = True
except ImportError:
    HAS_TALIB = False

logger = logging.getLogger("core.analysis.indicators")

class TechnicalIndicators:
    """
    Calculates technical indicators for market data.
    """
    
    def calculate_all(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate all strategy indicators and return DataFrame with added columns.
        """
        if data.empty:
            return data
            
        df = data.copy()
        
        # Ensure we have required columns
        # RSI
        df['RSI'] = self.rsi(df['Close'], 14)
        
        # Bollinger Bands
        upper, middle, lower = self.bbands(df['Close'], 20, 2.0)
        df['BB_Upper'] = upper
        df['BB_Middle'] = middle
        df['BB_Lower'] = lower
        
        # ADX (Requires High, Low, Close)
        df['ADX'] = self.adx(df['High'], df['Low'], df['Close'], 14)
        
        # ATR
        df['ATR'] = self.atr(df['High'], df['Low'], df['Close'], 14)
        
        # VWAP
        df['VWAP'] = self.vwap(df)
        
        # SMA 50 (Daily logic usually applies to specific timeframe, but can calculate here)
        df['SMA_50'] = self.sma(df['Close'], 50)
        
        # Volume SMA
        df['Volume_SMA_20'] = self.sma(df['Volume'], 20)
        
        return df

    def rsi(self, close: pd.Series, period: int = 14) -> pd.Series:
        if HAS_TALIB:
            return pd.Series(talib.RSI(close.values, timeperiod=period), index=close.index)
        else:
            delta = close.diff()
            gain = (delta.where(delta > 0, 0)).fillna(0)
            loss = (-delta.where(delta < 0, 0)).fillna(0)
            avg_gain = gain.rolling(window=period, min_periods=period).mean()
            avg_loss = loss.rolling(window=period, min_periods=period).mean()
            rs = avg_gain / avg_loss.replace(0, np.nan)
            return 100 - (100 / (1 + rs))

    def bbands(self, close: pd.Series, period: int = 20, dev: float = 2.0):
        if HAS_TALIB:
            u, m, l = talib.BBANDS(close.values, timeperiod=period, nbdevup=dev, nbdevdn=dev, matype=0)
            return pd.Series(u, index=close.index), pd.Series(m, index=close.index), pd.Series(l, index=close.index)
        else:
            m = close.rolling(window=period).mean()
            std = close.rolling(window=period).std()
            u = m + (std * dev)
            l = m - (std * dev)
            return u, m, l
            
    def adx(self, high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
        if HAS_TALIB:
            return pd.Series(talib.ADX(high.values, low.values, close.values, timeperiod=period), index=close.index)
        else:
            # Simplified Pandas ADX (approximate)
            # True Range
            tr1 = high - low
            tr2 = abs(high - close.shift(1))
            tr3 = abs(low - close.shift(1))
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            atr = tr.rolling(window=period).mean()
            
            # Plus Directional Movement
            up_move = high.diff()
            down_move = -low.diff()
            plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
            minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
            
            plus_di = 100 * pd.Series(plus_dm, index=close.index).rolling(window=period).mean() / atr
            minus_di = 100 * pd.Series(minus_dm, index=close.index).rolling(window=period).mean() / atr
            
            dx = (abs(plus_di - minus_di) / (plus_di + minus_di)) * 100
            adx = dx.rolling(window=period).mean()
            return adx

    def atr(self, high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
        if HAS_TALIB:
            return pd.Series(talib.ATR(high.values, low.values, close.values, timeperiod=period), index=close.index)
        else:
            tr1 = high - low
            tr2 = abs(high - close.shift(1))
            tr3 = abs(low - close.shift(1))
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            return tr.rolling(window=period).mean()
            
    def vwap(self, df: pd.DataFrame) -> pd.Series:
        if 'Volume' not in df.columns:
            return pd.Series(np.nan, index=df.index)
            
        typical_price = (df['High'] + df['Low'] + df['Close']) / 3
        # Cumulative VWAP usually resets daily? 
        # For indicators on continuous timeframe, standard is rolling or cumulative.
        # Simple implementation: Cumulative from start of series (or window?)
        # Standard Intraday VWAP resets at market open.
        # Here we implement a generic cumulative or window?
        # Let's do a simple rolling VWAP for trend analysis or just full cumulative.
        # Strategy usually needs Anchor VWAP or session VWAP.
        # Implementing Rolling VWAP (window=period) might be better for continuous?
        # No, VWAP is usually Session based.
        # Let's approximate by grouping by day?
        # COMPLEXITY: Continuous data spans days.
        # Let's use simple rolling for now to match legacy behavior roughly or better session-based.
        
        # Legacy implementation was cumulative.
        cumulative_pv = (typical_price * df['Volume']).cumsum()
        cumulative_volume = df['Volume'].cumsum()
        return cumulative_pv / cumulative_volume

    def sma(self, series: pd.Series, period: int) -> pd.Series:
        if HAS_TALIB:
             return pd.Series(talib.SMA(series.values, timeperiod=period), index=series.index)
        return series.rolling(window=period).mean()
