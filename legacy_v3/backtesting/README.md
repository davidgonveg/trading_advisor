# 🔙 Sistema de Backtesting - Trading Advisor

Sistema profesional de backtesting que **replica EXACTAMENTE** el comportamiento del sistema de trading en producción.

## 📋 Características

- ✅ **Comportamiento idéntico al sistema real** - Reutiliza las clases reales: `Scanner`, `PositionCalculator`, `ExitManager`
- ✅ **Validación exhaustiva de datos** - Verifica calidad y completitud antes de backtesting
- ✅ **Time-forward testing** - Sin look-ahead bias
- ✅ **Entradas escalonadas** - 3 niveles de entrada (40%/30%/30%)
- ✅ **Salidas parciales** - 4 TPs (25%/25%/25%/25%)
- ✅ **Exit Manager** - Salidas anticipadas por deterioro técnico
- ✅ **Gestión realista de capital** - Comisiones, slippage, riesgo
- ✅ **Análisis detallado** - Por símbolo, indicadores, señales
- ✅ **Reportes completos** - JSON, TXT, CSV

## 🚀 Inicio Rápido

### Ejecutar backtesting completo

```bash
python backtesting/run_backtest.py
```

### Ejecutar para un símbolo específico

```bash
python backtesting/run_backtest.py --symbol AAPL
```

### Modos de configuración

```bash
# Modo conservador (risk 1%, max 3 posiciones)
python backtesting/run_backtest.py --conservative

# Modo agresivo (risk 2.5%, max 7 posiciones)
python backtesting/run_backtest.py --aggressive

# Últimos 60 días
python backtesting/run_backtest.py --days 60

# Custom capital y riesgo
python backtesting/run_backtest.py --capital 50000 --risk 2.0

# Señal mínima más alta
python backtesting/run_backtest.py --min-signal 70

# Sin exit manager
python backtesting/run_backtest.py --no-exit-manager
```

## 📁 Estructura

```
backtesting/
├── __init__.py                    # Exports principales
├── config.py                      # Configuración del backtesting
├── data_validator.py              # Validador de datos históricos
├── signal_replicator.py           # Wrapper del scanner real
├── position_replicator.py         # Wrapper del position calculator real
├── exit_replicator.py             # Wrapper del exit manager real
├── trade_manager.py               # Gestión de trades y posiciones
├── backtest_engine.py             # Motor principal
├── performance_analyzer.py        # Análisis de rendimiento
├── indicator_analyzer.py          # Análisis de indicadores
├── report_generator.py            # Generación de reportes
├── run_backtest.py                # Script principal
├── README.md                      # Esta documentación
└── results/                       # Reportes generados
    ├── backtest.log              # Log de ejecución
    ├── results_YYYYMMDD_HHMMSS.json
    ├── summary_YYYYMMDD_HHMMSS.txt
    └── trades_YYYYMMDD_HHMMSS.csv
```

## 🔧 Configuración

El backtesting se configura mediante la clase `BacktestConfig`:

```python
from backtesting.config import BacktestConfig

# Configuración personalizada
config = BacktestConfig(
    initial_capital=10000.0,
    risk_per_trade=1.5,
    max_concurrent_positions=5,
    symbols=["AAPL", "MSFT", "GOOGL"],
    min_signal_strength=65,
    enable_exit_manager=True,
)
```

### Parámetros principales

- `initial_capital`: Capital inicial (default: $10,000)
- `risk_per_trade`: % de capital a arriesgar por trade (default: 1.5%)
- `max_concurrent_positions`: Posiciones simultáneas máx (default: 5)
- `commission_per_share`: Comisión por acción (default: $0.005)
- `min_signal_strength`: Fuerza mínima de señal (default: 55)
- `min_entry_quality`: Calidad mínima (default: "PARTIAL_ENTRY")
- `enable_exit_manager`: Activar exit manager (default: True)
- `validate_data_before_backtest`: Validar datos (default: True)

## 📊 Validación de Datos

Antes de ejecutar backtesting, el sistema valida:

1. **Completitud** - % de datos esperados vs reales
2. **Gaps** - Detecta y reporta huecos en los datos
3. **OHLC** - Valida consistencia de precios
4. **Indicadores** - Verifica que estén calculados
5. **Volumen** - Detecta anomalías

Score mínimo requerido: **70/100**

### Validar datos manualmente

```python
from backtesting.data_validator import DataValidator

validator = DataValidator()
report = validator.validate_symbol("AAPL")

print(report.summary())
print(f"Backtest ready: {report.is_backtest_ready}")
```

## 🎯 Flujo de Ejecución

