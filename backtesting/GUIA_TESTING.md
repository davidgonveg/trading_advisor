# 🧪 GUÍA COMPLETA DE TESTING - Sistema de Backtesting

Guía paso a paso para probar y validar el sistema completo de backtesting.

## 📋 Tabla de Contenidos

1. [Verificación Inicial](#1-verificación-inicial)
2. [Test del Validador de Datos](#2-test-del-validador-de-datos)
3. [Test de Componentes Individuales](#3-test-de-componentes-individuales)
4. [Backtesting de Prueba (1 Símbolo)](#4-backtesting-de-prueba-1-símbolo)
5. [Backtesting Completo](#5-backtesting-completo)
6. [Análisis de Resultados](#6-análisis-de-resultados)
7. [Troubleshooting](#7-troubleshooting)

---

## 1. Verificación Inicial

### 1.1 Verificar Estructura

```bash
# Desde la raíz del proyecto
cd /home/user/trading_advisor

# Ver estructura de backtesting
ls -la backtesting/
```

**Deberías ver:**
- 13 archivos Python
- README.md y GUIA_TESTING.md
- Todos los módulos implementados

### 1.2 Verificar Base de Datos

```bash
# Verificar que existe la BD
ls -lh database/trading_data.db
```

**Si NO existe**, crear y poblar:
```bash
# Inicializar BD
python database/models.py

# Poblar con datos (esto puede tardar)
python historical_data/populate_db.py
```

### 1.3 Verificar Datos Disponibles

```python
# Desde Python o en un script de prueba
python3 << 'PYEOF'
from database.connection import get_connection

conn = get_connection()
cursor = conn.cursor()

# Ver cuántos datos hay
cursor.execute("SELECT symbol, COUNT(*) FROM indicators_data GROUP BY symbol")
results = cursor.fetchall()

print("📊 DATOS DISPONIBLES:")
print("-" * 50)
for symbol, count in results:
    print(f"  {symbol}: {count:,} filas")

conn.close()
PYEOF
```

**Esperado:** Al menos 100-500 filas por símbolo (mínimo para backtesting).

---

## 2. Test del Validador de Datos

### 2.1 Test Básico del Validador

```bash
# Test del validador con AAPL
python3 << 'PYEOF'
import logging
logging.basicConfig(level=logging.INFO)

from backtesting.data_validator import DataValidator

print("=" * 70)
print("🔍 TEST DEL VALIDADOR DE DATOS")
print("=" * 70)

validator = DataValidator()

# Validar AAPL
print("\nValidando AAPL...")
report = validator.validate_symbol("AAPL")

# Mostrar resumen
print(report.summary())

# Detalles
print("\n📋 DETALLES:")
print(f"  Backtest ready: {report.is_backtest_ready}")
print(f"  Score general: {report.overall_score:.1f}/100")
print(f"  Gaps encontrados: {report.gaps_found}")
print(f"  Completitud: {report.completeness_pct:.1f}%")

# Mostrar issues críticos
critical = report.get_critical_issues()
if critical:
    print("\n🚨 ISSUES CRÍTICOS:")
    for issue in critical:
        print(f"  • {issue.description}")
        if issue.recommendation:
            print(f"    💡 {issue.recommendation}")
else:
    print("\n✅ No hay issues críticos")

print("\n" + "=" * 70)
PYEOF
```

**Esperado:**
- Score >= 70/100
- `is_backtest_ready = True`
- Pocos o ningún issue crítico

### 2.2 Validar Todos los Símbolos

```bash
python3 << 'PYEOF'
import logging
logging.basicConfig(level=logging.INFO)

from backtesting.data_validator import validate_all_symbols
import config

print("=" * 70)
print("🔍 VALIDACIÓN DE TODOS LOS SÍMBOLOS")
print("=" * 70)

symbols = config.SYMBOLS
print(f"\nValidando {len(symbols)} símbolos...")

reports = validate_all_symbols(symbols)

print("\n📊 RESUMEN:")
print("-" * 70)
for symbol, report in reports.items():
    status = "✅" if report.is_backtest_ready else "❌"
    print(f"{status} {symbol}: Score {report.overall_score:.1f}/100 - {report.total_rows:,} filas")

# Contar ready
ready_count = sum(1 for r in reports.values() if r.is_backtest_ready)
print(f"\n✅ Símbolos ready: {ready_count}/{len(reports)}")
print("=" * 70)
PYEOF
```

---

## 3. Test de Componentes Individuales

### 3.1 Test del Signal Replicator

```bash
python3 << 'PYEOF'
import logging
logging.basicConfig(level=logging.INFO)

from backtesting.signal_replicator import SignalReplicator
from database.connection import get_connection
import pandas as pd

print("=" * 70)
print("📡 TEST DEL SIGNAL REPLICATOR")
print("=" * 70)

# Cargar datos de AAPL
symbol = "AAPL"
print(f"\nCargando datos de {symbol}...")

conn = get_connection()
query = """
SELECT * FROM indicators_data
WHERE symbol = ?
ORDER BY timestamp ASC
LIMIT 500
"""
df = pd.read_sql_query(query, conn, params=[symbol])
conn.close()

print(f"  ✅ {len(df)} filas cargadas")

# Crear replicator y escanear
df['timestamp'] = pd.to_datetime(df['timestamp'])
replicator = SignalReplicator()

print(f"\nEscaneando {len(df)} barras...")
signals = replicator.scan_historical_dataframe(symbol, df, min_signal_strength=65)

print(f"\n📊 RESULTADOS:")
print(f"  Señales encontradas: {len(signals)}")

if signals:
    print(f"\n🎯 PRIMERAS 5 SEÑALES:")
    for i, (idx, signal) in enumerate(signals[:5], 1):
        print(f"\n  {i}. {signal.timestamp}")
        print(f"     Tipo: {signal.signal_type}")
        print(f"     Fuerza: {signal.signal_strength} pts")
        print(f"     Calidad: {signal.entry_quality}")
        print(f"     Precio: ${signal.current_price:.2f}")
        print(f"     Confianza: {signal.confidence_level}")

print("\n" + "=" * 70)
PYEOF
```

**Esperado:**
- Al menos 1-5 señales encontradas
- Señales con fuerza >= 65
- Precios realistas

### 3.2 Test del Position Replicator

```bash
python3 << 'PYEOF'
import logging
logging.basicConfig(level=logging.INFO)

from backtesting.position_replicator import PositionReplicator
from scanner import TradingSignal
from datetime import datetime

print("=" * 70)
print("💼 TEST DEL POSITION REPLICATOR")
print("=" * 70)

# Crear señal de prueba
test_signal = TradingSignal(
    symbol="AAPL",
    timestamp=datetime.now(),
    signal_type="LONG",
    signal_strength=75,
    confidence_level="HIGH",
    current_price=150.0,
    entry_quality="FULL_ENTRY",
    indicator_scores={
        'MACD': 20, 'RSI': 18, 'VWAP': 15,
        'ROC': 20, 'BOLLINGER': 15, 'VOLUME': 10
    },
    indicator_signals={
        'MACD': 'BULLISH_CROSS', 'RSI': 'OVERSOLD',
        'VWAP': 'AT_VWAP', 'ROC': 'STRONG_MOMENTUM',
        'BOLLINGER': 'LOWER_BAND', 'VOLUME': 'HIGH'
    }
)

print("\n📋 Señal de prueba:")
print(f"  Symbol: {test_signal.symbol}")
print(f"  Type: {test_signal.signal_type}")
print(f"  Strength: {test_signal.signal_strength} pts")
print(f"  Price: ${test_signal.current_price:.2f}")

# Calcular posición
replicator = PositionReplicator(capital=10000.0, risk_per_trade=1.5)
print("\n💰 Calculando posición con $10,000 y 1.5% risk...")

position_plan = replicator.calculate_position(test_signal, 10000.0)

if position_plan:
    print("\n✅ POSICIÓN CALCULADA:")
    print(f"\n  Entradas:")
    print(f"    Entry 1: ${position_plan.entry_1_price:.2f} x {position_plan.entry_1_quantity} shares")
    print(f"    Entry 2: ${position_plan.entry_2_price:.2f} x {position_plan.entry_2_quantity} shares")
    print(f"    Entry 3: ${position_plan.entry_3_price:.2f} x {position_plan.entry_3_quantity} shares")
    print(f"\n  Stop Loss: ${position_plan.stop_loss:.2f}")
    print(f"\n  Take Profits:")
    print(f"    TP1: ${position_plan.take_profit_1:.2f}")
    print(f"    TP2: ${position_plan.take_profit_2:.2f}")
    print(f"    TP3: ${position_plan.take_profit_3:.2f}")
    print(f"    TP4: ${position_plan.take_profit_4:.2f}")
    print(f"\n  Total shares: {position_plan.total_position_size}")
    print(f"  Max risk: ${position_plan.max_capital_at_risk:.2f}")
    print(f"  Max R:R: {position_plan.max_risk_reward:.1f}R")
    print(f"  ATR: ${position_plan.atr:.2f}")
else:
    print("\n❌ No se pudo calcular posición")

print("\n" + "=" * 70)
PYEOF
```

**Esperado:**
- Posición calculada correctamente
- 3 niveles de entrada
- 4 take profits
- Stop loss razonable
- R:R > 1.5

### 3.3 Test del Exit Replicator

```bash
python3 << 'PYEOF'
import logging
logging.basicConfig(level=logging.INFO)

from backtesting.exit_replicator import ExitReplicator
from scanner import TradingSignal
from datetime import datetime
import pandas as pd

print("=" * 70)
print("🚪 TEST DEL EXIT REPLICATOR")
print("=" * 70)

# Crear señal LONG
signal = TradingSignal(
    symbol="AAPL",
    timestamp=datetime.now(),
    signal_type="LONG",
    signal_strength=75,
    confidence_level="HIGH",
    current_price=150.0,
    entry_quality="FULL_ENTRY",
    indicator_scores={},
    indicator_signals={}
)

print("\n📋 Señal original: LONG @ $150.00")

# Escenario 1: Condiciones normales
print("\n1️⃣  ESCENARIO: Condiciones normales")
normal_row = pd.Series({
    'rsi_value': 55,
    'macd_histogram': 0.05,
    'roc_value': 1.0,
    'bb_position': 0.6,
    'volume_oscillator': 20,
    'atr_percentage': 2.0,
})

replicator = ExitReplicator()
should_exit, urgency, score, reason = replicator.evaluate_exit_conditions(
    original_signal=signal,
    current_row=normal_row,
    entry_price=150.0,
    current_price=152.0,
    bars_held=10
)

print(f"  Should exit: {should_exit}")
print(f"  Urgency: {urgency.value}")
print(f"  Score: {score:.1f}")
print(f"  Reason: {reason if reason else 'N/A'}")

# Escenario 2: Deterioro severo
print("\n2️⃣  ESCENARIO: Deterioro severo (RSI alto, MACD negativo, ROC negativo)")
deteriorado_row = pd.Series({
    'rsi_value': 82,  # Sobrecomprado extremo
    'macd_histogram': -0.1,  # Momentum bajista
    'roc_value': -2.5,  # ROC negativo
    'bb_position': 0.96,  # Banda superior
    'volume_oscillator': -60,  # Volumen vendedor
    'atr_percentage': 2.5,
})

should_exit, urgency, score, reason = replicator.evaluate_exit_conditions(
    original_signal=signal,
    current_row=deteriorado_row,
    entry_price=150.0,
    current_price=148.0,  # Precio cayendo
    bars_held=20
)

print(f"  Should exit: {should_exit}")
print(f"  Urgency: {urgency.value}")
print(f"  Score: {score:.1f}")
print(f"  Reason: {reason if reason else 'N/A'}")

print("\n✅ Exit Replicator funcionando correctamente")
print("=" * 70)
PYEOF
```

**Esperado:**
- Escenario 1: NO exit (condiciones normales)
- Escenario 2: EXIT recomendado/urgente (deterioro severo)

---

## 4. Backtesting de Prueba (1 Símbolo)

### 4.1 Test Rápido con AAPL

```bash
echo "=" | awk '{for(i=0;i<70;i++)printf "="; print ""}'
echo "🚀 TEST RÁPIDO: BACKTESTING DE AAPL"
echo "=" | awk '{for(i=0;i<70;i++)printf "="; print ""}'
echo ""

python backtesting/run_backtest.py --symbol AAPL --days 30
```

**Esto debería:**
1. ✅ Validar datos de AAPL
2. ✅ Cargar ~2,000-3,000 barras (30 días)
3. ✅ Ejecutar backtesting completo
4. ✅ Generar métricas
5. ✅ Crear reportes en `backtesting/results/`

**Tiempo estimado:** 30-60 segundos

### 4.2 Verificar Resultados

```bash
echo ""
echo "📊 VERIFICANDO RESULTADOS..."
echo ""

# Ver archivos generados
echo "📄 Archivos generados:"
ls -lth backtesting/results/ | head -10

echo ""
echo "📋 Último resumen:"
cat $(ls -t backtesting/results/summary_*.txt | head -1)
```

### 4.3 Verificar JSON

```bash
python3 << 'PYEOF'
import json
import glob

# Cargar último resultado
files = sorted(glob.glob('backtesting/results/results_*.json'), reverse=True)
if files:
    with open(files[0]) as f:
        results = json.load(f)

    print("=" * 70)
    print("📊 ANÁLISIS DEL JSON")
    print("=" * 70)

    metrics = results.get('metrics', {})
    trades = results.get('trades', [])

    print(f"\n💰 RENDIMIENTO:")
    print(f"  Capital inicial: ${metrics.get('initial_capital', 0):,.2f}")
    print(f"  Capital final: ${metrics.get('final_capital', 0):,.2f}")
    print(f"  Return: {metrics.get('return_pct', 0):.2f}%")

    print(f"\n📊 TRADES:")
    print(f"  Total: {metrics.get('total_trades', 0)}")
    print(f"  Ganadores: {metrics.get('winning_trades', 0)}")
    print(f"  Perdedores: {metrics.get('losing_trades', 0)}")
    print(f"  Win rate: {metrics.get('win_rate', 0):.1f}%")

    print(f"\n📈 MÉTRICAS:")
    print(f"  Profit factor: {metrics.get('profit_factor', 0):.2f}")
    print(f"  Max drawdown: {metrics.get('max_drawdown_pct', 0):.2f}%")
    print(f"  Sharpe ratio: {metrics.get('sharpe_ratio', 0):.2f}")

    # Mostrar algunos trades
    print(f"\n🎯 TRADES (primeros 3):")
    for i, trade in enumerate(trades[:3], 1):
        print(f"\n  {i}. {trade['symbol']} {trade['direction']}")
        print(f"     Entry: ${trade['avg_entry_price']:.2f}")
        print(f"     P&L: ${trade['total_pnl']:.2f}")
        print(f"     Exit reason: {trade['exit_reason']}")

    print("\n" + "=" * 70)
else:
    print("❌ No se encontraron resultados JSON")
PYEOF
```

---

## 5. Backtesting Completo

### 5.1 Todos los Símbolos (Modo Normal)

```bash
echo "=" | awk '{for(i=0;i<70;i++)printf "="; print ""}'
echo "🚀 BACKTESTING COMPLETO - TODOS LOS SÍMBOLOS"
echo "=" | awk '{for(i=0;i<70;i++)printf "="; print ""}'
echo ""
echo "⚠️  ADVERTENCIA: Esto puede tardar 5-15 minutos"
echo "   Procesará todos los símbolos con datos disponibles"
echo ""
read -p "¿Continuar? (y/N): " confirm

if [ "$confirm" = "y" ] || [ "$confirm" = "Y" ]; then
    python backtesting/run_backtest.py
else
    echo "❌ Cancelado"
fi
```

### 5.2 Modo Conservador

```bash
echo "🛡️  Ejecutando en modo CONSERVADOR..."
python backtesting/run_backtest.py --conservative
```

**Características:**
- Risk: 1% (vs 1.5% normal)
- Max posiciones: 3 (vs 5 normal)
- Señal mínima: 65 pts (vs 55 normal)
- Calidad mínima: FULL_ENTRY (vs PARTIAL_ENTRY normal)

### 5.3 Modo Agresivo

```bash
echo "⚡ Ejecutando en modo AGRESIVO..."
python backtesting/run_backtest.py --aggressive
```

**Características:**
- Risk: 2.5% (vs 1.5% normal)
- Max posiciones: 7 (vs 5 normal)
- Señal mínima: 55 pts
- Calidad mínima: PARTIAL_ENTRY

---

## 6. Análisis de Resultados

### 6.1 Comparar Resultados

Crea un script para comparar diferentes ejecuciones:

```bash
cat > backtesting/compare_results.py << 'PYEOF'
#!/usr/bin/env python3
"""Comparar resultados de múltiples backtests"""

import json
import glob
from datetime import datetime

files = sorted(glob.glob('backtesting/results/results_*.json'), reverse=True)

if not files:
    print("❌ No hay resultados para comparar")
    exit(1)

print("=" * 70)
print("📊 COMPARACIÓN DE RESULTADOS")
print("=" * 70)

for i, filepath in enumerate(files[:5], 1):  # Últimos 5
    with open(filepath) as f:
        results = json.load(f)

    metrics = results.get('metrics', {})
    config = results.get('config', {})

    # Extraer timestamp del filename
    timestamp = filepath.split('_')[1] + '_' + filepath.split('_')[2].replace('.json', '')
    dt = datetime.strptime(timestamp, '%Y%m%d_%H%M%S')

    print(f"\n{i}. {dt.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   Símbolos: {len(config.get('symbols', []))}")
    print(f"   Capital: ${metrics.get('initial_capital', 0):,.2f}")
    print(f"   Return: {metrics.get('return_pct', 0):.2f}%")
    print(f"   Trades: {metrics.get('total_trades', 0)}")
    print(f"   Win rate: {metrics.get('win_rate', 0):.1f}%")
    print(f"   Profit factor: {metrics.get('profit_factor', 0):.2f}")
    print(f"   Max DD: {metrics.get('max_drawdown_pct', 0):.2f}%")

print("\n" + "=" * 70)
PYEOF

chmod +x backtesting/compare_results.py
python backtesting/compare_results.py
```

### 6.2 Análisis por Símbolo

```bash
python3 << 'PYEOF'
import json
import glob

files = sorted(glob.glob('backtesting/results/results_*.json'), reverse=True)
if files:
    with open(files[0]) as f:
        results = json.load(f)

    perf_by_symbol = results.get('performance_analysis', {}).get('by_symbol', {})

    if perf_by_symbol:
        print("=" * 70)
        print("📊 ANÁLISIS POR SÍMBOLO")
        print("=" * 70)

        # Ordenar por P&L
        sorted_symbols = sorted(
            perf_by_symbol.items(),
            key=lambda x: x[1]['total_pnl'],
            reverse=True
        )

        print(f"\n{'Symbol':<10} {'Trades':<8} {'Win%':<8} {'P&L':<12} {'PF':<6}")
        print("-" * 70)

        for symbol, metrics in sorted_symbols:
            print(f"{symbol:<10} {metrics['total_trades']:<8} "
                  f"{metrics['win_rate']:<8.1f} "
                  f"${metrics['total_pnl']:<11.2f} "
                  f"{metrics['profit_factor']:<6.2f}")

        print("\n" + "=" * 70)
PYEOF
```

### 6.3 Análisis LONG vs SHORT

```bash
python3 << 'PYEOF'
import json
import glob

files = sorted(glob.glob('backtesting/results/results_*.json'), reverse=True)
if files:
    with open(files[0]) as f:
        results = json.load(f)

    long_short = results.get('performance_analysis', {}).get('long_vs_short', {})

    if long_short:
        print("=" * 70)
        print("📊 ANÁLISIS LONG vs SHORT")
        print("=" * 70)

        for direction in ['LONG', 'SHORT']:
            metrics = long_short.get(direction, {})
            print(f"\n{direction}:")
            print(f"  Trades: {metrics.get('total_trades', 0)}")
            print(f"  Win rate: {metrics.get('win_rate', 0):.1f}%")
            print(f"  P&L: ${metrics.get('total_pnl', 0):.2f}")
            print(f"  Profit factor: {metrics.get('profit_factor', 0):.2f}")

        print("\n" + "=" * 70)
PYEOF
```

---

## 7. Troubleshooting

### Problema 1: "No se encontraron datos"

**Causa:** Base de datos vacía o sin datos del símbolo

**Solución:**
```bash
# Verificar datos disponibles
python3 << 'PYEOF'
from database.connection import get_connection
conn = get_connection()
cursor = conn.cursor()
cursor.execute("SELECT DISTINCT symbol FROM indicators_data")
symbols = [row[0] for row in cursor.fetchall()]
print(f"Símbolos en BD: {symbols}")
conn.close()
PYEOF

# Si está vacía, poblar:
python historical_data/populate_db.py
```

### Problema 2: "Score de datos bajo"

**Causa:** Datos incompletos, con gaps o indicadores faltantes

**Solución:**
```bash
# Ver detalles de la validación
python3 << 'PYEOF'
from backtesting.data_validator import DataValidator

validator = DataValidator()
report = validator.validate_symbol("AAPL")

print(report.summary())

# Ver issues
for issue in report.issues:
    print(f"{issue.severity.value}: {issue.description}")
    if issue.recommendation:
        print(f"  💡 {issue.recommendation}")
PYEOF

# Recalcular indicadores si es necesario
python historical_data/historical_indicators_calc.py
```

### Problema 3: "No hay trades"

**Causa:** Señal mínima muy alta o datos de mala calidad

**Solución:**
```bash
# Probar con señal más baja
python backtesting/run_backtest.py --symbol AAPL --min-signal 55

# O revisar si hay señales en los datos
python3 << 'PYEOF'
from backtesting.signal_replicator import SignalReplicator
from database.connection import get_connection
import pandas as pd

conn = get_connection()
df = pd.read_sql_query(
    "SELECT * FROM indicators_data WHERE symbol = 'AAPL' ORDER BY timestamp LIMIT 1000",
    conn
)
conn.close()

df['timestamp'] = pd.to_datetime(df['timestamp'])

replicator = SignalReplicator()
signals = replicator.scan_historical_dataframe('AAPL', df, min_signal_strength=55)

print(f"Señales encontradas con threshold 55: {len(signals)}")
PYEOF
```

### Problema 4: Backtesting muy lento

**Causa:** Demasiados datos o muchos símbolos

**Solución:**
```bash
# Reducir período
python backtesting/run_backtest.py --days 30

# O un solo símbolo
python backtesting/run_backtest.py --symbol AAPL

# O sin validación (no recomendado)
python backtesting/run_backtest.py --no-validate
```

### Problema 5: Errores de import

**Causa:** Paths incorrectos

**Solución:**
```bash
# Asegurarse de ejecutar desde la raíz del proyecto
cd /home/user/trading_advisor

# Y que Python encuentre los módulos
export PYTHONPATH=/home/user/trading_advisor:$PYTHONPATH

# Luego ejecutar
python backtesting/run_backtest.py
```

---

## 📊 Checklist Final

Usa este checklist para verificar que todo funciona:

- [ ] ✅ Base de datos existe y tiene datos
- [ ] ✅ Validador funciona y da scores >= 70
- [ ] ✅ Signal replicator encuentra señales
- [ ] ✅ Position replicator calcula posiciones correctamente
- [ ] ✅ Exit replicator detecta deterioro
- [ ] ✅ Backtesting de 1 símbolo completa exitosamente
- [ ] ✅ Se generan los 3 reportes (JSON, TXT, CSV)
- [ ] ✅ Las métricas tienen sentido (win rate 30-70%, PF > 1)
- [ ] ✅ Los trades muestran entradas/salidas escalonadas
- [ ] ✅ Backtesting completo funciona
- [ ] ✅ Análisis por símbolo funciona
- [ ] ✅ Comparación de resultados funciona

---

## 🎯 Próximos Pasos

Después de completar todos los tests:

1. **Analizar qué símbolos funcionan mejor**
2. **Comparar LONG vs SHORT**
3. **Ajustar parámetros del sistema** (en config.py del proyecto principal)
4. **Re-ejecutar backtesting** para verificar mejoras
5. **Comparar con paper trading** para validar coherencia

---

## 💡 Tips Finales

- **Empezar siempre con 1 símbolo** para tests rápidos
- **Validar siempre los datos** antes de backtesting completo
- **Revisar los logs** en `backtesting/results/backtest.log`
- **Comparar resultados** entre diferentes configuraciones
- **No confiar en un solo backtest** - ejecutar varios con diferentes períodos

---

¡Buena suerte con las pruebas! 🚀
