# 🧪 Suite de Tests del Trading Advisor

Suite comprehensiva de tests para verificar el correcto funcionamiento de todos los componentes del sistema de trading.

## 📋 Contenido

### Tests Disponibles

1. **test_database.py** - Tests de base de datos
   - Estructura de tablas
   - Integridad de datos (OHLC, duplicados, valores negativos)
   - Detección de gaps temporales
   - Estadísticas y performance

2. **test_indicators.py** - Tests de indicadores técnicos
   - RSI, MACD, VWAP, ROC, Bollinger Bands, ATR
   - Validación de rangos
   - Edge cases (datos planos, alta volatilidad)
   - Performance

3. **test_gap_filling.py** - Tests de gap filling
   - Detección de gaps (pequeños, overnight, weekend)
   - Clasificación por tipo y severidad
   - Relleno de gaps con datos reales
   - Validación de calidad

4. **test_positions.py** - Tests de position tracking
   - Registro de posiciones
   - Actualización de niveles (entries, exits, stop)
   - Cálculo de métricas (P&L, avg entry)
   - Cierre de posiciones

5. **test_backtesting.py** - Tests de backtesting
   - Configuración
   - Validación de datos
   - Ejecución de backtests
   - Cálculo de métricas (win rate, profit factor, drawdown)

6. **test_integration.py** - Tests de integración end-to-end
   - Flujo completo de datos a señales
   - Escenarios realistas (trending, volatile, consolidation)
   - Ciclo completo de trading

## 🚀 Ejecución

### Ejecutar todos los tests

```bash
cd test
pytest -v
```

### Ejecutar tests específicos

```bash
# Solo tests de base de datos
pytest test_database.py -v

# Solo tests de indicadores
pytest test_indicators.py -v

# Solo tests rápidos (excluir lentos)
pytest -v -m "not slow"
```

### Ejecutar por categoría (markers)

```bash
# Solo tests de base de datos
pytest -v -m database

# Solo tests de gaps
pytest -v -m gaps

# Solo tests de integración
pytest -v -m integration

# Excluir tests lentos
pytest -v -m "not slow"
```

### Opciones útiles

```bash
# Modo verbose con detalles
pytest -v --tb=short

# Mostrar print statements
pytest -v -s

# Ejecutar hasta el primer fallo
pytest -x

# Ejecutar solo tests que fallaron antes
pytest --lf

# Generar reporte de cobertura
pytest --cov=. --cov-report=html

# Ejecutar en paralelo (más rápido)
pytest -n auto
```

## 📊 Markers Disponibles

Los tests están organizados con markers para ejecución selectiva:

- `@pytest.mark.database` - Tests de base de datos
- `@pytest.mark.indicators` - Tests de indicadores
- `@pytest.mark.gaps` - Tests de gap filling
- `@pytest.mark.positions` - Tests de posiciones
- `@pytest.mark.backtest` - Tests de backtesting
- `@pytest.mark.integration` - Tests de integración
- `@pytest.mark.slow` - Tests lentos (pueden omitirse)

## 📝 Estructura de Tests

```
test/
├── conftest.py              # Configuración y fixtures
├── test_database.py         # Tests de BD
├── test_indicators.py       # Tests de indicadores
├── test_gap_filling.py      # Tests de gaps
├── test_positions.py        # Tests de posiciones
├── test_backtesting.py      # Tests de backtesting
├── test_integration.py      # Tests de integración
├── pytest.ini               # Configuración pytest
├── README.md                # Este archivo
└── __init__.py              # Package marker
```

## ✅ Qué Verifican los Tests

### Integridad de Datos
- ✅ Sin timestamps duplicados
- ✅ Consistencia OHLC (High >= Low, etc.)
- ✅ Sin precios negativos
- ✅ Sin volúmenes negativos
- ✅ RSI en rango 0-100
- ✅ Sin gaps en datos continuos

### Indicadores Técnicos
- ✅ RSI detecta sobreventa/sobrecompra
- ✅ MACD detecta cruces alcistas/bajistas
- ✅ VWAP desviación razonable
- ✅ Bollinger Bands en orden correcto
- ✅ ROC detecta momentum
- ✅ ATR clasifica volatilidad

