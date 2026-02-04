"""
Standalone diagnostic script to test signal handling logic with Feb 2 data.
This bypasses the full backtest infrastructure to isolate the signal execution issue.
"""
import sys
import os
sys.path.insert(0, os.path.abspath('.'))

import logging
import pandas as pd
import json
from datetime import datetime, timezone

# Setup logging to see DEBUG messages
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

from backtesting.core.backtester import BacktestEngine
from backtesting.strategies.vwap_bounce import VWAPBounce
from backtesting.core.data_loader import DataLoader

def main():
    print("="*80)
    print("DIAGNOSTIC: Testing Signal Handling for Feb 2, 2026")
    print("="*80)
    
    # Load config
    with open('backtesting/config.json', 'r') as f:
        config = json.load(f)
    
    # Load GLD data
    loader = DataLoader()
    start_date = datetime(2026, 2, 1, tzinfo=timezone.utc)
    end_date = datetime(2026, 2, 3, tzinfo=timezone.utc)
    
    print(f"\nLoading GLD data from {start_date} to {end_date}...")
    data = loader.load_data('GLD', '1h', start_date, end_date)
    
    if data.empty:
        print("ERROR: No data loaded!")
        return
    
    print(f"Loaded {len(data)} bars")
    print(f"Date range: {data.index[0]} to {data.index[-1]}")
    
    # Filter to Feb 2
    feb2_data = data[data.index.date == datetime(2026, 2, 2).date()]
    print(f"\nFeb 2 bars: {len(feb2_data)}")
    
    # Create backtest engine
    engine = BacktestEngine(
        initial_capital=config['backtesting']['initial_capital'],
        commission=config['backtesting']['commission'],
        slippage=config['backtesting']['slippage'],
        config=config,
        timestamp="diagnostic",
        symbol="GLD",
        strategy_name="VWAPBounce"
    )
    
    # Setup strategy
    strategy = VWAPBounce()
    engine.set_strategy(strategy, config['strategies']['vwap_bounce'])
    
    print("\n" + "="*80)
    print("Running backtest...")
    print("="*80 + "\n")
    
    # Run backtest
    results = engine.run('GLD', data)
    
    print("\n" + "="*80)
    print("RESULTS")
    print("="*80)
    print(f"Total trades executed: {len(results['trades'])}")
    print(f"Final equity: ${results['final_equity']:.2f}")
    
    # Check audit log for Feb 2
    print("\n" + "="*80)
    print("Checking audit log for Feb 2 signals...")
    print("="*80)
    
    # The audit log is in the results
    # Let's manually check the bars
    print("\nThis diagnostic run should have shown DEBUG logs above.")
    print("Look for [SIGNAL HANDLER] entries for 2026-02-02.")

if __name__ == "__main__":
    main()
