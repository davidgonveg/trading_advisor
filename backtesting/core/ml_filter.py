import joblib
import os
import json
import logging
import pandas as pd
import numpy as np
from typing import Dict, Any, Optional, List
from .features import FeatureEngineer

logger = logging.getLogger("backtesting.core.ml_filter")

class MLFilter:
    """
    Loads trained ML models and provides filtering services for backtesting.
    Supports global or per-symbol models.
    """
    def __init__(self, config: Dict[str, Any]):
        self.config = config.get("ml_filter", {})
        self.enabled = self.config.get("enabled", False)
        self.per_symbol = self.config.get("per_symbol", False)
        self.model_type = config.get("model_type", "XGBoost")
        self.models = {} # Cache for symbol-specific models
        self.features = {} # Cache for features per model
        self._warned_symbols = set() # To prevent log spam
        
        # Load global model if per_symbol is False
        if not self.per_symbol and self.enabled:
            model_path = self.config.get("model_path", f"models/global_{self.model_type}_classifier.joblib")
            self._load_model("global", model_path)

    def _load_model(self, key: str, path: str):
        """Helper to load a model and its features."""
        if os.path.exists(path):
            try:
                self.models[key] = joblib.load(path)
                feat_path = path.replace(".joblib", "_features.json")
                with open(feat_path, 'r') as f:
                    self.features[key] = json.load(f)
                logger.info(f"✅ ML Model loaded for {key}: {path} ({len(self.features[key])} features)")
            except Exception as e:
                logger.error(f"❌ Failed to load ML model {path}: {e}")
        else:
            logger.warning(f"⚠️ ML Model not found at {path}")

    def predict_proba(self, indicators: Dict[str, Any], history: List[Dict[str, Any]], symbol: str = "global") -> float:
        """
        Predicts probability of success using FeatureEngineer for consistent extraction.
        """
        if not self.enabled:
            return 1.0
            
        key = symbol if (self.per_symbol and symbol in self.models or self._try_load_per_symbol(symbol)) else "global"
        
        if key not in self.models:
            # Log warning only once per symbol to avoid spam
            if not hasattr(self, '_warned_symbols'):
                self._warned_symbols = set()
            if key not in self._warned_symbols:
                logger.warning(f"⚠️ ML Model not found for '{key}' (model_type={self.model_type}) - FILTER DISABLED for this symbol")
                self._warned_symbols.add(key)
            return 1.0 # Pass if no model available
            
        try:
            model = self.models[key]
            expected_feats = self.features[key]
            
            # --- EXTRACT FEATURES via Shared Logic ---
            features_dict = FeatureEngineer.extract_features(indicators, history)
            
            # Align with model columns
            # We must ensure the DataFrame has exactly the columns the model expects
            # Missing features -> NaN (XGBoost handles this)
            # Extra features -> Ignored
            
            row_dict = {}
            for feat in expected_feats:
                # Default to NaN if missing, XGBoost handles it.
                row_dict[feat] = features_dict.get(feat, np.nan)
                
            # Create DataFrame
            row = pd.DataFrame([row_dict])
            
            # Predict
            if len(self._warned_symbols) < 30: # Limit spam
                 logger.info(f"ML INPUT {symbol}: NATR={row_dict.get('NATR'):.4f}, Dist_VWAP={row_dict.get('Dist_VWAP'):.4f}, RSI={row_dict.get('RSI'):.4f}, WickU={row_dict.get('Wick_Upper_Pct'):.4f}")
            
            probs = model.predict_proba(row)[0]
            
            return float(probs[1]) # Index 1 is success (label 1)
        except Exception as e:
            logger.error(f"Prediction error for {symbol}: {e}")
            return 1.0 # Fail-safe pass

    def _try_load_per_symbol(self, symbol: str) -> bool:
        """Attempts to load a symbol-specific model on the fly."""
        if not self.per_symbol:
            return False
            
        model_path = f"models/{symbol}_{self.model_type}_classifier.joblib"
        self._load_model(symbol, model_path)
        return symbol in self.models
