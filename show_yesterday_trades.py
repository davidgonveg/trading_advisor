"""
Script to show only trades from yesterday (2026-02-02) from the latest backtest.
"""
import json
import glob
import os
from datetime import datetime, timedelta

# Get yesterday's date
yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

print(f"=== TRADES FROM {yesterday} ===\n")

# Find latest backtest audit files
audit_files = glob.glob("backtesting/logs/audit_*_VWAPBounce_*.json")
if not audit_files:
    print("No backtest files found!")
    exit(1)

# Get the latest timestamp
latest_timestamp = max([f.split('_')[-1].replace('.json', '') for f in audit_files])

# Process each symbol
results = []
for symbol in ['GLD', 'XLK', 'SPY', 'QQQ', 'SMH', 'XLE', 'XLF', 'IWM']:
    audit_file = f"backtesting/logs/audit_{symbol}_VWAPBounce_{latest_timestamp}.json"
    
    if not os.path.exists(audit_file):
        continue
    
    with open(audit_file) as f:
        data = json.load(f)
    
    # Find trades from yesterday
    yesterday_trades = []
    for trade in data.get('trades', []):
        # Check if trade has timestamp info
        for key in ['entry_time', 'timestamp', 'time']:
            if key in trade and yesterday in str(trade[key]):
                yesterday_trades.append(trade)
                break
    
    # Also check bars for signals on yesterday
    yesterday_bars = [b for b in data.get('bars', []) if yesterday in b.get('timestamp', '')]
    signals_yesterday = [b for b in yesterday_bars if b.get('signal') not in ['HOLD', None]]
    
    if yesterday_trades or signals_yesterday:
        results.append({
            'symbol': symbol,
            'trades': len(yesterday_trades),
            'signals': len(signals_yesterday),
            'bars': len(yesterday_bars)
        })

if results:
    print(f"{'Symbol':<8} {'Trades':<8} {'Signals':<10} {'Bars on ' + yesterday}")
    print("-" * 50)
    for r in results:
        print(f"{r['symbol']:<8} {r['trades']:<8} {r['signals']:<10} {r['bars']}")
else:
    print(f"No trades or signals found for {yesterday}")
    print("\nNote: The backtest may have generated trades on other days.")
    print("To see all trades, check the full backtest summary above.")

print(f"\n💡 Tip: Los trades pueden haberse ejecutado en días anteriores")
print(f"   y cerrado en {yesterday}, o viceversa. El backtest completo")
print(f"   muestra el rendimiento total del período.")
