
import logging
import sys
import pandas as pd
from datetime import timedelta
import os

# Root execution
sys.path.append(os.getcwd())

from data.storage.database import Database
from backtesting.engine import BacktestEngine
from config.settings import DATABASE_PATH

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("verify_backtest")

def main():
    logger.info("Initializing Verification Backtest (SPY Only, Last 5 Days)...")
    
    db = Database()
    symbol = "SPY"
    
    # 1. Load Data
    logger.info(f"Loading data for {symbol}...")
    df_1h = db.load_market_data(symbol, "1h")
    if df_1h.empty:
        logger.error("No 1H data.")
        return
        
    df_1h.columns = [c.capitalize() for c in df_1h.columns]
    
    df_ind = db.load_indicators(symbol, "1h")
    if df_ind.empty:
        logger.error("No 1H indicators.")
        return
        
    df_combined = df_1h.join(df_ind, how='inner', lsuffix='_price', rsuffix='')
    
    # 2. Determine Date Range (Last 90 days to catch Nov 2025 signals)
    max_date = df_combined.index.max()
    start_date = max_date - timedelta(days=90)
    
    logger.info(f"Data Range: {df_combined.index.min()} to {max_date}")
    logger.info(f"Backtest Target: {start_date} to {max_date}")
    
    # Filter Data
    # Engine processes *all* passed data, so we slice here?
    # Or pass dates to Engine? Engine logic:
    # "Iterate timestamps" - it iterates *all* indices in market_data.
    # So we should slice the dataframe BEFORE passing to engine.
    
    df_sliced = df_combined[df_combined.index >= start_date]
    if df_sliced.empty:
        logger.error("Sliced data is empty.")
        return
        
    logger.info(f"Running with {len(df_sliced)} candles.")
    
    # 3. Setup Daily Data
    df_1d = db.load_market_data(symbol, "1d")
    daily_map = {}
    if not df_1d.empty:
        df_1d.columns = [c.capitalize() for c in df_1d.columns]
        daily_map[symbol] = df_1d
        
    # 4. Engine
    engine = BacktestEngine(initial_capital=10000.0)
    engine.market_data = {symbol: df_sliced}
    engine.daily_data = daily_map
    
    # 5. Run
    history = engine.run()
    
    if history is None:
        print("No trades generated.")
    else:
        print("\n" + "="*50)
        print("VERIFICATION RESULTS")
        print("="*50)
        trades = history['trades']
        print(f"Total Trades: {len(trades)}")
        print(f"Final Equity: {history['final_equity']:.2f}")
        
        for t in trades:
            print(f"[{t['time']}] {t['side']} {t['symbol']} @ {t['entry_price']:.2f} -> {t['exit_price']:.2f} PnL: {t['pnl']:.2f}")
            
if __name__ == "__main__":
    main()
