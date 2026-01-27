import joblib
import os
import json
import logging
import pandas as pd
from typing import Dict, Any, Optional, List

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
        self.model_type = self.config.get("model_type", "RandomForest")
        self.models = {} # Cache for symbol-specific models
        self.features = {} # Cache for features per model
        
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
                logger.debug(f"ML Model loaded for {key}: {path}")
            except Exception as e:
                logger.error(f"Failed to load ML model {path}: {e}")
        else:
            logger.debug(f"ML Model not found at {path}")

    def predict_proba(self, indicators: Dict[str, Any], symbol: str = "global") -> float:
        """
        Predicts probability of success. Returns 1.0 (pass) if filter is disabled or model fails.
        """
        if not self.enabled:
            return 1.0
            
        key = symbol if (self.per_symbol and symbol in self.models or self._try_load_per_symbol(symbol)) else "global"
        
        if key not in self.models:
            return 1.0 # Pass if no model available
            
        try:
            model = self.models[key]
            feats = self.features[key]
            
            # Prepare row
            row = pd.DataFrame([indicators])
            for f in feats:
                if f not in row.columns:
                    row[f] = 0.0
            row = row[feats]
            
            # Predict
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