### Gap Filling
- ✅ Detecta gaps pequeños, overnight, weekend
- ✅ Clasifica por severidad
- ✅ Rellena con datos reales cuando posible
- ✅ Preserva gaps de fin de semana
- ✅ Calcula score de calidad

### Position Tracking
- ✅ Registra posiciones correctamente
- ✅ Actualiza niveles de entrada/salida
- ✅ Calcula precio medio correcto
- ✅ Calcula P&L no realizado
- ✅ Progresión de estados (PENDING → FILLED → CLOSED)

### Backtesting
- ✅ Valida calidad de datos antes de backtest
- ✅ Ejecuta trades correctamente
- ✅ Calcula comisiones y slippage
- ✅ Genera equity curve
- ✅ Calcula métricas (win rate, profit factor, drawdown)

### Integración
- ✅ Flujo completo datos → indicadores → señales → posiciones
- ✅ Escenarios realistas (trending, volatile, consolidation)
- ✅ Manejo de edge cases (datos vacíos, punto único)

## 🔧 Fixtures Disponibles

El archivo `conftest.py` proporciona fixtures reutilizables:

- `temp_db` - Base de datos temporal
- `populated_db` - BD con datos de prueba
- `sample_ohlcv_data` - DataFrame OHLCV de muestra
- `sample_ohlcv_with_gaps` - Datos con gaps intencionados
- `mock_trading_signal` - Señal de trading de prueba
- `mock_position_plan` - Plan de posición de prueba
- `position_tracker_instance` - Position tracker sin BD
- `indicators_instance` - Calculador de indicadores
- `gap_detector_instance` - Detector de gaps

## 📈 Cobertura Esperada

Los tests cubren:

- ✅ **Base de datos**: 100% de tablas, 90%+ de funciones
- ✅ **Indicadores**: Todos los indicadores implementados
- ✅ **Gap Filling**: Todos los tipos de gaps
- ✅ **Positions**: Todo el ciclo de vida
- ✅ **Backtesting**: Flujo completo + métricas
- ✅ **Integración**: Escenarios end-to-end

## 🐛 Debugging Tests

Si un test falla:

```bash
# Ver traceback completo
pytest test_database.py::TestDataIntegrity::test_ohlc_consistency -vv

# Debugger interactivo
pytest --pdb

# Ver warnings
pytest -v -W all
```

## 📊 Reportes

### Generar reporte HTML

```bash
pytest --html=report.html --self-contained-html
```

### Generar reporte de cobertura

```bash
pytest --cov=. --cov-report=html
open htmlcov/index.html
```

## 💡 Tips

1. **Ejecutar tests frecuentemente** durante desarrollo
2. **Usar `-x`** para parar en primer fallo
3. **Usar `-v`** para ver qué tests pasan/fallan
4. **Usar markers** para ejecutar solo lo relevante
5. **Revisar fixtures** en conftest.py para reutilizar código

## 🔍 Troubleshooting

### "ModuleNotFoundError"
```bash
# Asegurarse de estar en el directorio correcto
cd /path/to/trading_advisor
pytest test/
```

### "Database locked"
```bash
# Los tests usan BD temporal, no debería pasar
# Si pasa, cerrar conexiones manuales
```

### Tests muy lentos
```bash
# Omitir tests marcados como 'slow'
pytest -v -m "not slow"

# Ejecutar en paralelo
pytest -n auto
```

## 📚 Recursos

- [Pytest Documentation](https://docs.pytest.org/)
- [Testing Best Practices](https://docs.pytest.org/en/stable/goodpractices.html)
- [Fixtures](https://docs.pytest.org/en/stable/fixture.html)
- [Markers](https://docs.pytest.org/en/stable/mark.html)

---

**¿Todos los tests pasan?** ✅ El sistema está funcionando correctamente.

**Algunos tests fallan?** ❌ Revisar los errores y corregir el código.
