import json
import logging
import os
import pandas as pd
import concurrent.futures
from datetime import datetime, timezone
from backtesting.core.data_loader import DataLoader
from backtesting.core.backtester import BacktestEngine
from backtesting.analytics.metrics import MetricsCalculator
from backtesting.strategies.vwap_bounce import VWAPBounce
from typing import Dict, Any

# Setup basic logging to avoid clutter
logging.basicConfig(level=logging.ERROR)

def load_config():
    with open("backtesting/config.json", "r") as f:
        return json.load(f)

def run_single_test(args):
    """Worker function for individual backtest."""
    strat_class, params, config, symbol, data, ml_enabled = args
    
    if data.empty:
        return None
    
    # Create isolated config for this run
    test_config = json.loads(json.dumps(config)) # Deep copy
    if 'ml_filter' not in test_config:
        test_config['ml_filter'] = {}
    test_config['ml_filter']['enabled'] = ml_enabled
    
    if 'debug' not in test_config:
        test_config['debug'] = {}
    test_config['debug']['enabled'] = False # Force debug OFF
    
    engine = BacktestEngine(
        initial_capital=test_config['backtesting']['initial_capital'],
        commission=test_config['backtesting']['commission'],
        slippage=test_config['backtesting']['slippage'],
        config=test_config,
        symbol=symbol,
        strategy_name=strat_class.__name__
    )
    
    strategy_instance = strat_class()
    engine.set_strategy(strategy_instance, params)
    
    results = engine.run(symbol, data)
    
    metrics = MetricsCalculator.calculate_metrics(
        results['trades'], 
        results['equity_curve'], 
        test_config['backtesting']['initial_capital']
    )
    
    return {
        "symbol": symbol,
        "ml_enabled": ml_enabled,
        "metrics": metrics
    }

def main():
    config = load_config()
    symbols = config['backtesting'].get('symbols', ['SPY'])
    
    print(f"\n{'='*100}")
    print(f" ML FILTER COMPARISON | {len(symbols)} Symbols | Parallel Execution")
    print(f"{'='*100}")

    # 1. Pre-load Data
    loader = DataLoader()
    start_date = datetime.strptime(config['backtesting']['start_date'], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    end_date = datetime.strptime(config['backtesting']['end_date'], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    
    data_cache = {}
    print("Loading historical data...")
    for symbol in symbols:
        data = loader.load_data(symbol, config['backtesting']['interval'], start_date, end_date)
        if not data.empty:
            data_cache[symbol] = data

    strategies = [
        (VWAPBounce, config['strategies']['vwap_bounce']),
    ]

    # 2. Build tasks
    tasks = []
    for strat_class, params in strategies:
        for symbol, data in data_cache.items():
            tasks.append((strat_class, params, config, symbol, data, False)) # Baseline
            tasks.append((strat_class, params, config, symbol, data, True))  # With ML

    # 3. Execute in parallel
    print(f"Executing {len(tasks)} backtests...")
    results_map = {} # (symbol, ml_enabled) -> metrics
    
    with concurrent.futures.ProcessPoolExecutor() as executor:
        futures = {executor.submit(run_single_test, task): task for task in tasks}
        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            if res:
                results_map[(res['symbol'], res['ml_enabled'])] = res['metrics']

    # 4. Generate comparison table
    comparison_data = []
    for symbol in data_cache:
        m_base = results_map.get((symbol, False))
        m_ml = results_map.get((symbol, True))
        
        if m_base and m_ml:
            base_pnl = m_base.get('Total P&L %', 0)
            ml_pnl = m_ml.get('Total P&L %', 0)
            base_wr = m_base.get('Win Rate %', 0)
            ml_wr = m_ml.get('Win Rate %', 0)
            base_trades = m_base.get('Total Trades', 0)
            ml_trades = m_ml.get('Total Trades', 0)
            
            pnl_diff = ml_pnl - base_pnl
            wr_diff = ml_wr - base_wr
            reduction = ((base_trades - ml_trades) / base_trades * 100) if base_trades > 0 else 0
            
            comparison_data.append({
                "Symbol": symbol,
                "Trades (B)": base_trades,
                "Trades (ML)": ml_trades,
                "Reduc %": f"{reduction:.1f}%",
                "WR (B)": f"{base_wr:.1f}%",
                "WR (ML)": f"{ml_wr:.1f}%",
                "WR Improv": f"{wr_diff:+.1f}%",
                "PNL (B)": f"{base_pnl:+.2f}%",
                "PNL (ML)": f"{ml_pnl:+.2f}%",
                "PNL Improv": f"{pnl_diff:+.2f}%"
            })

    if comparison_data:
        df = pd.DataFrame(comparison_data).sort_values(by="Symbol")
        print("\n" + "="*110)
        print("PERFORMANCE COMPARISON: BASELINE VS MACHINE LEARNING FILTER")
        print("="*110)
        print(df.to_string(index=False))
        print("="*110)
        
        # Summary Averages
        avg_base_pnl = df["PNL (B)"].str.replace('%','').astype(float).mean()
        avg_ml_pnl = df["PNL (ML)"].str.replace('%','').astype(float).mean()
        avg_base_wr = df["WR (B)"].str.replace('%','').astype(float).mean()
        avg_ml_wr = df["WR (ML)"].str.replace('%','').astype(float).mean()
        
        print(f"\nOVERALL SUMMARY:")
        print(f"  Avg Win Rate: {avg_base_wr:.1f}% -> {avg_ml_wr:.1f}% ({avg_ml_wr - avg_base_wr:+.1f}%)")
        print(f"  Avg P&L:      {avg_base_pnl:.2f}% -> {avg_ml_pnl:.2f}% ({avg_ml_pnl - avg_base_pnl:+.2f}%)")
    else:
        print("No paired results found for comparison.")

if __name__ == "__main__":
    main()
