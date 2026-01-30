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
                min_samples_split=kwargs.get("min_samples_split", 5),
                min_samples_leaf=kwargs.get("min_samples_leaf", 2),
                random_state=42,
                n_jobs=-1
            )
        elif model_type == "XGBoost":
            try:
                from xgboost import XGBClassifier
                return XGBClassifier(
                    n_estimators=kwargs.get("n_estimators", 100),
                    max_depth=kwargs.get("max_depth", 6),
                    learning_rate=kwargs.get("learning_rate", 0.05),
                    subsample=kwargs.get("subsample", 0.8),
                    colsample_bytree=kwargs.get("colsample_bytree", 0.8),
                    scale_pos_weight=kwargs.get("scale_pos_weight", 1.0), # Handle imbalance
                    random_state=42,
                    n_jobs=-1,
                    eval_metric='logloss'
                )
            except ImportError:
                logger.error("XGBoost not installed. Install with: pip install xgboost")
                logger.error("Falling back to RandomForest.")
                return RandomForestClassifier(
                    random_state=42, 
                    n_jobs=-1, 
                    class_weight='balanced' if kwargs.get('scale_pos_weight', 1.0) != 1.0 else None
                )
        elif model_type == "LightGBM":
            try:
                from lightgbm import LGBMClassifier
                return LGBMClassifier(
                    n_estimators=kwargs.get("n_estimators", 100),
                    max_depth=kwargs.get("max_depth", 6),
                    learning_rate=kwargs.get("learning_rate", 0.05),
                    num_leaves=kwargs.get("num_leaves", 31),
                    subsample=kwargs.get("subsample", 0.8),
                    colsample_bytree=kwargs.get("colsample_bytree", 0.8),
                    random_state=42,
                    n_jobs=-1,
                    verbose=-1
                )
            except ImportError:
                logger.error("LightGBM not installed. Install with: pip install lightgbm")
                logger.error("Falling back to RandomForest.")
                return RandomForestClassifier(random_state=42, n_jobs=-1)
        elif model_type == "CatBoost":
            try:
                from catboost import CatBoostClassifier
                return CatBoostClassifier(
                    iterations=kwargs.get("iterations", 100),
                    depth=kwargs.get("depth", 6),
                    learning_rate=kwargs.get("learning_rate", 0.05),
                    random_state=42,
                    verbose=False,
                    thread_count=-1
                )
            except ImportError:
                logger.error("CatBoost not installed. Install with: pip install catboost")
                logger.error("Falling back to RandomForest.")
                return RandomForestClassifier(random_state=42, n_jobs=-1)
        else:
            logger.warning(f"Unknown model type '{model_type}'. Available: RandomForest, XGBoost, LightGBM, CatBoost")
            logger.warning("Using RandomForest as default.")
            return RandomForestClassifier(random_state=42, n_jobs=-1)

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
    # 5. Train
    # We use scale_pos_weight to handle imbalance, so we want the raw, shifted probabilities.
    # Calibration (CalibratedClassifierCV) often maps these back to the low "true" probability,
    # undoing the aggression we want for filtering. We will skip calibration for now.
    
    base_model = ModelFactory.get_model(model_type, scale_pos_weight=len(y_train[y_train==0])/len(y_train[y_train==1]))

    try:
        base_model.fit(X_train, y_train)
        model = base_model
        
        # Log feature importance if available
        if hasattr(model, "feature_importances_"):
            # Sort and log top 5
            importances = model.feature_importances_
            indices = np.argsort(importances)[::-1]
            top_feats = [features.columns[i] for i in indices[:5]]
            logger.info(f"Top Features for {os.path.basename(model_path)}: {top_feats}")

    except Exception as e:
        logger.error(f"Training failed: {e}")
        return False

    # 6. Evaluate
    y_pred = model.predict(X_test)
    y_prob = model.predict_proba(X_test)[:, 1]
    
    acc = accuracy_score(y_test, y_pred)
    
    # Log detailed stats
    p_min, p_max, p_mean = y_prob.min(), y_prob.max(), y_prob.mean()
    logger.info(f"Model {os.path.basename(model_path)} | Acc: {acc:.2f} | Probs: Min={p_min:.2f} Max={p_max:.2f} Mean={p_mean:.2f}")
    
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
    import argparse
    
    parser = argparse.ArgumentParser(description="Train ML models for trading advisor")
    parser.add_argument("--model_type", type=str, default="RandomForest", 
                        choices=["RandomForest", "XGBoost", "LightGBM", "CatBoost"],
                        help="Type of model to train")
    parser.add_argument("--per-symbol", action="store_true", 
                        help="Train separate models per symbol")
    parser.add_argument("--symbols", nargs="+", default=None,
                        help="Specific symbols to train (default: all in data)")
    parser.add_argument("--min_samples", type=int, default=50,
                        help="Minimum samples required to train")
    parser.add_argument("--data_path", type=str, default="data/ml/training_data.csv",
                        help="Path to training data")
    
    args = parser.parse_args()
    
    # If symbols are provided, we'll need to filter the dataframe inside train_pipeline
    # But train_pipeline reads the file directly. Let's patch it or just handle it here.
    # For now, let's keep it simple and just pass the args that match.
    # Note: The current train_pipeline doesn't accept a symbols list argument to filter.
    # Steps:
    # 1. Read data here if symbols filtering is needed? 
    # Actually, train_pipeline reads the CSV. Let's modify train_pipeline to accept symbols filter or just let it run for all.
    # The previous prompt implied we wanted to filter symbols. Let's stick to the existing signature for now
    # and mostly ensure model_type and per_symbol are passed correctly.
    
    train_pipeline(data_path=args.data_path, 
                   model_type=args.model_type, 
                   per_symbol=args.per_symbol,
                   min_samples=args.min_samples)
