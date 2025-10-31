# 🚀 CHEATSHEET - Comandos Rápidos

Referencia rápida de comandos más usados.

## 🎯 Inicio Rápido

```bash
# Quickstart interactivo (recomendado para empezar)
./backtesting/quickstart.sh

# Tests automatizados
python backtesting/test_system.py            # Tests completos
python backtesting/test_system.py --quick    # Solo tests rápidos
```

## 📊 Backtesting

### Básico

```bash
# Backtesting completo (todos los símbolos)
python backtesting/run_backtest.py

# Un símbolo específico
python backtesting/run_backtest.py --symbol AAPL

# Últimos N días
python backtesting/run_backtest.py --days 30
python backtesting/run_backtest.py --days 60
python backtesting/run_backtest.py --days 90
```

### Modos Predefinidos

```bash
# Conservador (risk 1%, max 3 posiciones, señal mín 65)
python backtesting/run_backtest.py --conservative

# Agresivo (risk 2.5%, max 7 posiciones, señal mín 55)
python backtesting/run_backtest.py --aggressive
```

### Personalizado

```bash
# Capital personalizado
python backtesting/run_backtest.py --capital 50000

# Riesgo personalizado
python backtesting/run_backtest.py --risk 2.0

# Señal mínima más alta
python backtesting/run_backtest.py --min-signal 70

# Combinado
python backtesting/run_backtest.py --symbol AAPL --days 60 --capital 20000 --risk 1.0
```

### Opciones Avanzadas

```bash
# Sin validación de datos (no recomendado)
python backtesting/run_backtest.py --no-validate

# Sin exit manager
python backtesting/run_backtest.py --no-exit-manager
```

## 🔍 Validación de Datos

### Python

```python
# Validar un símbolo
from backtesting.data_validator import DataValidator

validator = DataValidator()
report = validator.validate_symbol("AAPL")
print(report.summary())

# Validar todos
from backtesting.data_validator import validate_all_symbols
import config

reports = validate_all_symbols(config.SYMBOLS)
```

### Desde CLI

```bash
# Test del validador
python3 << 'EOF'
from backtesting.data_validator import DataValidator
validator = DataValidator()
report = validator.validate_symbol("AAPL")
print(report.summary())
EOF
```

## 📈 Análisis de Resultados

### Ver último resumen

```bash
cat $(ls -t backtesting/results/summary_*.txt | head -1)
```

### Ver último JSON

```bash
python3 << 'EOF'
import json
import glob

files = sorted(glob.glob('backtesting/results/results_*.json'), reverse=True)
if files:
    with open(files[0]) as f:
        results = json.load(f)

    m = results['metrics']
    print(f"Return: {m['return_pct']:.2f}%")
    print(f"Win rate: {m['win_rate']:.1f}%")
    print(f"Profit factor: {m['profit_factor']:.2f}")
    print(f"Trades: {m['total_trades']}")
EOF
```

### Comparar resultados

```bash
python backtesting/compare_results.py
```

### Ver trades en CSV

```bash
# Abrir con less
less $(ls -t backtesting/results/trades_*.csv | head -1)

# O con Python pandas
python3 << 'EOF'
import pandas as pd
import glob

files = sorted(glob.glob('backtesting/results/trades_*.csv'), reverse=True)
if files:
    df = pd.read_csv(files[0])
    print(df.head(10))
EOF
```

## 🗄️ Base de Datos

### Verificar datos disponibles

```bash
python3 << 'EOF'
from database.connection import get_connection

conn = get_connection()
cursor = conn.cursor()

cursor.execute("SELECT symbol, COUNT(*) FROM indicators_data GROUP BY symbol")
for symbol, count in cursor.fetchall():
    print(f"{symbol}: {count:,} filas")

conn.close()
EOF
```

### Poblar base de datos

```bash
# Inicializar
python database/models.py

# Poblar con datos
python historical_data/populate_db.py
```

### Ver últimos datos de un símbolo

```bash
python3 << 'EOF'
from database.connection import get_connection
import pandas as pd

conn = get_connection()
df = pd.read_sql_query(
    "SELECT timestamp, symbol, close_price, rsi_value FROM indicators_data WHERE symbol = 'AAPL' ORDER BY timestamp DESC LIMIT 10",
    conn
)
print(df)
conn.close()
EOF
```

## 🧪 Testing

### Tests individuales

```python
# Test validador
python backtesting/data_validator.py

# Test signal replicator
python backtesting/signal_replicator.py

# Test position replicator
python backtesting/position_replicator.py

# Test exit replicator
python backtesting/exit_replicator.py
```

### Suite completa

```bash
# Tests automatizados completos
python backtesting/test_system.py

# Solo tests rápidos
python backtesting/test_system.py --quick
```

## 📊 Análisis por Símbolo

