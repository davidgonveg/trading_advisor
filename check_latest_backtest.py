import json

# Check the LATEST backtest run
with open('backtesting/logs/audit_GLD_VWAPBounce_20260203_192048.json') as f:
    data = json.load(f)
    
    print("=== GLD LATEST BACKTEST ===")
    print(f"Period: {data['metadata']['period']}")
    print(f"Total bars: {len(data['bars'])}")
    print(f"Total trades: {len(data['trades'])}\n")
    
    # Find bars around 14:30 (when live trade happened)
    feb2_bars = [b for b in data['bars'] if '2026-02-02' in b['timestamp'] and ('14:' in b['timestamp'] or '15:' in b['timestamp'])]
    
    if feb2_bars:
        print("Bars around 14:30-15:30 on 2026-02-02:")
        for bar in feb2_bars[:5]:
            print(f"  {bar['timestamp']}: Close={bar['ohlc']['Close']:.2f}, VWAP={bar['indicators'].get('VWAP', 'N/A')}, Signal={bar['signal']}")
    
    if data['trades']:
        print(f"\nTrades on 2026-02-02:")
        for t in data['trades']:
            if '2026-02-02' in t.get('entry_time', ''):
                print(f"  {t['side']} @ {t['entry_time']} | Entry: ${t['entry_price']:.2f} | Exit: ${t.get('exit_price', 'OPEN')}")

print("\n=== XLK LATEST BACKTEST ===")
with open('backtesting/logs/audit_XLK_VWAPBounce_20260203_192048.json') as f:
    data = json.load(f)
    
    print(f"Period: {data['metadata']['period']}")
    print(f"Total bars: {len(data['bars'])}")
    print(f"Total trades: {len(data['trades'])}\n")
    
    # Find bars around 14:30 (when live trade happened)
    feb2_bars = [b for b in data['bars'] if '2026-02-02' in b['timestamp'] and ('14:' in b['timestamp'] or '15:' in b['timestamp'])]
    
    if feb2_bars:
        print("Bars around 14:30-15:30 on 2026-02-02:")
        for bar in feb2_bars[:5]:
            print(f"  {bar['timestamp']}: Close={bar['ohlc']['Close']:.2f}, VWAP={bar['indicators'].get('VWAP', 'N/A')}, Signal={bar['signal']}")
    
    if data['trades']:
        print(f"\nTrades on 2026-02-02:")
        for t in data['trades']:
            if '2026-02-02' in t.get('entry_time', ''):
                print(f"  {t['side']} @ {t['entry_time']} | Entry: ${t['entry_price']:.2f} | Exit: ${t.get('exit_price', 'OPEN')}")
