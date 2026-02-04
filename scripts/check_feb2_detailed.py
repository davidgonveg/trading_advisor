"""Check for signals on Feb 2, 2026 in audit logs."""
import json

def check_signals(filepath, symbol):
    with open(filepath, 'r') as f:
        data = json.load(f)
    
    feb2_bars = [b for b in data['bars'] if '2026-02-02' in b['timestamp']]
    signals = [b for b in feb2_bars if b['signal'] not in ['HOLD', None]]
    
    print(f"\n{'='*80}")
    print(f"{symbol} - Feb 2, 2026 Analysis")
    print(f"{'='*80}")
    print(f"Total bars on Feb 2: {len(feb2_bars)}")
    print(f"Signals detected: {len(signals)}")
    
    for sig in signals:
        print(f"\n  Timestamp: {sig['timestamp']}")
        print(f"  Signal: {sig['signal']}")
        print(f"  Close: ${sig['ohlc']['Close']:.2f}")
        print(f"  Cash: ${sig['portfolio_before']['cash']:.2f}")
        print(f"  Open trades: {len(sig['portfolio_before'].get('open_trades', []))}")
    
    return signals

# Check both symbols
gld_signals = check_signals('backtesting/logs/audit_GLD_VWAPBounce_20260203_195307.json', 'GLD')
xlk_signals = check_signals('backtesting/logs/audit_XLK_VWAPBounce_20260203_195307.json', 'XLK')

print(f"\n{'='*80}")
print(f"SUMMARY: GLD={len(gld_signals)} signals, XLK={len(xlk_signals)} signals")
print(f"{'='*80}")
