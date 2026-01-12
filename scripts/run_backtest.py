
import logging
import sys
import pandas as pd
from datetime import datetime, timezone

# Add project root to path
import os
sys.path.append(os.getcwd())
print(f"DEBUG: CWD={os.getcwd()}")
print(f"DEBUG: Path={sys.path}")
try:
    import config
    print(f"DEBUG: Config found: {config}")
    print(f"DEBUG: Config file: {getattr(config, '__file__', 'No file')}")
except Exception as e:
    print(f"DEBUG: Config import failed: {e}")

from data.storage.database import Database
from backtesting.engine import BacktestEngine

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("scripts.run_backtest")

def main():
    logger.info("Initializing Backtest...")
    
    # 1. Setup Data
    db = Database()
    symbols = ["SPY", "QQQ", "IWM", "DIA", "GLD", "TLT"] 
    # Validated symbols
    
    data_map = {}
    
    for symbol in symbols:
        logger.info(f"Loading data for {symbol}...")
        
        # Load 1H Market Data
        df_1h = db.load_market_data(symbol, "1h")
        if df_1h.empty:
            logger.warning(f"No 1H data for {symbol}. Skipping.")
            continue
            
        # Load 1H Indicators
        df_ind = db.load_indicators(symbol, "1h")
        if df_ind.empty:
            logger.warning(f"No 1H indicators for {symbol}. Skipping.")
            continue
            
        # Merge
        # Inner join to ensure we have both price and indicators
        df_combined = df_1h.join(df_ind, how='inner', lsuffix='_price', rsuffix='')
        
        # Load Daily Data for Trend (SMA50)
        # Strategy needs 'SMA_50' from Daily timeframe.
        # But 'scanner.py' expects 'SMA_50' in the daily dataframe passed to it.
        # OR if we merged it? 
        # Only 'scanner.py' uses Daily DF. 
        # BUT 'patterns.py' might need it? No.
        
        # Let's verify 'scanner.py' signature:
        # find_signals(self, symbol: str, df: pd.DataFrame, df_daily: pd.DataFrame)
        
        # So we need to pass Daily DF separately.
        # But wait, BacktestEngine.run uses:
        # self.scanner.find_signals(symbol, df, df_daily)
        # Note: In engine.py I left df_daily empty! TODO.
        
        # We need to load Daily data here and pass it to Engine.
        # Engine currently doesn't accept daily map.
        
        # HACK: Let's attach daily data to 'data_map' via a convention or modify Engine.
        # Better: Modify Engine to accept daily_data_map.
        
        # For now, let's just make sure 1H data is solid.
        data_map[symbol] = df_combined
        
    if not data_map:
        logger.error("No data loaded. Exiting.")
        return

    # 2. Setup Engine
    engine = BacktestEngine(initial_capital=10000.0)
    
    # Fix: Manually inject daily data into engine if we modify it, 
    # or rely on Scanner logic.
    # Let's modify Engine on the fly or ensuring Engine can fetch logic?
    # No, keep it simple.
    
    # We need to fetch Daily Data too!
    daily_map = {}
    for symbol in symbols:
        df_1d = db.load_market_data(symbol, "1d")
        df_ind_1d = db.load_indicators(symbol, "1d")
        if not df_1d.empty and not df_ind_1d.empty:
            df_d = df_1d.join(df_ind_1d, how='inner', lsuffix='_price', rsuffix='')
            daily_map[symbol] = df_d
            
    # Inject into Engine (I need to add this field to Engine)
    engine.market_data = data_map
    engine.daily_data = daily_map
    
    # 3. Modify Engine to use this daily_data
    # (Engine.run needs to access self.daily_data)
    
    # 4. Run
    history_report = engine.run()
    
    # 5. Print Summary
    print("\n" + "="*50)
    print("BACKTEST RESULTS (10,000 EUR Start)")
    print("="*50)
    
    equity = history_report['final_equity']
    trades = history_report['trades']
    
    print(f"Final Equity: {equity:,.2f} EUR")
    pnl = equity - 10000
    ret_pct = (pnl / 10000) * 100
    print(f"Total Return: {ret_pct:.2f}%")
    print(f"Total Trades: {len(trades)}")
    
    wins = [t for t in trades if t['pnl'] > 0]
    losses = [t for t in trades if t['pnl'] <= 0]
    win_rate = (len(wins) / len(trades) * 100) if trades else 0.0
    
    print(f"Win Rate:     {win_rate:.2f}%")
    if trades:
        avg_win = sum(t['pnl'] for t in wins) / len(wins) if wins else 0
        avg_loss = sum(t['pnl'] for t in losses) / len(losses) if losses else 0
        print(f"Avg Win:      {avg_win:.2f} EUR")
        print(f"Avg Loss:     {avg_loss:.2f} EUR")
    
    print("\nRecent Trades:")
    for t in trades[-5:]:
        print(f"{t['time']} {t['symbol']} {t['side']} PnL: {t['pnl']:.2f}")

if __name__ == "__main__":
    main()