```python
from backtesting.performance_analyzer import PerformanceAnalyzer
import json, glob

# Cargar último resultado
files = sorted(glob.glob('backtesting/results/results_*.json'), reverse=True)
with open(files[0]) as f:
    results = json.load(f)

# Analizar
analyzer = PerformanceAnalyzer()
by_symbol = analyzer.analyze_by_symbol(results['trades'])

# Mostrar
for symbol, metrics in by_symbol.items():
    print(f"{symbol}: Win Rate {metrics['win_rate']:.1f}%, P&L ${metrics['total_pnl']:.2f}")
```

## 📖 Documentación

```bash
# README principal
cat backtesting/README.md

# Guía de testing
cat backtesting/GUIA_TESTING.md

# Este cheatsheet
cat backtesting/CHEATSHEET.md
```

## 🔧 Troubleshooting

### Sin datos

```bash
# Verificar BD existe
ls -lh database/trading_data.db

# Si no existe, poblar
python historical_data/populate_db.py
```

### Score de datos bajo

```bash
# Ver detalles de validación
python3 << 'EOF'
from backtesting.data_validator import DataValidator

validator = DataValidator()
report = validator.validate_symbol("AAPL")

print(f"Score: {report.overall_score}/100")
print(f"Issues: {len(report.issues)}")

for issue in report.issues[:5]:
    print(f"  {issue.severity.value}: {issue.description}")
EOF
```

### No hay trades

```bash
# Probar con señal más baja
python backtesting/run_backtest.py --min-signal 55

# O verificar que hay señales en los datos
python3 << 'EOF'
from backtesting.signal_replicator import SignalReplicator
from database.connection import get_connection
import pandas as pd

conn = get_connection()
df = pd.read_sql_query(
    "SELECT * FROM indicators_data WHERE symbol = 'AAPL' ORDER BY timestamp LIMIT 500",
    conn
)
conn.close()

df['timestamp'] = pd.to_datetime(df['timestamp'])

replicator = SignalReplicator()
signals = replicator.scan_historical_dataframe('AAPL', df, min_signal_strength=55)

print(f"Señales encontradas: {len(signals)}")
EOF
```

### Backtesting muy lento

```bash
# Reducir símbolos
python backtesting/run_backtest.py --symbol AAPL

# O reducir período
python backtesting/run_backtest.py --days 15

# O sin validación (no recomendado)
python backtesting/run_backtest.py --no-validate
```

## 📁 Estructura de Archivos

```
backtesting/
├── results/              # Resultados generados
│   ├── results_*.json   # Resultados completos
│   ├── summary_*.txt    # Resúmenes
│   ├── trades_*.csv     # Trades en CSV
│   └── backtest.log     # Log de ejecución
│
├── __init__.py          # Exports
├── config.py            # Configuración
├── backtest_engine.py   # Motor principal
├── run_backtest.py      # Script principal
├── test_system.py       # Tests automatizados
├── quickstart.sh        # Inicio rápido interactivo
│
├── README.md            # Documentación completa
├── GUIA_TESTING.md      # Guía de testing
└── CHEATSHEET.md        # Este archivo
```

## 🎯 Workflows Comunes

### 1. Primera vez

```bash
./backtesting/quickstart.sh
```

### 2. Test rápido

```bash
python backtesting/test_system.py --quick
```

### 3. Backtesting de exploración

```bash
# Probar varios símbolos
python backtesting/run_backtest.py --symbol AAPL --days 30
python backtesting/run_backtest.py --symbol MSFT --days 30
python backtesting/run_backtest.py --symbol GOOGL --days 30
```

### 4. Backtesting serio

```bash
# Backtesting completo con validación
python backtesting/run_backtest.py

# Revisar resultados
cat $(ls -t backtesting/results/summary_*.txt | head -1)

# Analizar por símbolo
python3 << 'EOF'
import json, glob
from backtesting.performance_analyzer import PerformanceAnalyzer

files = sorted(glob.glob('backtesting/results/results_*.json'), reverse=True)
with open(files[0]) as f:
    results = json.load(f)

analyzer = PerformanceAnalyzer()
by_symbol = analyzer.analyze_by_symbol(results['trades'])

for symbol, m in sorted(by_symbol.items(), key=lambda x: x[1]['total_pnl'], reverse=True):
    print(f"{symbol}: ${m['total_pnl']:8.2f} | WR {m['win_rate']:5.1f}% | PF {m['profit_factor']:4.2f}")
EOF
```

### 5. Comparar configuraciones

```bash
# Normal
python backtesting/run_backtest.py > /dev/null
mv backtesting/results/summary_*.txt backtesting/results/summary_normal.txt

# Conservador
python backtesting/run_backtest.py --conservative > /dev/null
mv backtesting/results/summary_*.txt backtesting/results/summary_conservative.txt

# Agresivo
python backtesting/run_backtest.py --aggressive > /dev/null
mv backtesting/results/summary_*.txt backtesting/results/summary_aggressive.txt

# Comparar
diff backtesting/results/summary_normal.txt backtesting/results/summary_conservative.txt
```

---

💡 **Tip**: Guarda este archivo en favoritos para acceso rápido!
