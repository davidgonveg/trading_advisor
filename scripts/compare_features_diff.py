import json
import pandas as pd
import numpy as np

def run_comparison():
    # Load Golden Sample
    try:
        with open("golden_sample.json", "r") as f:
            golden = json.load(f)
    except FileNotFoundError:
        print("Error: golden_sample.json not found")
        return

    # Load Live Features
    try:
        with open("live_features.json", "r") as f:
            live_list = json.load(f)
    except FileNotFoundError:
        print("Error: live_features.json not found")
        return

    print(f"Loaded Golden Sample (TS: {golden.get('timestamp')})")
    print(f"Loaded {len(live_list)} Live Features")

    # Find Best Match (by VWAP similarity)
    # Golden VWAP
    g_vwap = golden.get('VWAP')
    
    if g_vwap is None:
        print("Error: Golden sample has no VWAP")
        return

    best_match = None
    min_diff = float('inf')

    if len(live_list) > 1:
        print("Forcing comparison with Entry 2 (Index 1) as it appears to be the correct timestamp")
        best_match = live_list[1]
        
        # Recalculate diff for logging
        l_vwap = best_match.get('VWAP')
        if l_vwap and g_vwap:
            min_diff = abs(l_vwap - g_vwap)
    else:
        # Fallback to loop logic
        for live in live_list:

    if min_diff > 1.0:
        print(f"Warning: Best match VWAP diff is large ({min_diff:.2f}). Might not be same bar.")
    else:
        print(f"Found Match! VWAP Diff: {min_diff:.4f}")

    if not best_match:
        print("No match found")
        return

    # Compare Keys
    print("\n--- Feature Comparison (Diff > 0.0001) ---")
    
    all_keys = set(golden.keys()) | set(best_match.keys())
    # Ignored keys
    ignored = {'timestamp', 'label', 'pnl', 'feature_id', 'is_filled', 'source', 'symbol', 'strategy', 'side', 'quantity', 'stop_loss', 'take_profit'}
    
    mismatches = []
    
    for k in sorted(all_keys):
        if k in ignored: continue
        
        v_g = golden.get(k)
        v_l = best_match.get(k)
        
        # Handle types
        try:
            val_g = float(v_g) if v_g is not None else np.nan
            val_l = float(v_l) if v_l is not None else np.nan
        except:
            continue
            
        # Check diff
        if np.isnan(val_g) and np.isnan(val_l):
            continue
        elif np.isnan(val_g) or np.isnan(val_l):
            mismatches.append(f"{k}: Golden={v_g} | Live={v_l} (NaN Mismatch)")
        else:
            diff = abs(val_g - val_l)
            if diff > 0.0001:
                # percentage error if possible
                pct = (diff / abs(val_g)) * 100 if val_g != 0 else diff
                mismatches.append(f"{k}: Golden={val_g:.4f} | Live={val_l:.4f} | Diff={diff:.4f} ({pct:.1f}%)")

    if mismatches:
        for m in mismatches:
            print(m)
    else:
        print("PERFECT MATCH! No significant differences found.")

if __name__ == "__main__":
    run_comparison()
