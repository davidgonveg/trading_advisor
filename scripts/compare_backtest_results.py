"""
Compare backtest results before and after wick_ratio fix
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

print("="*80)
print("BACKTEST COMPARISON: Before vs After wick_ratio Fix")
print("="*80)

print("\nBEFORE (wick_ratio = 1.0):")
print("-" * 80)
before_results = """
Symbol   Strategy  P&L %    Win Rate  Sharpe  MaxDD  Trades  Profit Factor
   GLD VWAPBounce +1,487.56%    60.0%    0.21 -58.2%      10           1.91
   IWM VWAPBounce    +69.45%    87.5%    0.11 -42.0%       8          93.33
   QQQ VWAPBounce   +760.55%    40.0%    0.19 -47.5%       5           0.35
   SMH VWAPBounce   +655.61%    35.3%    0.18 -53.4%      17           0.86
   SPY VWAPBounce   +167.14%    56.2%    0.13 -29.5%      16           3.43
   XLE VWAPBounce   +113.56%    66.7%    0.11 -29.6%      12           2.33
   XLF VWAPBounce   +198.04%     0.0%    0.15 -61.5%       1           0.00
   XLK VWAPBounce   +681.97%    76.2%    0.18 -52.3%      21           3.83
"""
print(before_results)

# Read latest results
latest_log = sorted(Path("backtesting/logs").glob("trades_*.csv"), key=lambda x: x.stat().st_mtime)
if latest_log:
    latest = latest_log[-1]
    print(f"\nAFTER (wick_ratio = 2.0) - from {latest.name}:")
    print("-" * 80)
    
    import pandas as pd
    df = pd.read_csv(latest)
    
    # Count trades per symbol
    trade_counts = df.groupby('symbol').size()
    print("\nTrade Counts by Symbol:")
    for symbol, count in trade_counts.items():
        before_count = {
            'GLD': 10, 'IWM': 8, 'QQQ': 5, 'SMH': 17, 
            'SPY': 16, 'XLE': 12, 'XLF': 1, 'XLK': 21
        }.get(symbol, 0)
        change = count - before_count
        pct_change = (change / before_count * 100) if before_count > 0 else 0
        print(f"  {symbol}: {count} trades (was {before_count}, {change:+d} / {pct_change:+.1f}%)")
    
    print(f"\nTotal Trades: {len(df)} (was 90)")
    print(f"Change: {len(df) - 90:+d} trades ({(len(df) - 90) / 90 * 100:+.1f}%)")
else:
    print("\n⚠️  No new backtest results found")

print("\n" + "="*80)
print("EXPECTED IMPACT:")
print("="*80)
print("Stricter wick requirement (2.0x vs 1.0x) should REDUCE trade count")
print("This brings backtest closer to live trading behavior")
print("="*80)
