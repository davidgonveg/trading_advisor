import pandas as pd
import numpy as np
import joblib
import os
import json
import logging
from typing import Dict, List, Optional, Any

try:
    from tqdm import tqdm
except ImportError:
    def tqdm(iterable, **kwargs):
        return iterable

# ML Libraries
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ModelFactory:
    """
    Factory to create and train different types of models.
    """
    @staticmethod
    def get_model(model_type: str = "RandomForest", **kwargs):
        if model_type == "RandomForest":
            return RandomForestClassifier(
                n_estimators=kwargs.get("n_estimators", 100),
                max_depth=kwargs.get("max_depth", 10),
                random_state=42
            )
        elif model_type == "XGBoost":
            try:
                from xgboost import XGBClassifier
                return XGBClassifier(
                    n_estimators=kwargs.get("n_estimators", 100),
                    max_depth=kwargs.get("max_depth", 6),
                    random_state=42
                )
            except ImportError:
                logger.error("XGBoost not installed. Falling back to RandomForest.")
                return RandomForestClassifier(random_state=42)
        else:
            logger.warning(f"Unknown model type {model_type}. Using RandomForest.")
            return RandomForestClassifier(random_state=42)

def train_single_model(df: pd.DataFrame, model_type: str, model_path: str, min_samples: int = 50) -> bool:
    """
    Trains a model on the provided dataframe and saves it.
    """
    if len(df) < min_samples:
        logger.warning(f"Not enough samples ({len(df)}) for {os.path.basename(model_path)}. Min required: {min_samples}")
        return False

    # 1. Feature Selection
    drop_cols = ['symbol', 'strategy', 'timestamp', 'side', 'pnl', 'label']
    features = df.drop(columns=[c for c in drop_cols if c in df.columns])
    target = df['label']

    # 2. Preprocessing
    features = features.fillna(0)
    
    # 3. Split
    try:
        X_train, X_test, y_train, y_test = train_test_split(features, target, test_size=0.2, random_state=42)
    except ValueError as e:
        logger.error(f"Error splitting data: {e}")
        return False

    # 4. Train
    model = ModelFactory.get_model(model_type)
    model.fit(X_train, y_train)

    # 5. Evaluate
    y_pred = model.predict(X_test)
    acc = accuracy_score(y_test, y_pred)
    
    logger.info(f"Model {os.path.basename(model_path)} | Accuracy: {acc:.2f} | Samples: {len(df)}")
    
    # 6. Save
    os.makedirs(os.path.dirname(model_path), exist_ok=True)
    joblib.dump(model, model_path)
    
    # Save features
    feat_path = model_path.replace(".joblib", "_features.json")
    with open(feat_path, 'w') as f:
        json.dump(list(features.columns), f)
        
    return True

def train_pipeline(data_path="data/ml/training_data.csv", 
                   model_type="RandomForest", 
                   per_symbol=False,
                   min_samples=50):
    """
    Main pipeline to train models.
    """
    if not os.path.exists(data_path):
        logger.error(f"Data file not found: {data_path}")
        return

    logger.info(f"Starting training pipeline. Type: {model_type} | Per-Symbol: {per_symbol}")
    df = pd.read_csv(data_path)

    if per_symbol:
        symbols = df['symbol'].unique()
        for sym in tqdm(symbols, desc="Training per-symbol models"):
            sym_df = df[df['symbol'] == sym]
            model_path = f"models/{sym}_{model_type}_classifier.joblib"
            train_single_model(sym_df, model_type, model_path, min_samples)
    else:
        model_path = f"models/global_{model_type}_classifier.joblib"
        train_single_model(df, model_type, model_path, min_samples)

if __name__ == "__main__":
    # You can customize these params or load them from a config
    train_pipeline(per_symbol=True, model_type="RandomForest")
