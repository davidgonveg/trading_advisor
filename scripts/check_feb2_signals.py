"""
Quick script to check what signals were generated on 2026-02-02
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from data.storage.database import Database
import pandas as pd

db = Database()

# Check alerts table for 2026-02-02
conn = db.get_connection()
cursor = conn.cursor()

print("="*80)
print("LIVE TRADING ALERTS ON 2026-02-02")
print("="*80)

cursor.execute("""
    SELECT timestamp, symbol, signal_type, price, sl_price, tp1_price, atr, status
    FROM alerts
    WHERE date(timestamp) = '2026-02-02'
    ORDER BY timestamp
""")

alerts = cursor.fetchall()
print(f"\nFound {len(alerts)} alerts:\n")

for alert in alerts:
    ts, symbol, sig_type, price, sl, tp, atr, status = alert
    print(f"📊 {ts} | {symbol} | {sig_type}")
    price_str = f"${price:.2f}" if price else "N/A"
    sl_str = f"${sl:.2f}" if sl else "N/A"
    tp_str = f"${tp:.2f}" if tp else "N/A"
    atr_str = f"${atr:.2f}" if atr else "N/A"
    print(f"   Entry: {price_str} | SL: {sl_str} | TP: {tp_str} | ATR: {atr_str}")
    print(f"   Status: {status}\n")

conn.close()

# Check market data availability
print("\n" + "="*80)
print("MARKET DATA AVAILABILITY FOR 2026-02-02")
print("="*80)

for symbol in ['XLK', 'GLD']:
    df = db.load_market_data(symbol, "1h")
    if not df.empty:
        feb2_data = df[df.index.date == pd.Timestamp('2026-02-02', tz='UTC').date()]
        print(f"\n{symbol}: {len(feb2_data)} bars")
        if len(feb2_data) > 0:
            print(f"  First bar: {feb2_data.index[0]}")
            print(f"  Last bar: {feb2_data.index[-1]}")
    else:
        print(f"\n{symbol}: NO DATA")
