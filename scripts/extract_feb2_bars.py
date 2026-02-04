"""Extract and analyze Feb 2 bars from GLD audit log."""
import json

with open('backtesting/logs/audit_GLD_VWAPBounce_20260203_195307.json', 'r') as f:
    data = json.load(f)

# Find Feb 2 bars
feb2_bars = [b for b in data['bars'] if '2026-02-02' in b['timestamp']]

print(f"Total bars on Feb 2: {len(feb2_bars)}")
print(f"\nLooking for signals...")

for bar in feb2_bars:
    if bar['signal'] not in ['HOLD', None]:
        print(f"\n{'='*80}")
        print(f"SIGNAL FOUND!")
        print(f"{'='*80}")
        print(f"Timestamp: {bar['timestamp']}")
        print(f"Signal: {bar['signal']}")
        print(f"Close: ${bar['ohlc']['Close']:.2f}")
        print(f"\nPortfolio Before:")
        print(f"  Cash: ${bar['portfolio_before']['cash']:.2f}")
        print(f"  Total Equity: ${bar['portfolio_before'].get('total_equity', 0):.2f}")
        print(f"  Positions: {bar['portfolio_before'].get('positions', {})}")
        print(f"  Open Trades: {len(bar['portfolio_before'].get('open_trades', []))}")
        
        # Show open trades details
        if bar['portfolio_before'].get('open_trades'):
            print(f"\n  Open Trade Details:")
            for trade in bar['portfolio_before']['open_trades']:
                print(f"    {trade}")
        
        # Check all keys in the bar
        print(f"\nAll keys in this bar:")
        for key in bar.keys():
            if key not in ['ohlc', 'indicators', 'portfolio_before']:
                print(f"  - {key}: {bar[key]}")
