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
    
    # Check if comparison mode is requested
    ml_cfg = config.get("ml_filter", {})
    comparison_mode = ml_cfg.get("comparison_mode", False)
    # If ML is enabled but no comparison_mode is set, just run normal with ML
    
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
            if comparison_mode:
                # Add baseline run
                base_config = json.loads(json.dumps(config))
                base_config['ml_filter']['enabled'] = False
                tasks.append((strat_class, params, base_config, symbol, data_cache[symbol], f"{ts}_BASE"))
                
                # Add ML run
                ml_config = json.loads(json.dumps(config))
                ml_config['ml_filter']['enabled'] = True
                tasks.append((strat_class, params, ml_config, symbol, data_cache[symbol], f"{ts}_ML"))
            else:
                tasks.append((strat_class, params, config, symbol, data_cache[symbol], ts))
            
    print("\n" + "="*80)
    mode_str = "COMPARISON MODE (Normal vs ML)" if comparison_mode else "NORMAL MODE"
    print(f"STARTING PARALLEL BACKTEST | {mode_str} | {len(tasks)} Rounds")
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
                    # Enrich with ML status
                    task = future_to_task[future]
                    res['ml_enabled'] = task[2].get('ml_filter', {}).get('enabled', False)
                    all_results.append(res)
            except Exception as exc:
                task = future_to_task[future]
                logger.error(f"Task {task[3]} {task[0].__name__} generated an exception: {exc}")
            
    # 6. Print Summary
    if comparison_mode:
        print_comparison_summary(all_results, ts, datetime.now() - start_time)
    else:
        print_standard_summary(all_results, ts, datetime.now() - start_time)

def print_standard_summary(all_results, ts, elapsed):
    print("\n" + "="*110)
    print(f"MULTI-SYMBOL PERFORMANCE SUMMARY ({ts})")
    print(f" Elapsed Time: {elapsed}")
    print("="*110)
    
    summary = []
    for res in all_results:
        m = res['metrics']
        summary.append({
            "Symbol": res['symbol'],
            "Strategy": res['strategy'],
            "P&L %": f"{m.get('Total P&L %'):+,.2f}%",
            "Win Rate": f"{m.get('Win Rate %'):.1f}%",
            "Sharpe": m.get("Sharpe Ratio"),
            "MaxDD": f"{m.get('Max Drawdown %'):.1f}%",
            "Trades": m.get("Total Trades"),
            "Profit Factor": m.get("Profit Factor")
        })
    
    if summary:
        print(pd.DataFrame(summary).sort_values(by='Symbol').to_string(index=False))
    print("="*110)

def print_comparison_summary(all_results, ts, elapsed):
    print("\n" + "="*120)
    print(f"ML FILTER COMPARISON SUMMARY ({ts})")
    print(f" Elapsed Time: {elapsed}")
    print("="*120)
    
    # Group results by symbol/strategy
    grouped = {}
    for res in all_results:
        key = (res['symbol'], res['strategy'])
        if key not in grouped: grouped[key] = {}
        grouped[key]['ml' if res['ml_enabled'] else 'base'] = res['metrics']
    
    comp_table = []
    for (sym, strat), runs in grouped.items():
        if 'base' in runs and 'ml' in runs:
            m_base = runs['base']
            m_ml = runs['ml']
            
            pnl_base = m_base.get('Total P&L %', 0)
            pnl_ml = m_ml.get('Total P&L %', 0)
            wr_base = m_base.get('Win Rate %', 0)
            wr_ml = m_ml.get('Win Rate %', 0)
            trades_base = m_base.get('Total Trades', 0)
            trades_ml = m_ml.get('Total Trades', 0)
            
            reduction = ((trades_base - trades_ml) / trades_base * 100) if trades_base > 0 else 0
            
            comp_table.append({
                "Symbol": sym,
                "Trades(B)": trades_base,
                "Trades(ML)": trades_ml,
                "Reduc %": f"{reduction:.1f}%",
                "WR(B)": f"{wr_base:.1f}%",
                "WR(ML)": f"{wr_ml:.1f}%",
                "WR +/-": f"{wr_ml - wr_base:+.1f}%",
                "PNL(B)": f"{pnl_base:+.2f}%",
                "PNL(ML)": f"{pnl_ml:+.2f}%",
                "PNL +/-": f"{pnl_ml - pnl_base:+.2f}%"
            })
    
    if comp_table:
        print(pd.DataFrame(comp_table).sort_values(by='Symbol').to_string(index=False))
    else:
        print("Not enough results for comparison.")
    print("="*120)

if __name__ == "__main__":
    main()
