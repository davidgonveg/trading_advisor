"""
Quick ML Backtesting Test

Runs a single symbol backtest to verify ML filter is working correctly.
"""

import sys
import json
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from backtesting.main import main as run_backtest

if __name__ == "__main__":
    print("="*80)
    print("QUICK ML FILTER TEST")
    print("="*80)
    print("\nThis will run a quick backtest on QQQ to verify ML filter is working.")
    print("Expected behavior:")
    print("  - ML model should load successfully")
    print("  - Should see [ML FILTER] log messages")
    print("  - Trade count should be reduced vs baseline")
    print("="*80)
    
    # Load config and verify settings
    with open("backtesting/config.json", 'r') as f:
        config = json.load(f)
    
    ml_cfg = config.get("ml_filter", {})
    print(f"\nCurrent ML Config:")
    print(f"  Enabled: {ml_cfg.get('enabled')}")
    print(f"  Model Type: {ml_cfg.get('model_type')}")
    print(f"  Threshold: {ml_cfg.get('threshold')}")
    print(f"  Per-Symbol: {ml_cfg.get('per_symbol')}")
    print(f"  Comparison Mode: {ml_cfg.get('comparison_mode')}")
    
    # Temporarily modify config for quick test
    config['backtesting']['symbols'] = ['QQQ']  # Test only QQQ
    config['ml_filter']['comparison_mode'] = True  # Enable comparison
    
    with open("backtesting/config.json", 'w') as f:
        json.dump(config, f, indent=2)
    
    print("\n" + "="*80)
    print("Starting backtest...")
    print("="*80 + "\n")
    
    try:
        run_backtest()
    except Exception as e:
        print(f"\n❌ Error during backtest: {e}")
        import traceback
        traceback.print_exc()
