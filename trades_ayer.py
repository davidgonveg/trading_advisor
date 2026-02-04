"""
Muestra los trades de ayer del último backtest en formato simple.
"""
import json
import glob
from datetime import datetime, timedelta

yesterday = "2026-02-02"

# Buscar archivos de auditoría más recientes
audit_files = glob.glob("backtesting/logs/audit_*_VWAPBounce_*.json")
if not audit_files:
    print("No hay archivos de backtest")
    exit(1)

latest_ts = max([f.split('_')[-1].replace('.json', '') for f in audit_files])

print(f"📊 TRADES DEL {yesterday}")
print("=" * 80)

found_any = False

for symbol in ['GLD', 'XLK', 'SPY', 'QQQ', 'SMH', 'XLE', 'XLF', 'IWM']:
    file = f"backtesting/logs/audit_{symbol}_VWAPBounce_{latest_ts}.json"
    try:
        with open(file) as f:
            data = json.load(f)
        
        # Buscar barras del 2026-02-02 con señales
        bars_yesterday = [b for b in data['bars'] if yesterday in b['timestamp']]
        signals = [b for b in bars_yesterday if b.get('signal') not in ['HOLD', None]]
        
        if signals:
            found_any = True
            print(f"\n🔹 {symbol}")
            for bar in signals:
                ts = bar['timestamp'].split('T')[1][:5] if 'T' in bar['timestamp'] else bar['timestamp']
                signal = bar['signal']
                price = bar['ohlc']['Close']
                vwap = bar['indicators'].get('VWAP', 'N/A')
                print(f"   {ts} | {signal:4} @ ${price:.2f} | VWAP: ${vwap}")
    except:
        pass

if not found_any:
    print(f"\n❌ No se encontraron señales para {yesterday}")
    print("\n💡 Esto puede significar que:")
    print("   - Las condiciones de entrada no se cumplieron ese día")
    print("   - Los trades se ejecutaron en días anteriores/posteriores")
    
print("\n" + "=" * 80)
print(f"📁 Archivos completos en: backtesting/logs/audit_*_{latest_ts}.json")
