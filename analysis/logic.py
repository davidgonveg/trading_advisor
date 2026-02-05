import pandas as pd
from typing import Dict, Optional, Any
from analysis.signal import SignalType

def check_vwap_bounce(row: pd.Series, params: Dict[str, Any]) -> Optional[SignalType]:
    """
    Centralized logic for VWAP Bounce Strategy Entry.
    Returns SignalType.LONG, SignalType.SHORT, or None.
    
    Expected keys in row:
    - Close, Open, High, Low, Volume
    - VWAP
    - Volume_SMA_20 (or Vol_SMA)
    - RSI (if rsi filter enabled)
    - EMA_200 (or Dist_EMA200 if trend filter enabled)
    """
    
    # Extract params with safe defaults
    wick_ratio = params.get('wick_ratio', 2.0)
    vol_mult = params.get('vol_mult', 1.0)
    
    use_rsi = params.get('use_rsi_filter', False)
    rsi_long = params.get('rsi_threshold_long', 70)
    rsi_short = params.get('rsi_threshold_short', 30)
    
    use_trend = params.get('use_trend_filter', False)
    
    # Extract Data 
    close = row.get('Close')
    low = row.get('Low')
    high = row.get('High')
    open_p = row.get('Open')
    vol = row.get('Volume')
    
    vwap = row.get('VWAP')
    
    # Handle naming variations
    vol_sma = row.get('Volume_SMA_20')
    if pd.isna(vol_sma) or vol_sma == 0:
        vol_sma = row.get('Vol_SMA', 0)
        
    rsi = row.get('RSI', 50)
    
    ema200 = row.get('EMA_200')
    dist_ema200 = row.get('Dist_EMA200')
    
    # Critical Validation
    if not vwap or pd.isna(vwap): return None
    # We allow Vol_SMA to be missing? No, strategy requires volume confirmation.
    if pd.isna(vol_sma) or vol_sma == 0: return None
    
    # Pattern Calculation (Calculated here to ensure consistency with Logic, disregarding pre-calc differences)
    # Using 'abs' for body just in case
    body = abs(close - open_p)
    lower_wick = min(open_p, close) - low
    upper_wick = high - max(open_p, close)
    
    # 1. Volume Confirmation
    if vol <= (vol_sma * vol_mult):
        return None
        
    # 2. LONG Check
    # Rule: Low touched VWAP from above (implied by Low <= VWAP < Close?)
    # Usually Bounce means it dipped below and closed above? Or just touched?
    # Logic: Low <= VWAP and Close > VWAP. (Wick passed through/touched VWAP)
    is_long_bounce = (low <= vwap) and (close > vwap)
    
    if is_long_bounce:
        valid_wick = lower_wick > (wick_ratio * body)
        valid_rsi = (not use_rsi) or (rsi < rsi_long)
        
        valid_trend = True
        if use_trend:
            if dist_ema200 is not None and not pd.isna(dist_ema200): 
                valid_trend = dist_ema200 > 0
            elif ema200 is not None and not pd.isna(ema200): 
                valid_trend = close > ema200
        
        if valid_wick and valid_rsi and valid_trend:
            return SignalType.LONG

    # 3. SHORT Check
    # Rule: High touched VWAP from below. High >= VWAP and Close < VWAP.
    is_short_bounce = (high >= vwap) and (close < vwap)
    
    if is_short_bounce:
        valid_wick = upper_wick > (wick_ratio * body)
        valid_rsi = (not use_rsi) or (rsi > rsi_short)
        
        valid_trend = True
        if use_trend:
            if dist_ema200 is not None and not pd.isna(dist_ema200): 
                valid_trend = dist_ema200 < 0
            elif ema200 is not None and not pd.isna(ema200): 
                valid_trend = close < ema200
        
        if valid_wick and valid_rsi and valid_trend:
            return SignalType.SHORT
            
    return None
