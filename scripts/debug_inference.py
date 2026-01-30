import joblib
import pandas as pd
import json
import os
import sys

# Define a sample that SHOULD pass (taken from a successful trade in a baseline audit log if possible, 
# or just a reasonable looking sample based on training data distribution)

# From previous check_audit_values output for QQQ:
# Index 31022: {'VWAP': 635.7, 'Volume_SMA': 2951775, 'ATR': 5.2, ...}
# We need 5 bars of history too.

def debug_inference():
    symbol = "QQQ"
    model_path = f"models/{symbol}_XGBoost_classifier.joblib"
    feat_path = f"models/{symbol}_XGBoost_classifier_features.json"
    data_path = "data/ml/training_data.csv"
    
    if not os.path.exists(model_path):
        print(f"Model not found: {model_path}")
        return

    print(f"Loading model: {model_path}")
    model = joblib.load(model_path)
    
    with open(feat_path, 'r') as f:
        features = json.load(f)

    # LOAD REAL POSITIVE SAMPLE
    print(f"Loading training data from {data_path}...")
    data_df = pd.read_csv(data_path)
    # Filter for symbol and label=1
    pos_samples = data_df[(data_df['symbol'] == symbol) & (data_df['label'] == 1)]
    
    if pos_samples.empty:
        print("No positive samples found for QQQ!")
        return
        
    # Use the first positive sample
    sample_row = pos_samples.iloc[0]
    print("\nReal Sample Features (first 5):")
    print(sample_row[features[:5]])
    
    # Prepare DF
    # The training data already has L1..L5 columns and correct names
    df = pd.DataFrame([sample_row])
    
    # Ensure correct columns order
    df = df[features]
    
    print("\nSample Inputs (Transposed):")
    print(df.T.head(10))
    
    # Predict
    try:
        # Check if it has predict_proba
        if hasattr(model, "predict_proba"):
            probs = model.predict_proba(df)
            print(f"\nPrediction (Probabilities): {probs}")
            print(f"Probability of Class 1: {probs[0][1]:.4f}")
        else:
            pred = model.predict(df)
            print(f"\nPrediction (Class): {pred}")
            
    except Exception as e:
        print(f"\nError predicting: {e}")

if __name__ == "__main__":
    debug_inference()
