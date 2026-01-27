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
        df['SMA_200'] = self.sma(df['Close'], 200) # v3.1 Trend Filter
        
        # Volume SMA
        df['Volume_SMA_20'] = self.sma(df['Volume'], 20)
        
        # Connors RSI
        df['CRSI'] = self.connors_rsi(df['Close'], 3, 2, 100)
        
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
            
        # Session VWAP (Resets at the start of each day in NY)
        # 1. Calculate Typical Price
        typical_price = (df['High'] + df['Low'] + df['Close']) / 3
        
        # 2. Calculate PV (Price * Volume)
        pv = typical_price * df['Volume']
        
        # 3. Group by Date (NY Timezone) and calculate Cumulative Sums
        # Ensure the index is a DatetimeIndex and convert to NY to catch the reset correctly
        try:
            ny_index = df.index.tz_convert('America/New_York')
        except Exception:
            # Fallback if index is not timezone aware (assume UTC)
            ny_index = df.index.tz_localize('UTC').tz_convert('America/New_York')

        df_temp = pd.DataFrame(index=df.index)
        df_temp['pv'] = pv
        df_temp['vol'] = df['Volume']
        df_temp['date'] = ny_index.date
        
        # Group by date and cumsum
        df_temp['cum_pv'] = df_temp.groupby('date')['pv'].cumsum()
        df_temp['cum_vol'] = df_temp.groupby('date')['vol'].cumsum()
        
        return df_temp['cum_pv'] / df_temp['cum_vol']

    def sma(self, series: pd.Series, period: int) -> pd.Series:
        if HAS_TALIB:
             return pd.Series(talib.SMA(series.values.astype(float), timeperiod=period), index=series.index)
        return series.rolling(window=period).mean()

    def streak(self, close: pd.Series) -> pd.Series:
        """
        Calculates the streak of consecutive days up or down.
        Up days = +1, +2...
        Down days = -1, -2...
        Unchanged = 0
        """
        diff = close.diff().fillna(0)
        
        # We need to iterate or use a cumulative group approach
        # Vectorized approach:
        # Create a group id that increments when sign changes
        
        # 1. Sign of change
        signs = np.sign(diff)
        
        # 2. Identify change of sign (where sign != prev_sign)
        # We use (sign != sign.shift)
        # Note: 0 is treated as its own sign, but CRSI usually treats 0 as breaking streak or sustaining?
        # Standard Connors: Streak resets on 0? Or 0 continues?
        # Usually: Close > Prev => Streak > 0. Close < Prev => Streak < 0. Close == Prev => Streak = 0.
        
        # Let's assume strict inequality.
        
        # Compare to prev value to efficiently group
        # This is checking "start of new streak"
        no_change = (diff == 0)
        change_sign = (signs != signs.shift(1)) & (~no_change)
        
        stats = pd.DataFrame({'val': signs, 'change': change_sign})
        stats['group'] = stats['change'].cumsum()
        
        # Now groupby group and cumsum the signs?
        # If signs are +1, +1, +1 => cumsum is 1, 2, 3. Correct.
        # If signs are -1, -1 => cumsum is -1, -2. Correct.
        
        streaks = stats.groupby('group')['val'].cumsum()
        
        # Where diff was 0, streak is 0
        streaks[no_change] = 0
        
        return streaks

    def connors_rsi(self, close: pd.Series, rsi_period=3, streak_period=2, rank_period=100) -> pd.Series:
        """
        Calculates Connors RSI (3,2,100).
        CRSI = (RSI(3) + RSI(Streak, 2) + PercentRank(100)) / 3
        """
        # 1. RSI(Close, 3)
        rsi_price = self.rsi(close, rsi_period)
        
        # 2. RSI(Streak, 2)
        s = self.streak(close)
        rsi_streak = self.rsi(s, streak_period)
        
        # 3. PercentRank(Return, 100)
        # Percentage of correct values in the lookback period that are LESS than current value
        # We use one-day return (pct_change or just diff?)
        # Connors definition: "Percent Rank of the one-day return"
        ret = close.pct_change().fillna(0)
        
        # Rolling Rank (Percent)
        # Pandas rolling doesn't have 'rank'. using apply is slow but standard.
        # Ensure we just rank the current value against the window.
        
        def calc_rank(x):
            # x is the window (size 100) including current
            # rank of the last item
            current = x[-1]
            # Count how many are strictly less than current
            count = (x < current).sum()
            # Connors formula usually: number of values < current / total values * 100
            # Some defs use <=. Let's use < as typical percentile.
            return (count / len(x)) * 100.0

        # Optimization: scipy might be faster if imported, but let's stick to numpy/pandas
        percent_rank = ret.rolling(window=rank_period).apply(calc_rank, raw=True)
        
        crsi = (rsi_price + rsi_streak + percent_rank) / 3.0
        return crsi

