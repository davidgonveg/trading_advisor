import json

# Check ALL trades for GLD
with open('backtesting/logs/audit_GLD_VWAPBounce_20260203_192048.json') as f:
    data = json.load(f)
    
    print("=== ALL GLD TRADES ===")
    print(f"Total trades: {len(data['trades'])}\n")
    
    for i, t in enumerate(data['trades'], 1):
        entry_time = t.get('entry_time', 'N/A')
        exit_time = t.get('exit_time', 'N/A')
        entry_price = t.get('entry_price', t.get('price', 0))
        exit_price = t.get('exit_price', 0)
        pnl = t.get('pnl', t.get('profit', 0))
        print(f"{i}. {t.get('side', 'N/A')} | Entry: {entry_time} @ ${entry_price:.2f} | Exit: {exit_time} @ ${exit_price:.2f} | P&L: ${pnl:.2f}")

# Check ALL trades for XLK
with open('backtesting/logs/audit_XLK_VWAPBounce_20260203_192048.json') as f:
    data = json.load(f)
    
    print("\n=== ALL XLK TRADES ===")
    print(f"Total trades: {len(data['trades'])}\n")
    
    for i, t in enumerate(data['trades'], 1):
        entry_time = t.get('entry_time', 'N/A')
        exit_time = t.get('exit_time', 'N/A')
        entry_price = t.get('entry_price', t.get('price', 0))
        exit_price = t.get('exit_price', 0)
        pnl = t.get('pnl', t.get('profit', 0))
        print(f"{i}. {t.get('side', 'N/A')} | Entry: {entry_time} @ ${entry_price:.2f} | Exit: {exit_time} @ ${exit_price:.2f} | P&L: ${pnl:.2f}")
