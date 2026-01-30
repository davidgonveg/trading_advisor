import pandas as pd
import joblib
import os
import json
import numpy as np
from collections import Counter
import sys
from pathlib import Path

# Add root to sys.path
sys.path.append(str(Path(__file__).parent.parent))

def analyze_model_probs():
    data_path = "data/ml/training_data.csv"
    if not os.path.exists(data_path):
        print(f"❌ Data file not found: {data_path}")
        return

    print(f"Loading data from {data_path}...")
    df = pd.read_csv(data_path)
    print(f"Total samples: {len(df)}")
    
    # Check Class Balance
    labels = df['label'].value_counts()
    print(f"\nClass Balance:\n{labels}")
    print(f"Positive Rate: {labels.get(1, 0) / len(df):.2%}")

    # Check for per-symbol models or global
    # We'll check the 'models' directory
    model_dir = "models"
    model_files = [f for f in os.listdir(model_dir) if f.endswith(".joblib") and "classifier" in f]
    
    if not model_files:
        print("❌ No models found in 'models/' directory.")
        return

    print(f"\nFound {len(model_files)} models. Analyzing each...")

    for model_file in model_files:
        model_path = os.path.join(model_dir, model_file)
        
        # Determine if it's a symbol specific model
        # Filename format: {symbol}_{type}_classifier.joblib or global_{type}_classifier.joblib
        parts = model_file.split('_')
        symbol = parts[0]
        model_type = parts[1] # e.g. XGBoost, RandomForest
        
        print(f"\n{'='*60}")
        print(f"Model: {model_file} (Symbol: {symbol}, Type: {model_type})")
        print(f"{'='*60}")

        try:
            model = joblib.load(model_path)
        except Exception as e:
            print(f"❌ Failed to load model: {e}")
            continue

        # Load features
        feat_path = model_path.replace(".joblib", "_features.json")
        if not os.path.exists(feat_path):
            print(f"⚠️ Features file not found: {feat_path}. Skipping.")
            continue
            
        with open(feat_path, 'r') as f:
            features_list = json.load(f)

        # Filter data for this symbol if specific
        if symbol != "global":
            target_df = df[df['symbol'] == symbol].copy()
            if target_df.empty:
                print(f"⚠️ No training data found for {symbol}. Skipping.")
                continue
        else:
            target_df = df.copy()

        print(f"Testing on {len(target_df)} samples...")

        # Prepare Features
        # Fill missing features with 0
        X = target_df.copy()
        
        # Ensure all model features exist
        for feat in features_list:
            if feat not in X.columns:
                X[feat] = 0.0
                
        X = X[features_list]
        X = X.fillna(0) # Safety fill

        # Predict Probs
        try:
            if hasattr(model, "predict_proba"):
                probs = model.predict_proba(X)[:, 1] # Probability of class 1
            else:
                print("❌ Model does not support predict_proba.")
                continue
        except Exception as e:
            print(f"❌ Prediction error: {e}")
            continue

        # Analysis
        p_min, p_max, p_mean = probs.min(), probs.max(), probs.mean()
        p_50, p_75, p_90, p_95 = np.percentile(probs, [50, 75, 90, 95])
        
        print(f"\nProbability Stats:")
        print(f"  Min: {p_min:.4f}")
        print(f"  Max: {p_max:.4f}")
        print(f"  Mean: {p_mean:.4f}")
        print(f"  Median: {p_50:.4f}")
        print(f"  75th: {p_75:.4f}")
        print(f"  90th: {p_90:.4f}")
        
        # Threshold Analysis
        print("\nPass Rates at Thresholds:")
        thresholds = [0.3, 0.4, 0.5, 0.55, 0.6, 0.7]
        for t in thresholds:
            passed = (probs > t).sum()
            rate = passed / len(probs)
            print(f"  > {t:.2f}: {passed} signals ({rate:.2%})")

        # Histogram
        print("\nDistribution (Histogram):")
        hist, bin_edges = np.histogram(probs, bins=10, range=(0, 1))
        for i in range(10):
            range_str = f"{bin_edges[i]:.1f}-{bin_edges[i+1]:.1f}"
            bar = "#" * int(hist[i] / len(probs) * 50) # Scale to 50 chars
            print(f"  {range_str}: {hist[i]:<5} {bar}")

if __name__ == "__main__":
    analyze_model_probs()
