import sys
from pathlib import Path
import json
import pandas as pd
import logging

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from backtesting.main import BacktestEngine
from backtesting.core.ml_filter import MLFilter
from backtesting.core.data_loader import DataLoader
from backtesting.strategies.vwap_bounce import VWAPBounce
from backtesting.core.features import FeatureEngineer

# Target info
TARGET_SYMBOL = "QQQ"
# TARGET_TIMESTAMP = "2025-10-29"

# Monkey patch predict_proba
original_predict = MLFilter.predict_proba
CAPTURED_FEATURES = []

def intercepted_predict_proba(self, indicators, history, symbol="global"):
    # Capture features using the exact same logic as MLFilter
    try:
        features_dict = FeatureEngineer.extract_features(indicators, history)
        if symbol == TARGET_SYMBOL:
            CAPTURED_FEATURES.append(features_dict)
    except Exception as e:
        print(f"Debug Capture Error: {e}")

    # CALL ORIGINAL (which uses FeatureEngineer internally now too)
    prob = original_predict(self, indicators, history, symbol)
    
    if symbol == TARGET_SYMBOL:
        print(f"DEBUG PROB for {symbol}: {prob:.4f}")
        
    return prob

# Patch it
MLFilter.predict_proba = intercepted_predict_proba

def run_debug():
    config_dict = {
        "backtesting": {
            "initial_capital": 100000.0,
            "commission": 5e-05,
            "slippage": 0.0005,
            "start_date": "2025-10-25", # Short window around failure
            "end_date": "2025-10-31", 
            "interval": "1h",
            "symbols": ["QQQ"]
        },
        "strategies": {
            "vwap_bounce": {
              "risk_pct": 0.015,
              "atr_period": 14,
              "atr_multiplier_sl": 2.0,
              "atr_multiplier_tp": 4.0,
              "volume_sma": 20
            }
        },
        "ml_filter": {
            "enabled": True,
            "per_symbol": True,
            "model_type": "XGBoost",
            "model_path": "models/", 
            "threshold": 0.2, # Low threshold to see if ANY pass
            "lookback": 5,
            "min_samples": 50
        },
        "logging": {"console": {"enabled": True, "level": "INFO"}}
    }
    
    try:
        # Filter data for speed
        start = pd.Timestamp("2024-01-01").tz_localize("UTC") # Long Warmup needed for indicators
        end = pd.Timestamp("2025-10-31").tz_localize("UTC")
        
        # Load Data
        loader = DataLoader() # Uses default DB
        data = loader.load_data("QQQ", "1h", start, end)
        
        if data.empty:
            print("Error: No data found for QQQ in debug range")
            return
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Data Load Error: {e}")
        return

    # Run Engine
    engine = BacktestEngine(config=config_dict)
    
    # Preload model
    print("Preloading QQQ model...")
    engine.ml_filter._load_model("QQQ", "models/QQQ_XGBoost_classifier.joblib")
    
    # Initialize strategy
    strat = VWAPBounce()
    engine.set_strategy(strat, config_dict["strategies"]["vwap_bounce"])
        
    try:
        engine.run("QQQ", data)
    except SystemExit:
        pass
    except Exception as e:
        import traceback
        traceback.print_exc()
        # print(f"Error: {e}")
        
    # Save all captured
    if CAPTURED_FEATURES:
        print(f"Saving {len(CAPTURED_FEATURES)} captured vectors to live_features.json")
        with open("live_features.json", "w") as f:
            json.dump(CAPTURED_FEATURES, f, indent=2)

if __name__ == "__main__":
    run_debug()
