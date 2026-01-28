import pandas as pd
import numpy as np
import joblib
import os
import json
import logging
import time
from typing import Dict, List, Tuple
from pathlib import Path

try:
    from tqdm import tqdm
except ImportError:
    def tqdm(iterable, **kwargs):
        return iterable

# ML Libraries
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, 
    f1_score, roc_auc_score, classification_report
)

# Import ModelFactory
import sys
sys.path.append(str(Path(__file__).parent))
from train_ml_model import ModelFactory

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def train_and_evaluate_model(
    model_type: str, 
    X_train: pd.DataFrame, 
    X_test: pd.DataFrame, 
    y_train: pd.Series, 
    y_test: pd.Series
) -> Dict:
    """
    Train a model and return evaluation metrics.
    """
    logger.info(f"Training {model_type}...")
    
    # Get model
    model = ModelFactory.get_model(model_type)
    
    # Train
    start_time = time.time()
    model.fit(X_train, y_train)
    train_time = time.time() - start_time
    
    # Predict
    y_pred = model.predict(X_test)
    y_pred_proba = model.predict_proba(X_test)[:, 1] if hasattr(model, 'predict_proba') else None
    
    # Calculate metrics
    metrics = {
        'model_type': model_type,
        'accuracy': accuracy_score(y_test, y_pred),
        'precision': precision_score(y_test, y_pred, zero_division=0),
        'recall': recall_score(y_test, y_pred, zero_division=0),
        'f1_score': f1_score(y_test, y_pred, zero_division=0),
        'roc_auc': roc_auc_score(y_test, y_pred_proba) if y_pred_proba is not None else 0.0,
        'train_time': train_time,
        'model': model
    }
    
    logger.info(f"{model_type} - Accuracy: {metrics['accuracy']:.4f}, F1: {metrics['f1_score']:.4f}, Time: {train_time:.2f}s")
    
    return metrics


def compare_models(
    data_path: str = "data/ml/training_data.csv",
    models: List[str] = None,
    per_symbol: bool = False,
    output_dir: str = "results"
) -> pd.DataFrame:
    """
    Compare multiple ML models on the same dataset.
    """
    if models is None:
        models = ["RandomForest", "XGBoost", "LightGBM", "CatBoost"]
    
    if not os.path.exists(data_path):
        logger.error(f"Data file not found: {data_path}")
        return None
    
    logger.info(f"Loading data from {data_path}...")
    df = pd.read_csv(data_path)
    
    # Feature selection
    drop_cols = ['symbol', 'strategy', 'timestamp', 'side', 'pnl', 'label']
    features = df.drop(columns=[c for c in drop_cols if c in df.columns])
    target = df['label']
    
    # Preprocessing
    features = features.fillna(0)
    
    logger.info(f"Dataset: {len(df)} samples, {len(features.columns)} features")
    logger.info(f"Class distribution: {target.value_counts().to_dict()}")
    
    # Split data
    X_train, X_test, y_train, y_test = train_test_split(
        features, target, test_size=0.2, random_state=42, stratify=target
    )
    
    # Train and evaluate each model
    results = []
    for model_type in models:
        try:
            metrics = train_and_evaluate_model(model_type, X_train, X_test, y_train, y_test)
            results.append(metrics)
        except Exception as e:
            logger.error(f"Error training {model_type}: {e}")
            continue
    
    if not results:
        logger.error("No models were successfully trained!")
        return None
    
    # Create results DataFrame
    results_df = pd.DataFrame([
        {
            'Model': r['model_type'],
            'Accuracy': r['accuracy'],
            'Precision': r['precision'],
            'Recall': r['recall'],
            'F1-Score': r['f1_score'],
            'ROC-AUC': r['roc_auc'],
            'Train Time (s)': r['train_time']
        }
        for r in results
    ])
    
    # Sort by F1-Score
    results_df = results_df.sort_values('F1-Score', ascending=False)
    
    # Print results
    print("\n" + "="*80)
    print("MODEL COMPARISON RESULTS")
    print("="*80)
    print(results_df.to_string(index=False))
    print("="*80)
    
    # Find best model
    best_idx = results_df['F1-Score'].idxmax()
    best_model_name = results_df.loc[best_idx, 'Model']
    best_f1 = results_df.loc[best_idx, 'F1-Score']
    
    print(f"\n🏆 Best Model: {best_model_name} (F1-Score: {best_f1:.4f})")
    
    # Save results
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, "model_comparison.txt")
    
    with open(output_file, 'w') as f:
        f.write("="*80 + "\n")
        f.write("MODEL COMPARISON RESULTS\n")
        f.write("="*80 + "\n")
        f.write(results_df.to_string(index=False) + "\n")
        f.write("="*80 + "\n")
        f.write(f"\nBest Model: {best_model_name} (F1-Score: {best_f1:.4f})\n")
    
    logger.info(f"Results saved to {output_file}")
    
    # Save best model
    best_model = [r for r in results if r['model_type'] == best_model_name][0]['model']
    best_model_path = os.path.join("models", f"best_{best_model_name}_classifier.joblib")
    os.makedirs("models", exist_ok=True)
    joblib.dump(best_model, best_model_path)
    
    # Save features
    feat_path = best_model_path.replace(".joblib", "_features.json")
    with open(feat_path, 'w') as f:
        json.dump(list(features.columns), f)
    
    logger.info(f"Best model saved to {best_model_path}")
    
    return results_df


