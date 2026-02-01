import json
import logging
import os
import random
import time
import pandas as pd
import concurrent.futures
from datetime import datetime, timezone
from datetime import datetime, timezone
from backtesting.core.backtester import BacktestEngine
from backtesting.core.data_loader import DataLoader
from backtesting.strategies.vwap_bounce import VWAPBounce
from backtesting.main import load_config
from backtesting.analytics.metrics import MetricsCalculator

# Setup Logger
# We want to suppress INFO logs to console (so tqdm works) but keep them in file
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
log_file = f"backtesting/logs/optimizer_{timestamp}.log"

root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)

# 1. File Handler (Detailed)
fh = logging.FileHandler(log_file)
fh.setLevel(logging.INFO)
fh_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
fh.setFormatter(fh_formatter)
root_logger.addHandler(fh)

# 2. Console Handler (Warnings/Errors only)
ch = logging.StreamHandler()
ch.setLevel(logging.WARNING)
ch_formatter = logging.Formatter('%(levelname)s: %(message)s')
ch.setFormatter(ch_formatter)
root_logger.addHandler(ch)

logger = logging.getLogger("optimizer")

STRATEGIES = {
    "vwap_bounce": VWAPBounce
}

def generate_params(config_params):
    """Generates a random set of parameters based on the config."""
    params = {}
    for key, spec in config_params.items():
        if spec["type"] == "fixed":
            params[key] = spec["value"]
        elif spec["type"] == "range":
            if isinstance(spec["min"], int) and isinstance(spec["max"], int):
                params[key] = random.randint(spec["min"], spec["max"])
            else:
                # Continuous range, use random uniform or steps
                # If step is defined, snap to grid
                if "step" in spec:
                    steps = int((spec["max"] - spec["min"]) / spec["step"])
                    res = spec["min"] + (random.randint(0, steps) * spec["step"])
                    params[key] = round(res, 2)
                else:
                    params[key] = round(random.uniform(spec["min"], spec["max"]), 2)
        elif spec["type"] == "choice":
            params[key] = random.choice(spec["values"])
    return params

def chunked_iterable(iterable, size):
    """Yield successive n-sized chunks from iterable."""
    for i in range(0, len(iterable), size):
        yield iterable[i:i + size]

def run_batch_backtests(args):
    """
    Runs a batch of parameter sets on a single symbol.
    Args:
        symbol: str
        strategy_cls: Class
        params_list: List[Dict] - List of parameter dicts
        data: DataFrame
        base_config: Dict
    """
    symbol, strategy_cls, params_list, data, base_config = args
    
    results = []
    
    # 1. Setup Base Config for this Batch
    # We clone it once to save overhead
    batch_config = base_config.copy()
    
    # PERFORMANCE TUNING:
    # 1. Disable ML Filter (unless we want to optimize it later, but generally it's slow)
    batch_config["ml_filter"]["enabled"] = False 
    
    # 2. Disable Audit Logging (CRITICAL for speed)
    if "logging" not in batch_config: batch_config["logging"] = {}
    if "audit_log" not in batch_config["logging"]: batch_config["logging"]["audit_log"] = {}
    batch_config["logging"]["audit_log"]["enabled"] = False
    
    # 3. Disable Console Logging in Engine (Already handled by global logging config but good to force)
    if "console" not in batch_config["logging"]: batch_config["logging"]["console"] = {}
    batch_config["logging"]["console"]["enabled"] = False

    # Instantiate Engine ONCE if possible? 
    # No, BacktestEngine is stateful (portfolio, trades). 
    # But we can reuse the data reference.
    
    for params in params_list:
        try:
            engine = BacktestEngine(
                initial_capital=batch_config["backtesting"]["initial_capital"],
                commission=batch_config["backtesting"]["commission"],
                slippage=batch_config["backtesting"]["slippage"],
                config=batch_config, # Pass the optimized config
                symbol=symbol,
                strategy_name=f"OPT_{symbol}"
            )
            
            # Setup Strategy
            strat_key = "vwap_bounce" 
            # We assume strategy uses its local params, but Engine.set_strategy calls setup()
            
            engine.data = data # Direct data injection
            
            strategy_instance = strategy_cls()
            engine.set_strategy(strategy_instance, params)
            
            # Run
            raw_results = engine.run(symbol, data)
            
            metrics = MetricsCalculator.calculate_metrics(
                raw_results['trades'], 
                raw_results['equity_curve'], 
                batch_config['backtesting']['initial_capital']
            )
            
            results.append({
                "symbol": symbol,
                "params": params,
                "metrics": metrics
            })
            
        except Exception as e:
            logger.error(f"Failed run for {symbol}: {e}")
            # Continue with next param set
            continue
            
    return results

