import json

print("="*80)
print("ANÁLISIS DEL BACKTEST MÁS RECIENTE - GLD - 2026-02-02")
print("="*80)

# Usar el audit log más reciente
with open('backtesting/logs/audit_GLD_VWAPBounce_20260203_195307.json') as f:
    data = json.load(f)

# Buscar trades del 2 de febrero
trades = [t for t in data.get('trades', []) if '2026-02-02' in t.get('entry_time', '')]
print(f"\nTRADES ejecutados en Feb 2: {len(trades)}")
for t in trades:
    side = t.get('side', 'N/A')
    entry_time = t.get('entry_time', 'N/A')
    entry_price = t.get('entry_price', 0)
    print(f"  {entry_time} | {side} @ ${entry_price:.2f}")

# Buscar señales (barras con signal != HOLD)
print("\n" + "="*80)
bars = [b for b in data.get('bars', []) if '2026-02-02' in b['timestamp'] and b.get('signal') not in ['HOLD', None]]
print(f"SEÑALES detectadas en Feb 2: {len(bars)}")
for b in bars:
    timestamp = b['timestamp']
    signal = b['signal']
    ohlc = b.get('ohlc', {})
    close = ohlc.get('Close', 0)
    print(f"  {timestamp} | {signal} @ ${close:.2f}")

print("\n" + "="*80)
print("COMPARACIÓN CON LIVE TRADING:")
print("="*80)
print("Live trading guardó: 2 alertas (XLK LONG + GLD SHORT a las 15:30)")
print(f"Backtest detectó: {len(bars)} señales")
print(f"Backtest ejecutó: {len(trades)} trades")
print("="*80)
