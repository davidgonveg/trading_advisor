"""
Check trades from the latest backtest run
"""
import json
import glob
from pathlib import Path

# Find the latest audit logs
log_dir = Path("backtesting/logs")
audit_files = sorted(log_dir.glob("audit_*_VWAPBounce_20260203_193130.json"))

print("="*80)
print("LATEST BACKTEST TRADES (2026-02-03 19:31:30)")
print("="*80)

for audit_file in audit_files:
    symbol = audit_file.stem.split('_')[1]
    
    with open(audit_file) as f:
        data = json.load(f)
    
    # Check for trades
    trades = data.get('trades', [])
    
    # Filter for Feb 2 trades
    feb2_trades = [t for t in trades if '2026-02-02' in t.get('entry_time', '')]
    
    if feb2_trades:
        print(f"\n{symbol}: {len(feb2_trades)} trades on 2026-02-02")
        for trade in feb2_trades:
            print(f"  - {trade['entry_time']} | {trade.get('side', 'N/A')} @ ${trade.get('entry_price', 0):.2f}")
            print(f"    Exit: {trade.get('exit_time', 'OPEN')} @ ${trade.get('exit_price', 0):.2f}")
            print(f"    P&L: ${trade.get('pnl', 0):.2f}")
    else:
        # Check bars for signals
        bars = data.get('bars', [])
        feb2_bars = [b for b in bars if '2026-02-02' in b['timestamp']]
        signals = [b for b in feb2_bars if b.get('signal') not in ['HOLD', None]]
        
        if signals:
            print(f"\n{symbol}: {len(signals)} signals on 2026-02-02 (but no trades?)")
            for sig in signals:
                print(f"  - {sig['timestamp']} | {sig['signal']}")
        else:
            print(f"\n{symbol}: No trades or signals on 2026-02-02")

print("\n" + "="*80)
