
import logging
import sys
import pandas as pd
from datetime import datetime, timezone
import os

# Root execution, path is already correct usually, but let's be safe
sys.path.append(os.getcwd())

from data.storage.database import Database
from backtesting.engine import BacktestEngine
from config.settings import DATABASE_PATH # Verify import works here too

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("run_backtest_root")

# Configure Decisions Log
decision_logger = logging.getLogger("scanner_decisions")
decision_logger.setLevel(logging.INFO)
# Ensure logs dir exists
os.makedirs("logs", exist_ok=True)
fh = logging.FileHandler("logs/scanner_decisions.log", mode='w')
fh.setFormatter(logging.Formatter('%(message)s'))
decision_logger.addHandler(fh)
decision_logger.propagate = False # Don't print to console

def main():
    logger.info("Initializing Backtest (Root)...")
    
    # 1. Setup Data
    db = Database()
    symbols = ["SPY", "QQQ", "IWM", "DIA", "GLD", "TLT"] 
    
    data_map = {}
    
    for symbol in symbols:
        logger.info(f"Loading data for {symbol}...")
        
        # Load 1H Market Data
        df_1h = db.load_market_data(symbol, "1h")
        if df_1h.empty:
            logger.warning(f"No 1H data for {symbol}. Skipping.")
            continue
            
        # Standardize Columns
        df_1h.columns = [c.capitalize() for c in df_1h.columns]
            
        # Load 1H Indicators
        df_ind = db.load_indicators(symbol, "1h")
        if df_ind.empty:
            logger.warning(f"No 1H indicators for {symbol}. Skipping.")
            continue
            
        # FIX: Drop Duplicates in Indicators (DB has dupes)
        df_ind = df_ind[~df_ind.index.duplicated(keep='last')]
            
        # Merge
        df_combined = df_1h.join(df_ind, how='inner', lsuffix='_price', rsuffix='')
        data_map[symbol] = df_combined
        
    if not data_map:
        logger.error("No data loaded. Exiting.")
        return

    # 2. Setup Engine
    engine = BacktestEngine(initial_capital=10000.0)
    
    # Fetch Daily Data
    daily_map = {}
    for symbol in symbols:
        df_1d = db.load_market_data(symbol, "1d")
        if not df_1d.empty:
             df_1d.columns = [c.capitalize() for c in df_1d.columns]
             
        df_ind_1d = db.load_indicators(symbol, "1d")
        if not df_1d.empty and not df_ind_1d.empty:
            df_d = df_1d.join(df_ind_1d, how='inner', lsuffix='_price', rsuffix='')
            daily_map[symbol] = df_d
            
    engine.market_data = data_map
    engine.daily_data = daily_map
    
    # 3. Run
    history_report = engine.run()
    
    if history_report is None:
        print("No trades generated during backtest period.")
        return
    
    # 4. Print Detailed Results
    print("\n" + "="*80)
    print("BACKTEST RESULTS - DETAILED REPORT")
    print("="*80)
    
    equity = history_report['final_equity']
    trades = history_report['trades']
    positions = history_report['positions']
    
    # Summary Stats
    print(f"\nSUMMARY")
    print(f"Initial Capital:  10,000.00 EUR")
    print(f"Final Equity:     {equity:,.2f} EUR")
    pnl = equity - 10000
    ret_pct = (pnl / 10000) * 100
    print(f"Total P&L:        {pnl:+,.2f} EUR ({ret_pct:+.2f}%)")
    print(f"Total Trades:     {len(trades)}")
    
    wins = [t for t in trades if t['pnl'] > 0]
    losses = [t for t in trades if t['pnl'] <= 0]
    win_rate = (len(wins) / len(trades) * 100) if trades else 0.0
    
    print(f"\nPERFORMANCE")
    print(f"Wins:             {len(wins)}")
    print(f"Losses:           {len(losses)}")
    print(f"Win Rate:         {win_rate:.2f}%")
    
    if trades:
        avg_win = sum(t['pnl'] for t in wins) / len(wins) if wins else 0
        avg_loss = sum(t['pnl'] for t in losses) / len(losses) if losses else 0
        print(f"Avg Win:          {avg_win:+.2f} EUR")
        print(f"Avg Loss:         {avg_loss:+.2f} EUR")
        
        total_win_pnl = sum(t['pnl'] for t in wins)
        total_loss_pnl = abs(sum(t['pnl'] for t in losses)) if losses else 1
        profit_factor = total_win_pnl / total_loss_pnl if total_loss_pnl > 0 else float('inf')
        print(f"Profit Factor:    {profit_factor:.2f}")
    
    # Open Positions
    if positions:
        print(f"\nOPEN POSITIONS ({len(positions)})")
        total_unrealized = 0
        for sym, pos in positions.items():
            unrealized = pos.unrealized_pnl
            total_unrealized += unrealized
            print(f"  {sym}: {pos.quantity:+d} units @ {pos.avg_entry_price:.2f} | Current: {pos.current_price:.2f} | Unrealized P&L: {unrealized:+,.2f} EUR")
        print(f"  Total Unrealized P&L: {total_unrealized:+,.2f} EUR")
    
    # Detailed Trade Log
    print(f"\nALL TRADES ({len(trades)} total)")
    print("-" * 80)
    
    for i, t in enumerate(trades, 1):
        print(f"\nTrade #{i}:")
        print(f"  Symbol:     {t['symbol']}")
        print(f"  Side:       {t['side']}")
        print(f"  Time:       {t['time']}")
        print(f"  Quantity:   {t['qty']} units")
        print(f"  Entry:      {t['entry']:.2f} EUR")
        print(f"  Exit:       {t['exit']:.2f} EUR")
        print(f"  P&L:        {t['pnl']:+.2f} EUR")
        print(f"  Tag:        {t.get('tag', 'N/A')}")
    
    print("\n" + "="*80)

if __name__ == "__main__":
    main()
