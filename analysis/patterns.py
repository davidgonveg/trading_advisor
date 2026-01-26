import pandas as pd
import numpy as np
import logging

# Try importing TA-Lib
try:
    import talib
    HAS_TALIB = True
except ImportError:
    HAS_TALIB = False

logger = logging.getLogger("core.analysis.patterns")

class PatternRecognizer:
    """
    Detects candle patterns required by the strategy.
    Patterns:
    - Hammer (Bullish Reversal)
    - Shooting Star (Bearish Reversal)
    - Bullish Engulfing
    - Bearish Engulfing
    - Doji (Indecision/Reversal context)
    """
    
    def detect_patterns(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Appends boolean columns for patterns: 'is_hammer', 'is_shooting_star', etc.
        """
        if df.empty:
            return df
            
        data = df.copy()
        op = data['Open']
        hi = data['High']
        lo = data['Low']
        cl = data['Close']
        
        body = abs(cl - op)
        upper_wick = hi - np.maximum(cl, op)
        lower_wick = np.minimum(cl, op) - lo

        if HAS_TALIB:
            # TA-Lib returns integer score (usually 100 or -100)
            data['pat_hammer'] = talib.CDLHAMMER(op, hi, lo, cl)
            data['pat_shooting_star'] = talib.CDLSHOOTINGSTAR(op, hi, lo, cl)
            data['pat_engulfing'] = talib.CDLENGULFING(op, hi, lo, cl) # +100 bull, -100 bear
            data['pat_doji'] = talib.CDLDOJI(op, hi, lo, cl)
        else:
            # Pandas / Custom Logic Implementation
            # 1. Hammer: Small body, long lower wick, small/no upper wick
            avg_body = body.rolling(10).mean() # relative body size
            
            # Logic: Lower wick > 2 * body, Upper wick very small
            is_hammer = (lower_wick > 2 * body) & (upper_wick < body * 0.5)
            data['pat_hammer'] = np.where(is_hammer, 100, 0)
            
            # 2. Shooting Star: Small body, long upper wick
            is_star = (upper_wick > 2 * body) & (lower_wick < body * 0.5)
            data['pat_shooting_star'] = np.where(is_star, -100, 0) # usually strictly bearish
            
            # 3. Engulfing
            # Bullish: Prev Red, Curr Green, Curr Open < Prev Close, Curr Close > Prev Open
            prev_op = op.shift(1)
            prev_cl = cl.shift(1)
            
            is_bull_eng = (cl > op) & (prev_cl < prev_op) & (op < prev_cl) & (cl > prev_op)
            is_bear_eng = (cl < op) & (prev_cl > prev_op) & (op > prev_cl) & (cl < prev_op)
            
            data['pat_engulfing'] = 0
            data.loc[is_bull_eng, 'pat_engulfing'] = 100
            data.loc[is_bear_eng, 'pat_engulfing'] = -100
            
            # 4. Doji: Body is very very small
            is_doji = body <= (hi - lo) * 0.1
            data['pat_doji'] = np.where(is_doji, 100, 0)

        # 5. Pure Wick Rejection (VWAP Bounce Strategy) - ALWAYS RUN
        # Bullish: Lower Wick > 2 * Body
        is_wick_bull = lower_wick > (2 * body)
        data['pat_wick_bull'] = np.where(is_wick_bull, 100, 0)

        # Bearish: Upper Wick > 2 * Body
        is_wick_bear = upper_wick > (2 * body)
        data['pat_wick_bear'] = np.where(is_wick_bear, -100, 0)

        return data

    def check_bullish_reversal(self, row) -> bool:
        """Check if row has any bullish reversal pattern."""
        hammer = row.get('pat_hammer', 0) > 0
        bull_eng = row.get('pat_engulfing', 0) > 0
        doji = row.get('pat_doji', 0) != 0 # Doji is context dependent, but we treat presence as signal if other conds met
        
        return hammer or bull_eng or doji

    def check_bearish_reversal(self, row) -> bool:
        """Check if row has any bearish reversal pattern."""
        star = row.get('pat_shooting_star', 0) != 0 # TA-lib might return -100
        # Check explicit negative shooting star creation if standard is neg
        # In custom I used -100? No I used +100 for Hammer, -100 for Star?
        # WAIT: In custom 'pat_shooting_star', I set -100.
        # TA-Lib returns -100 for shooting star.
        
        bear_eng = row.get('pat_engulfing', 0) < 0
        doji = row.get('pat_doji', 0) != 0
        
        # Shooting Star check (handle both 100 and -100 just in case logic varies)
        is_star = row.get('pat_shooting_star', 0) != 0
        
        return is_star or bear_eng or doji

    def check_wick_reversal(self, row) -> int:
        """
        Returns 1 for Bullish Wick Rejection, -1 for Bearish, 0 otherwise.
        """
        if row.get('pat_wick_bull', 0) > 0:
            return 1
        if row.get('pat_wick_bear', 0) < 0: # Bearish stored as -100
            return -1
        return 0
