import json

# Check GLD bars on 2026-02-02
with open('backtesting/logs/audit_GLD_VWAPBounce_20260203_191529.json') as f:
    data = json.load(f)
    
    print("=== GLD BARS ON 2026-02-02 ===")
    feb2_bars = [b for b in data['bars'] if '2026-02-02' in b['timestamp']]
    print(f"Total bars on 2026-02-02: {len(feb2_bars)}\n")
    
    for bar in feb2_bars[:10]:  # Show first 10 bars
        print(f"Time: {bar['timestamp']}")
        print(f"  OHLC: O:{bar['ohlc']['Open']:.2f} H:{bar['ohlc']['High']:.2f} L:{bar['ohlc']['Low']:.2f} C:{bar['ohlc']['Close']:.2f}")
        print(f"  VWAP: {bar['indicators'].get('VWAP', 'N/A')}")
        print(f"  ATR: {bar['indicators'].get('ATR', 'N/A')}")
        print(f"  Volume_SMA: {bar['indicators'].get('Volume_SMA', 'N/A')}")
        print(f"  Signal: {bar['signal']}")
        print()

print("\n=== XLK BARS ON 2026-02-02 ===")
with open('backtesting/logs/audit_XLK_VWAPBounce_20260203_191529.json') as f:
    data = json.load(f)
    
    feb2_bars = [b for b in data['bars'] if '2026-02-02' in b['timestamp']]
    print(f"Total bars on 2026-02-02: {len(feb2_bars)}\n")
    
    for bar in feb2_bars[:10]:  # Show first 10 bars
        print(f"Time: {bar['timestamp']}")
        print(f"  OHLC: O:{bar['ohlc']['Open']:.2f} H:{bar['ohlc']['High']:.2f} L:{bar['ohlc']['Low']:.2f} C:{bar['ohlc']['Close']:.2f}")
        print(f"  VWAP: {bar['indicators'].get('VWAP', 'N/A')}")
        print(f"  ATR: {bar['indicators'].get('ATR', 'N/A')}")
        print(f"  Volume_SMA: {bar['indicators'].get('Volume_SMA', 'N/A')}")
        print(f"  Signal: {bar['signal']}")
        print()