def main():
    # 1. Load Configurations
    with open("backtesting/optimization_config.json", "r") as f:
        opt_config = json.load(f)
        
    base_config = load_config()
    
    strategy_name = opt_config.get("strategy", "vwap_bounce")
    strategy_cls = STRATEGIES.get(strategy_name)
    iterations = opt_config.get("iterations", 100)
    target_symbols = opt_config.get("symbols", ["QQQ"])
    
    # 2. Pre-load Data (RAM Intensive but fast)
    logger.info("--- Pre-loading Data ---")
    loader = DataLoader()
    start_date = datetime.strptime(base_config['backtesting']['start_date'], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    end_date = datetime.strptime(base_config['backtesting']['end_date'], "%Y-%m-%d").replace(tzinfo=timezone.utc) 
    
    data_cache = {}
    for sym in target_symbols:
        df = loader.load_data(sym, "1h", start_date, end_date)
        if not df.empty:
            data_cache[sym] = df
    
    # 3. Generate Task Batches
    logger.info(f"--- Generating {iterations} Parameter Combinations ---")
    
    # Generate all params first
    all_params = [generate_params(opt_config["parameters"]) for _ in range(iterations)]
    
    # Group by Symbol -> List[Params]
    # We want to minimize data copying. 
    # Ideal Batch: (Symbol, DataRef, ChunkOfParams)
    
    # Let's say we want ~50-100 sims per batch to amortize the process startup cost
    BATCH_SIZE = 50 
    
    tasks = []
    total_sims = 0
    
    for sym in data_cache:
        # Create chunks of params for this symbol
        param_chunks = list(chunked_iterable(all_params, BATCH_SIZE))
        
        for p_chunk in param_chunks:
            tasks.append((sym, strategy_cls, p_chunk, data_cache[sym], base_config))
            total_sims += len(p_chunk)
            
    logger.info(f"--- Starting Optimization ({total_sims} simulations in {len(tasks)} batches) ---")
    
    results = []
    start_time = time.time()
    
    # Use ProcessPoolExecutor
    max_workers = max(1, os.cpu_count() - 2)
    
    from tqdm import tqdm
    
    with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(run_batch_backtests, task) for task in tasks]
        
        # We track completed BATCHES, but update bar with SIMS count for better UX?
        # Or just track batches. Tracking batches is easier.
        
        for future in tqdm(concurrent.futures.as_completed(futures), total=len(futures), desc="Optimizing (Batches)", unit="batch"):
            batch_res = future.result()
            if batch_res:
                for res in batch_res:
                    row = res["metrics"].copy()
                    row["symbol"] = res["symbol"]
                    for k, v in res["params"].items():
                        row[f"p_{k}"] = v
                    results.append(row)
                
    total_time = time.time() - start_time
    logger.info(f"Optimization Finished in {total_time:.2f}s")
    
    # 4. Save Results
    df = pd.DataFrame(results)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"backtesting/logs/optimization_results_{timestamp}.csv"
    df.to_csv(filename, index=False)
    logger.info(f"Results saved to {filename}")

if __name__ == "__main__":
    main()
