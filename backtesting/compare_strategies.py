import json
import pandas as pd
import logging
from datetime import datetime, timezone
import concurrent.futures
import os
from backtesting.core.backtester import BacktestEngine
from backtesting.core.data_loader import DataLoader
from backtesting.strategies.vwap_bounce import VWAPBounce
from backtesting.analytics.metrics import MetricsCalculator
from backtesting.main import load_config
from tqdm import tqdm

# Configure Logging
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger("compare_strategies")

def run_strategy(args):
    symbol, data, config, params, strategy_label = args
    
    # Disable heavy logging
    run_config = config.copy()
    run_config["logging"] = {"console": {"enabled": False}, "audit_log": {"enabled": False}}
    run_config["ml_filter"] = {"enabled": False} 
    run_config["strategies"]["vwap_bounce"] = params
    
    try:
        engine = BacktestEngine(
            initial_capital=run_config["backtesting"]["initial_capital"],
            commission=run_config["backtesting"]["commission"],
            slippage=run_config["backtesting"]["slippage"],
            config=run_config,
            symbol=symbol,
            strategy_name=f"{strategy_label}"
        )
        
        engine.data = data
        strategy = VWAPBounce()
        engine.set_strategy(strategy, params)
        engine.strategy._precompute_indicators(data)
        
        res = engine.run(symbol, data)
        
        metrics = MetricsCalculator.calculate_metrics(
            res['trades'], 
            res['equity_curve'], 
            run_config['backtesting']['initial_capital']
        )
        
        return {
            "symbol": symbol,
            "label": strategy_label,
            "metrics": metrics
        }
        
    except Exception as e:
        print(f"Error processing {symbol} {strategy_label}: {e}")
        return None

def main():
    print("--- BASELINE VS PROPOSAL 1 COMPARISON ---")
    
    # 1. Define Configurations
    base_params = {
        "risk_pct": 0.015,
        "atr_period": 14,
        "atr_multiplier_sl": 2.0,
        "atr_multiplier_tp": 4.0,
        "volume_sma": 20,
        "wick_ratio": 1.0, 
        "time_stop_hours": 8,
        "use_trend_filter": False,
        "use_rsi_filter": False
    }
    
    # PROPOSAL 1: Smart Hunter
    # Same base params + Trend Filter + 2% Risk
    smart_params = base_params.copy()
    smart_params["use_trend_filter"] = True
    smart_params["risk_pct"] = 0.020 
    
    config = load_config()
    symbols = config['backtesting']['symbols']
    
    # 2. Load Data
    loader = DataLoader()
    start_date = datetime.strptime(config['backtesting']['start_date'], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    end_date = datetime.strptime(config['backtesting']['end_date'], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    
    data_cache = {}
    for sym in tqdm(symbols, desc="Loading Data"):
        df = loader.load_data(sym, "1h", start_date, end_date)
        if not df.empty:
            data_cache[sym] = df
            
    # 3. Create Tasks
    tasks = []
    for sym, data in data_cache.items():
        tasks.append((sym, data, config, base_params, "BASELINE"))
        tasks.append((sym, data, config, smart_params, "PROPOSAL_1"))
        
    results = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=os.cpu_count()-2) as executor:
        futures = [executor.submit(run_strategy, t) for t in tasks]
        for f in tqdm(concurrent.futures.as_completed(futures), total=len(futures), desc="Simulating"):
            if f.result():
                results.append(f.result())
                
    # 4. Display Results
    grouped = {}
    for r in results:
        sym = r['symbol']
        if sym not in grouped: grouped[sym] = {}
        grouped[sym][r['label']] = r['metrics']
        
    print("\n" + "="*95)
    print(f"{'SYMBOL':<8} | {'STRATEGY':<10} | {'P&L %':<10} | {'Sharpe':<8} | {'Win Rate':<8} | {'Trades':<6} | {'MaxDD':<8}")
    print("="*95)
    
    for sym in sorted(grouped.keys()):
        base = grouped[sym].get("BASELINE", {})
        opt = grouped[sym].get("PROPOSAL_1", {})
        
        if not base or not opt: continue
        
        pnl_base = base.get('Total P&L %', 0)
        pnl_opt = opt.get('Total P&L %', 0)
        
        print(f"{sym:<8} | {'BASE':<10} | {pnl_base:>9.2f}% | {base.get('Sharpe Ratio',0):>8.2f} | {base.get('Win Rate %',0):>8.1f}% | {base.get('Total Trades',0):>6} | {base.get('Max Drawdown %',0):>8.1f}%")
        print(f"{'':<8} | {'PROPOSAL 1':<10} | {pnl_opt:>9.2f}% | {opt.get('Sharpe Ratio',0):>8.2f} | {opt.get('Win Rate %',0):>8.1f}% | {opt.get('Total Trades',0):>6} | {opt.get('Max Drawdown %',0):>8.1f}%")
        print("-" * 95)
        
if __name__ == "__main__":
    main()