def compare_per_symbol(
    data_path: str = "data/ml/training_data.csv",
    models: List[str] = None,
    output_dir: str = "results"
) -> Dict[str, pd.DataFrame]:
    """
    Compare models for each symbol separately.
    """
    if models is None:
        models = ["RandomForest", "XGBoost", "LightGBM", "CatBoost"]
    
    if not os.path.exists(data_path):
        logger.error(f"Data file not found: {data_path}")
        return None
    
    logger.info(f"Loading data from {data_path}...")
    df = pd.read_csv(data_path)
    
    symbols = df['symbol'].unique()
    logger.info(f"Found {len(symbols)} symbols: {list(symbols)}")
    
    all_results = {}
    
    for symbol in tqdm(symbols, desc="Comparing models per symbol"):
        logger.info(f"\n{'='*60}")
        logger.info(f"Symbol: {symbol}")
        logger.info(f"{'='*60}")
        
        symbol_df = df[df['symbol'] == symbol]
        
        if len(symbol_df) < 50:
            logger.warning(f"Skipping {symbol} - insufficient samples ({len(symbol_df)})")
            continue
        
        # Feature selection
        drop_cols = ['symbol', 'strategy', 'timestamp', 'side', 'pnl', 'label']
        features = symbol_df.drop(columns=[c for c in drop_cols if c in symbol_df.columns])
        target = symbol_df['label']
        
        # Preprocessing
        features = features.fillna(0)
        
        # Split data
        try:
            X_train, X_test, y_train, y_test = train_test_split(
                features, target, test_size=0.2, random_state=42, stratify=target
            )
        except ValueError as e:
            logger.warning(f"Skipping {symbol} - {e}")
            continue
        
        # Train and evaluate each model
        results = []
        for model_type in models:
            try:
                metrics = train_and_evaluate_model(model_type, X_train, X_test, y_train, y_test)
                results.append(metrics)
            except Exception as e:
                logger.error(f"Error training {model_type} for {symbol}: {e}")
                continue
        
        if not results:
            logger.warning(f"No models trained successfully for {symbol}")
            continue
        
        # Create results DataFrame
        results_df = pd.DataFrame([
            {
                'Model': r['model_type'],
                'Accuracy': r['accuracy'],
                'F1-Score': r['f1_score'],
                'ROC-AUC': r['roc_auc']
            }
            for r in results
        ])
        
        results_df = results_df.sort_values('F1-Score', ascending=False)
        all_results[symbol] = results_df
        
        # Print results for this symbol
        print(f"\n{symbol}:")
        print(results_df.to_string(index=False))
        
        # Find and save best model for this symbol
        best_idx = results_df['F1-Score'].idxmax()
        best_model_name = results_df.loc[best_idx, 'Model']
        best_model = [r for r in results if r['model_type'] == best_model_name][0]['model']
        
        model_path = os.path.join("models", f"{symbol}_{best_model_name}_classifier.joblib")
        joblib.dump(best_model, model_path)
        
        feat_path = model_path.replace(".joblib", "_features.json")
        with open(feat_path, 'w') as f:
            json.dump(list(features.columns), f)
    
    # Save summary
    os.makedirs(output_dir, exist_ok=True)
    summary_file = os.path.join(output_dir, "per_symbol_comparison.txt")
    
    with open(summary_file, 'w') as f:
        f.write("="*80 + "\n")
        f.write("PER-SYMBOL MODEL COMPARISON\n")
        f.write("="*80 + "\n\n")
        
        for symbol, results_df in all_results.items():
            f.write(f"\n{symbol}:\n")
            f.write(results_df.to_string(index=False) + "\n")
            f.write("-"*60 + "\n")
    
    logger.info(f"Per-symbol results saved to {summary_file}")
    
    return all_results


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Compare ML models for trading")
    parser.add_argument("--data", type=str, default="data/ml/training_data.csv", help="Path to training data")
    parser.add_argument("--per-symbol", action="store_true", help="Compare models per symbol")
    parser.add_argument("--models", nargs="+", default=["RandomForest", "XGBoost", "LightGBM", "CatBoost"], 
                        help="Models to compare")
    parser.add_argument("--output", type=str, default="results", help="Output directory")
    
    args = parser.parse_args()
    
    if args.per_symbol:
        compare_per_symbol(args.data, args.models, args.output)
    else:
        compare_models(args.data, args.models, args.per_symbol, args.output)
