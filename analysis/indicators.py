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
            return pd.Series(talib.RSI(close.values.astype(float), timeperiod=period), index=close.index)
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
            u, m, l = talib.BBANDS(close.values.astype(float), timeperiod=period, nbdevup=dev, nbdevdn=dev, matype=0)
            return pd.Series(u, index=close.index), pd.Series(m, index=close.index), pd.Series(l, index=close.index)
        else:
            m = close.rolling(window=period).mean()
            std = close.rolling(window=period).std()
            u = m + (std * dev)
            l = m - (std * dev)
            return u, m, l
            
    def adx(self, high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
        if HAS_TALIB:
            return pd.Series(talib.ADX(high.values.astype(float), low.values.astype(float), close.values.astype(float), timeperiod=period), index=close.index)
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
            return pd.Series(talib.ATR(high.values.astype(float), low.values.astype(float), close.values.astype(float), timeperiod=period), index=close.index)
        else:
            tr1 = high - low
            tr2 = abs(high - close.shift(1))
            tr3 = abs(low - close.shift(1))
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            return tr.rolling(window=period).mean()
            
    def vwap(self, df: pd.DataFrame) -> pd.Series:
        if 'Volume' not in df.columns:
            return pd.Series(np.nan, index=df.index)
            
        # Session VWAP (Resets at the start of each day)
        # 1. Calculate Typical Price
        typical_price = (df['High'] + df['Low'] + df['Close']) / 3
        
        # 2. Calculate PV (Price * Volume)
        pv = typical_price * df['Volume']
        
        # 3. Group by Date and calculate Cumulative Sums
        # This requires the index to be a DatetimeIndex
        df_temp = pd.DataFrame(index=df.index)
        df_temp['pv'] = pv
        df_temp['vol'] = df['Volume']
        df_temp['date'] = df.index.date
        
        # Group by date and cumsum
        # We use transform to keep the original index structure
        df_temp['cum_pv'] = df_temp.groupby('date')['pv'].cumsum()
        df_temp['cum_vol'] = df_temp.groupby('date')['vol'].cumsum()
        
        return df_temp['cum_pv'] / df_temp['cum_vol']

    def sma(self, series: pd.Series, period: int) -> pd.Series:
        if HAS_TALIB:
             return pd.Series(talib.SMA(series.values.astype(float), timeperiod=period), index=series.index)
        return series.rolling(window=period).mean()
