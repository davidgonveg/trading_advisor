import joblib
import json
import pandas as pd
import numpy as np

def check_model():
    model_path = "models/QQQ_XGBoost_classifier.joblib"
    feat_path = "models/QQQ_XGBoost_classifier_features.json"
    
    print(f"Loading model from {model_path}")
    model = joblib.load(model_path)
    
    with open(feat_path, 'r') as f:
        features = json.load(f)
        
    print(f"Model expects {len(features)} features")
    
    import os
    
    # Check live features first
    if os.path.exists("live_features.json"):
        print("Loading live_features.json")
        with open("live_features.json", "r") as f:
            samples = json.load(f)
    else:
        print("Loading golden_sample.json")
        with open("golden_sample.json", "r") as f:
            samples = [json.load(f)]
            
    print(f"Checking {len(samples)} samples...")
    
    probs = []
    
    for i, sample in enumerate(samples):
        # Construct DF in correct order
        row_dict = {}
        for f in features:
            val = sample.get(f)
            if val is None or pd.isna(val):
                val = 0.0
            row_dict[f] = val
            
        df = pd.DataFrame([row_dict])
        prob = model.predict_proba(df)[0][1]
        probs.append(prob)

    probs = np.array(probs)
    
    # Global Stats
    passing = probs > 0.5
    pass_rate = np.mean(passing)
    mean_prob = np.mean(probs)
    
    print(f"\n--- Global Stats ---")
    print(f"Total Samples: {len(probs)}")
    print(f"Pass Rate (>0.5): {pass_rate*100:.2f}% ({np.sum(passing)} trades)")
    print(f"Mean Probability: {mean_prob:.4f}")
    
    # Split Half (Roughly 2024 vs 2025)
    mid = len(probs) // 2
    p1 = probs[:mid]
    p2 = probs[mid:]
    
    print(f"\n--- First Half (Approx 2024) ---")
    print(f"Pass Rate: {np.mean(p1 > 0.5)*100:.2f}%")
    print(f"Mean Prob: {np.mean(p1):.4f}")

    print(f"\n--- Second Half (Approx 2025) ---")
    print(f"Pass Rate: {np.mean(p2 > 0.5)*100:.2f}%")
    print(f"Mean Prob: {np.mean(p2):.4f}")

if __name__ == "__main__":
    check_model()