1. **Validación** - Verifica calidad de datos históricos
2. **Carga** - Lee datos desde la base de datos (tabla `indicators_data`)
3. **Procesamiento** - Barra por barra, cronológicamente:
   - Genera señales con `SignalReplicator`
   - Calcula posiciones con `PositionReplicator`
   - Ejecuta entradas escalonadas
   - Evalúa TPs, SL, Exit Manager
   - Actualiza capital y equity curve
4. **Cierre** - Cierra posiciones abiertas al final
5. **Análisis** - Calcula métricas por símbolo, indicador, etc.
6. **Reportes** - Genera JSON, TXT, CSV

## 📈 Métricas Calculadas

### Generales
- Return total y %
- Win rate
- Profit factor
- Max drawdown
- Sharpe ratio

### Por trade
- P&L realizado y no realizado
- Precio promedio de entrada
- Excursiones máximas (MFE/MAE)
- Barras mantenidas
- Comisiones y slippage

### Por símbolo
- Trades totales
- Win rate específico
- P&L total
- Profit factor

### Por indicador
- Contribución al éxito
- Mejores combinaciones
- Análisis por fuerza de señal

## 📝 Reportes Generados

### 1. JSON Completo (`results_YYYYMMDD_HHMMSS.json`)
- Configuración usada
- Métricas completas
- Todos los trades con detalles
- Equity curve
- Reportes de validación

### 2. Resumen TXT (`summary_YYYYMMDD_HHMMSS.txt`)
- Resumen ejecutivo
- Métricas principales
- Fácil de leer

### 3. Trades CSV (`trades_YYYYMMDD_HHMMSS.csv`)
- Todos los trades en formato tabular
- Importable a Excel/Google Sheets

## 🔬 Análisis Avanzado

### Análisis por símbolo

```python
from backtesting.performance_analyzer import PerformanceAnalyzer

analyzer = PerformanceAnalyzer()
symbol_performance = analyzer.analyze_by_symbol(results['trades'])

for symbol, metrics in symbol_performance.items():
    print(f"{symbol}: Win Rate {metrics['win_rate']:.1f}%, P&L ${metrics['total_pnl']:.2f}")
```

### Análisis LONG vs SHORT

```python
long_short = analyzer.analyze_long_vs_short(results['trades'])
print(f"LONG: {long_short['LONG']['win_rate']:.1f}% win rate")
print(f"SHORT: {long_short['SHORT']['win_rate']:.1f}% win rate")
```

### Análisis de indicadores

```python
from backtesting.indicator_analyzer import IndicatorAnalyzer

ind_analyzer = IndicatorAnalyzer()
indicator_contribution = ind_analyzer.analyze_indicator_contribution(results['trades'])
```

## 🐛 Troubleshooting

### Error: "No se encontraron datos"
- Ejecutar `python historical_data/populate_db.py` para cargar datos
- Verificar que la base de datos existe en `database/trading_data.db`

### Error: "Score de datos bajo"
- Ejecutar validación: `python backtesting/run_backtest.py --symbol AAPL` (con un símbolo)
- Revisar el reporte de validación
- Rellenar gaps si es necesario

### Backtesting muy lento
- Reducir número de símbolos
- Reducir período con `--days`
- Usar `--no-validate` (no recomendado)

### Resultados inesperados
- Verificar configuración (`config.py`)
- Revisar que el sistema real esté configurado igual
- Comprobar que los indicadores estén calculados correctamente

## 💡 Tips y Mejores Prácticas

1. **Validar siempre** - No saltarse la validación de datos
2. **Empezar pequeño** - Probar con un símbolo primero
3. **Comparar con paper trading** - Verificar coherencia
4. **Analizar por símbolo** - No todos los símbolos funcionan igual
5. **Revisar excursiones** - MAE/MFE son muy informativos
6. **Ajustar config** - Experimentar con risk, señales mínimas, etc.

## 🔮 Próximas Mejoras

- [ ] Walk-forward optimization
- [ ] Monte Carlo simulation
- [ ] Gráficos interactivos (Plotly)
- [ ] Análisis de sensibilidad de parámetros
- [ ] Comparación entre estrategias
- [ ] Export a TradingView

## 📞 Soporte

Si encuentras problemas o tienes sugerencias:
1. Revisar logs en `backtesting/results/backtest.log`
2. Verificar que el sistema real funcione correctamente
3. Comprobar que los datos históricos sean de calidad

---

**Nota importante**: Este sistema replica el comportamiento **IDÉNTICO** del sistema de trading real. Cualquier cambio en el sistema real debe reflejarse aquí para mantener la coherencia.
