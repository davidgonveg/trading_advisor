import pandas as pd
import numpy as np

class FeatureEngineer:
    """
    Central logic for ML feature extraction.
    Ensures parity between training (prepare_ml_dataset.py) and inference (MLFilter.py).
    
    Principles:
    1. STATIONARITY: All features must be relative/normalized (percentages, ratios).
       No absolute prices (exclude Close, VWAP) or volumes.
    2. ROBUSTNESS: Handle missing values gracefully (0.0 defaults).
    """
    
    @staticmethod
    def extract_features(current_indicators: dict, history_indicators: list) -> dict:
        """
        Extracts a single feature row from current + history indicators.
        
        Args:
            current_indicators: Dict of indicators for the current bar (at signal time).
            history_indicators: List of dicts for previous bars (L1, L2, etc.).
                                history[0] is L1 (1 bar ago), history[1] is L2, etc.
        """
        features = {}
        
        # Helper to safely get float
        def get_val(source, key, default=np.nan):
            val = source.get(key, default)
            if val is None or pd.isna(val):
                return default
            return float(val)

        # 1. Process Current Bar
        FeatureEngineer._process_bar(current_indicators, features, suffix="")
        
        # 2. Process History (Lags)
        for i, hist_inds in enumerate(history_indicators):
            suffix = f"_L{i+1}"
            FeatureEngineer._process_bar(hist_inds, features, suffix=suffix)
            
        return features

    @staticmethod
    def _process_bar(indicators: dict, dest: dict, suffix: str):
        """
        Calculates normalized features for a single bar and adds them to `dest`.
        """
        # Raw Values needed for normalization (but NOT added to features directly)
        close = indicators.get('close') or indicators.get('Close') 
        # Note: Audit logs might check 'close', indicators dict might use 'Close'. Handle both.
        
        if close is None:
            # Try to infer from other keys if strictly needed, or just return
            # Some indicators dicts might not have raw OHLC if not explicitly saved
            # But usually we need price to normalize
            pass
            
        # We assume the 'indicators' dict passed here might contain raw indicators derived from strategy.
        # Let's map specific known keys.
        
        # --- 1. RSI (Already Normalized 0-100) ---
        if 'RSI' in indicators:
            dest[f"RSI{suffix}"] = indicators['RSI']
            
        # --- 2. ATR -> NATR (Normalized ATR % of Price) ---
        # We need Close price to normalize. If not in indicators, we might fail.
        # Strategy usually puts 'close' in indicators for this specific reason if needed, 
        # or we rely on the fact that we might calculate NATR inside the strategy already?
        # Better: Calculate it here if 'ATR' and 'Close' exist.
        atr = indicators.get('ATR')
        
        # Try to find close in various casings
        close_price = indicators.get('close') or indicators.get('Close') or indicators.get('price')
        
        if atr is not None and close_price:
            dest[f"NATR{suffix}"] = (atr / close_price) * 100
        elif 'NATR' in indicators: # If strategy already did it
            dest[f"NATR{suffix}"] = indicators['NATR']
            
        # --- 3. VWAP -> Dist (Percent Distance) ---
        vwap = indicators.get('VWAP')
        if vwap is not None and not pd.isna(vwap) and close_price:
            dest[f"Dist_VWAP{suffix}"] = ((close_price - vwap) / vwap) * 100
        else:
            # Impute Neutral (0 distance) if VWAP missing (e.g. zero volume)
            # This allows XGBoost to see "no signal" instead of crashing/rejecting
            dest[f"Dist_VWAP{suffix}"] = 0.0
            
        # --- 4. Volume -> Ratio (to SMA) ---
        vol = indicators.get('Volume') or indicators.get('volume')
        vol_sma = indicators.get('Volume_SMA')
        
        if vol is not None and vol_sma and vol_sma > 0:
            dest[f"Vol_Ratio{suffix}"] = vol / vol_sma
        else:
            # Impute Neutral (1.0 ratio) if volume missing
            dest[f"Vol_Ratio{suffix}"] = 0.0  # Or 1.0? 0.0 implies "no volume" which is safer for "requires volume" strategies
            
        # --- 5. EMA Dist (Already usually a dist, but check) ---
        # Strategy often outputs 'Dist_EMA200' which is (Close - EMA)/EMA. This is good.
        if 'Dist_EMA200' in indicators:
            dest[f"Dist_EMA200{suffix}"] = indicators['Dist_EMA200']
            
        # --- 6. Wicks (Normalize by Body or Price) ---
        # If we have explicit UpperWick/LowerWick values (absolute size)
        u_wick = indicators.get('UpperWick')
        l_wick = indicators.get('LowerWick')
        
        if u_wick is not None and close_price:
             dest[f"Wick_Upper_Pct{suffix}"] = (u_wick / close_price) * 100
             
        if l_wick is not None and close_price:
             dest[f"Wick_Lower_Pct{suffix}"] = (l_wick / close_price) * 100

        # --- 7. Hour (Cyclical features if we want, or raw) ---
        # If 'Hour' is in indicators.
        if 'Hour' in indicators:
            dest[f"Hour{suffix}"] = indicators['Hour']

        # --- 8. Phase 2: Robust Indicators ---
        # These are already normalized/stationary from strategy
        for key in ['Log_Return', 'Hist_Vol', 'Slope', 'Acceleration', 'Donchian_Pos', 'Keltner_Pos', 'CCI']:
            val = indicators.get(key)
            if val is not None:
                dest[f"{key}{suffix}"] = val
            elif suffix == "": # Only warn for current bar if missing
                # Optional: Impute 0.0 or 0.5 (for positions) if missing
                pass

