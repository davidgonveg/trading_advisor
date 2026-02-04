import json

# Load GLD audit log
with open('backtesting/logs/audit_GLD_VWAPBounce_20260203_195307.json', 'r') as f:
    gld_data = json.load(f)

# Find Feb 2 bars
feb2_bars = [b for b in gld_data['bars'] if '2026-02-02' in b['timestamp']]
signals = [b for b in feb2_bars if b['signal'] not in ['HOLD', None]]

print("GLD Feb 2 Signals:")
print(f"Total signals: {len(signals)}")

for sig in signals:
    print(f"\n{sig['timestamp']}: {sig['signal']}")
    print(f"  Price: ${sig['ohlc']['Close']:.2f}")
    print(f"  Cash: ${sig['portfolio_before']['cash']:.2f}")
    print(f"  Open trades: {len(sig['portfolio_before'].get('open_trades', []))}")
