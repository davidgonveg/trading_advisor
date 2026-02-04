import json

# Check GLD
with open('backtesting/logs/audit_GLD_VWAPBounce_20260203_191529.json') as f:
    data = json.load(f)
    print(f"GLD - Period: {data['metadata']['period']}")
    print(f"GLD - Total bars: {len(data['bars'])}")
    print(f"GLD - Total trades: {len(data['trades'])}")
    
    # Find trades on 2026-02-02
    feb2_trades = [t for t in data['trades'] if '2026-02-02' in t.get('entry_time', '')]
    if feb2_trades:
        print(f"GLD - Trades on 2026-02-02: {len(feb2_trades)}")
        for t in feb2_trades:
            print(f"  {t['side']} @ {t['entry_time']} | Entry: {t['entry_price']} | Exit: {t.get('exit_price', 'OPEN')}")

# Check XLK
with open('backtesting/logs/audit_XLK_VWAPBounce_20260203_191529.json') as f:
    data = json.load(f)
    print(f"\nXLK - Period: {data['metadata']['period']}")
    print(f"XLK - Total bars: {len(data['bars'])}")
    print(f"XLK - Total trades: {len(data['trades'])}")
    
    # Find trades on 2026-02-02
    feb2_trades = [t for t in data['trades'] if '2026-02-02' in t.get('entry_time', '')]
    if feb2_trades:
        print(f"XLK - Trades on 2026-02-02: {len(feb2_trades)}")
        for t in feb2_trades:
            print(f"  {t['side']} @ {t['entry_time']} | Entry: {t['entry_price']} | Exit: {t.get('exit_price', 'OPEN')}")
