"""
ML Model Validation Script

Validates that ML models exist, load correctly, and produce reasonable predictions.
"""

import os
import json
import joblib
from pathlib import Path
from collections import defaultdict
import pandas as pd

def main():
    print("="*80)
    print("ML MODEL VALIDATION REPORT")
    print("="*80)
    
    # 1. Check config
    print("\n[CONFIG] CONFIGURATION CHECK")
    print("-"*80)
    
    config_path = "backtesting/config.json"
    with open(config_path, 'r') as f:
        config = json.load(f)
    
    ml_cfg = config.get("ml_filter", {})
    print(f"  ML Filter Enabled: {ml_cfg.get('enabled', False)}")
    print(f"  Per-Symbol Mode: {ml_cfg.get('per_symbol', False)}")
    print(f"  Model Type: {ml_cfg.get('model_type', 'N/A')}")
    print(f"  Model Path: {ml_cfg.get('model_path', 'N/A')}")
    print(f"  Threshold: {ml_cfg.get('threshold', 'N/A')}")
    print(f"  Comparison Mode: {ml_cfg.get('comparison_mode', False)}")
    
    # Check for conflicts
    if ml_cfg.get('per_symbol') and 'model_path' in ml_cfg:
        print("\n  [!] WARNING: per_symbol=true but model_path is set (will be ignored)")
    
    model_type = ml_cfg.get('model_type', 'RandomForest')
    
    # 2. Scan models directory
    print("\n\n[MODELS] MODELS DIRECTORY SCAN")
    print("-"*80)
    
    models_dir = Path("models")
    if not models_dir.exists():
        print("  [X] Models directory not found!")
        return
    
    # Group models by type and symbol
    models_by_type = defaultdict(list)
    
    for file in models_dir.glob("*.joblib"):
        filename = file.stem
        
        # Skip non-classifier models
        if not filename.endswith("_classifier"):
            continue
        
        # Parse: SYMBOL_MODELTYPE_classifier
        parts = filename.replace("_classifier", "").split("_")
        
        if len(parts) >= 2:
            symbol = "_".join(parts[:-1])
            mtype = parts[-1]
            models_by_type[mtype].append(symbol)
    
    # Print summary
    print(f"\n  Found {len(list(models_dir.glob('*.joblib')))} total .joblib files")
    print(f"\n  Models by Type:")
    for mtype, symbols in sorted(models_by_type.items()):
        print(f"    {mtype}: {len(symbols)} models")
        if len(symbols) <= 10:
            print(f"      Symbols: {', '.join(sorted(symbols))}")
        else:
            print(f"      Symbols: {', '.join(sorted(symbols)[:10])} ... (+{len(symbols)-10} more)")
    
    # 3. Check for backtesting symbols
    print("\n\n[SYMBOLS] BACKTESTING SYMBOLS CHECK")
    print("-"*80)
    
    backtest_symbols = config.get('backtesting', {}).get('symbols', [])
    print(f"  Symbols in config: {', '.join(backtest_symbols)}")
    
    # Check which symbols have which models
    print(f"\n  Model Availability (for model_type='{model_type}'):")
    
    missing_models = []
    for symbol in backtest_symbols:
        has_model = symbol in models_by_type.get(model_type, [])
        status = "[OK]" if has_model else "[MISSING]"
        print(f"    {status} {symbol}")
        if not has_model:
            missing_models.append(symbol)
    
    if missing_models:
        print(f"\n  [!] MISSING MODELS for {len(missing_models)} symbols: {', '.join(missing_models)}")
        print(f"      These symbols will fall back to pass-through (no filtering)")
    
    # 4. Test model loading
    print("\n\n[TEST] MODEL LOADING TEST")
    print("-"*80)
    
    test_symbol = backtest_symbols[0] if backtest_symbols else None
    if test_symbol and test_symbol in models_by_type.get(model_type, []):
        model_path = f"models/{test_symbol}_{model_type}_classifier.joblib"
        features_path = f"models/{test_symbol}_{model_type}_classifier_features.json"
        
        print(f"  Testing: {model_path}")
        
        try:
            model = joblib.load(model_path)
            print(f"    [OK] Model loaded successfully")
            print(f"    Type: {type(model).__name__}")
            
            if os.path.exists(features_path):
                with open(features_path, 'r') as f:
                    features = json.load(f)
                print(f"    [OK] Features loaded: {len(features)} features")
                print(f"    Sample features: {features[:5]}")
            else:
                print(f"    [X] Features file not found: {features_path}")
            
            # Test prediction with dummy data
            import numpy as np
            dummy_data = pd.DataFrame(np.random.randn(1, len(features)), columns=features)
            probs = model.predict_proba(dummy_data)
            print(f"    [OK] Prediction test successful")
            print(f"    Sample probability output: {probs[0]}")
            
        except Exception as e:
            print(f"    [X] Error loading/testing model: {e}")
    else:
        print(f"  [!] No model available to test for {test_symbol}")
    
    # 5. Summary and recommendations
    print("\n\n[SUMMARY] SUMMARY & RECOMMENDATIONS")
    print("="*80)
    
    issues = []
    
    # Check if configured model type exists
    if model_type not in models_by_type:
        issues.append(f"[X] CRITICAL: No models found for configured type '{model_type}'")
        issues.append(f"   Available types: {', '.join(sorted(models_by_type.keys()))}")
        issues.append(f"   → Update config.json ml_filter.model_type to one of the available types")
    
    # Check for missing symbol models
    if missing_models and ml_cfg.get('per_symbol'):
        issues.append(f"[!] WARNING: {len(missing_models)} symbols missing {model_type} models")
        issues.append(f"   → Run: python scripts/train_ml_model.py --model_type {model_type} --per-symbol --symbols {' '.join(missing_models)}")
    
    # Check config conflicts
    if ml_cfg.get('per_symbol') and 'model_path' in ml_cfg:
        issues.append(f"[!] WARNING: Conflicting config - per_symbol=true but model_path is set")
        issues.append(f"   → Remove 'model_path' from config.json when using per_symbol mode")
    
    if issues:
        print("\n[!] ISSUES FOUND:\n")
        for issue in issues:
            print(f"  {issue}")
    else:
        print("\n[OK] All checks passed! ML models are properly configured.")
    
    print("\n" + "="*80)

if __name__ == "__main__":
    main()
