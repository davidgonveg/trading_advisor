import json
import logging
from datetime import datetime, timezone
from backtesting.core.backtester import BacktestEngine
from backtesting.core.data_loader import DataLoader
from backtesting.core.validator import Validator
from backtesting.analytics.metrics import MetricsCalculator
from backtesting.strategies.vwap_bounce import VWAPBounce
from backtesting.strategies.ema_pullback import EMAPullback
import pandas as pd
import os

from backtesting.core.logger import setup_logging

def load_config():
    with open("backtesting/config.json", "r") as f:
        return json.load(f)

import concurrent.futures

def run_backtest_wrapper(args):
    """Unpacks arguments for parallel execution."""
    strat_class, params, config, symbol, data, timestamp = args
    
    if data.empty:
        return None
        
    engine = BacktestEngine(
        initial_capital=config['backtesting']['initial_capital'],
        commission=config['backtesting']['commission'],
        slippage=config['backtesting']['slippage'],
        config=config,
        timestamp=timestamp,
        symbol=symbol,
        strategy_name=strat_class.__name__
    )
    
    strategy_instance = strat_class()
    engine.set_strategy(strategy_instance, params)
    
    results = engine.run(symbol, data)
    
    metrics = MetricsCalculator.calculate_metrics(
        results['trades'], 
        results['equity_curve'], 
        config['backtesting']['initial_capital']
    )
    
    # Save Audit
    results['audit'].save(metrics)
    
    return {
        "symbol": symbol,
        "strategy": strat_class.__name__,
        "metrics": metrics
    }

def main():
    start_time = datetime.now()
    
    # 1. Load Config
    config = load_config()
    
    # 2. Setup Logging
    ts = setup_logging(config)
    logger = logging.getLogger("backtesting.main")
    
    # 3. Engine Validation
    Validator.run_all_tests()
    
    symbols = config['backtesting'].get('symbols', ['SPY'])
    
    # 4. Data Pre-loading
    logger.info(f"--- Pre-loading data for {len(symbols)} symbols ---")
    loader = DataLoader()
    start_date = datetime.strptime(config['backtesting']['start_date'], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    end_date = datetime.strptime(config['backtesting']['end_date'], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    
    data_cache = {}
    for symbol in symbols:
        data = loader.load_data(
            symbol=symbol,
            interval=config['backtesting']['interval'],
            start_date=start_date,
            end_date=end_date
        )
        if not data.empty:
            data_cache[symbol] = data

    strategies_to_test = [
        (VWAPBounce, config['strategies']['vwap_bounce']),
        # (EMAPullback, config['strategies']['ema_pullback']),
    ]
    
    # Generate tasks for parallel execution
    tasks = []
    for symbol in data_cache:
        for strat_class, params in strategies_to_test:
            tasks.append((strat_class, params, config, symbol, data_cache[symbol], ts))
            
    print("\n" + "="*80)
    print(f"STARTING PARALLEL BACKTEST | {len(symbols)} Assets | {len(strategies_to_test)} Strategies")
    print(f" Threads: {os.cpu_count()}")
    print("="*80)

    all_results = []
    
    # Use ProcessPoolExecutor for CPU-bound backtesting
    with concurrent.futures.ProcessPoolExecutor() as executor:
        future_to_task = {executor.submit(run_backtest_wrapper, task): task for task in tasks}
        for future in concurrent.futures.as_completed(future_to_task):
            try:
                res = future.result()
                if res:
                    all_results.append(res)
            except Exception as exc:
                task = future_to_task[future]
                logger.error(f"Task {task[3]} {task[0].__name__} generated an exception: {exc}")
            
    # 6. Print Multi-Symbol Summary
    print("\n" + "="*110)
    print(f"MULTI-SYMBOL PERFORMANCE SUMMARY ({ts})")
    print(f" Elapsed Time: {datetime.now() - start_time}")
    print("="*110)
    
    overall_summary = []
    long_summary = []
    short_summary = []
    
    for res in all_results:
        m = res['metrics']
        overall_summary.append({
            "Symbol": res['symbol'],
            "Strategy": res['strategy'],
            "P&L %": f"{m.get('Total P&L %'):+,.2f}%",
            "Win Rate": f"{m.get('Win Rate %'):.1f}%",
            "Sharpe": m.get("Sharpe Ratio"),
            "MaxDD": f"{m.get('Max Drawdown %'):.1f}%",
            "Trades": m.get("Total Trades"),
            "Profit Factor": m.get("Profit Factor")
        })
        
        l = m.get('Long Performance', {})
        long_summary.append({
            "Symbol": res['symbol'],
            "Trades": l.get("Total Trades"),
            "Win Rate": f"{l.get('Win Rate %', 0):.1f}%",
            "Profit Factor": l.get("Profit Factor"),
            "Net P&L $": f"${l.get('Total P&L', 0):,.2f}"
        })
        
        s = m.get('Short Performance', {})
        short_summary.append({
            "Symbol": res['symbol'],
            "Trades": s.get("Total Trades"),
            "Win Rate": f"{s.get('Win Rate %', 0):.1f}%",
            "Profit Factor": s.get("Profit Factor"),
            "Net P&L $": f"${s.get('Total P&L', 0):,.2f}"
        })
        
    if overall_summary:
        print("\nOVERALL PERFORMANCE")
        print(pd.DataFrame(overall_summary).sort_values(by='Symbol').to_string(index=False))
        
        print("\nLONG POSITIONS PERFORMANCE")
        print(pd.DataFrame(long_summary).sort_values(by='Symbol').to_string(index=False))
        
        print("\nSHORT POSITIONS PERFORMANCE")
        print(pd.DataFrame(short_summary).sort_values(by='Symbol').to_string(index=False))
    else:
        print("No results to display.")
        
    print("="*110)
    print(f"[OK] Detailed logs and audit trails (JSON/CSV) saved in backtesting/logs/")

if __name__ == "__main__":
    main()
