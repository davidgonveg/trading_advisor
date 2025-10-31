# 🚀 Quick Start - Testing

Guía rápida para ejecutar los tests del Trading Advisor.

## 📦 Instalación

### 1. Instalar dependencias de testing

```bash
cd /home/user/trading_advisor/test
pip install -r requirements_test.txt
```

O instalar solo pytest:

```bash
pip install pytest
```

## ▶️ Ejecución

### Método 1: Script automatizado (recomendado)

```bash
cd /home/user/trading_advisor/test
./run_tests.sh
```

Opciones disponibles:
- `./run_tests.sh all` - Todos los tests
- `./run_tests.sh fast` - Solo tests rápidos
- `./run_tests.sh database` - Solo tests de BD
- `./run_tests.sh indicators` - Solo tests de indicadores
- `./run_tests.sh coverage` - Con reporte de cobertura

### Método 2: pytest directamente

```bash
cd /home/user/trading_advisor/test
pytest -v
```

## ✅ Verificación Rápida

Para verificar que todo está bien configurado:

```bash
cd /home/user/trading_advisor/test
python -c "import pytest; print('✅ pytest instalado:', pytest.__version__)"
```

## 📊 Ver Resultados

Los tests mostrarán:
- ✅ PASSED - Test pasó correctamente
- ❌ FAILED - Test falló
- ⏭️  SKIPPED - Test omitido

Ejemplo de output:
```
test_database.py::TestDatabaseStructure::test_database_initialization PASSED
test_indicators.py::TestRSI::test_rsi_calculation PASSED
test_integration.py::TestEndToEndFlow::test_full_trading_cycle PASSED

======================== 45 passed in 5.23s ========================
```

## 🐛 Troubleshooting

### "No module named pytest"
```bash
pip install pytest
```

### "ModuleNotFoundError: No module named 'config'"
```bash
# Asegúrate de estar en el directorio test/
cd /home/user/trading_advisor/test
pytest -v
```

### Tests muy lentos
```bash
# Omitir tests lentos
./run_tests.sh fast

# O con pytest directo
pytest -v -m "not slow"
```

## 📈 Próximos Pasos

1. Ejecutar todos los tests: `./run_tests.sh`
2. Ver qué pasa y qué falla
3. Corregir código si es necesario
4. Re-ejecutar hasta que todo pase ✅

---

**¿Problemas?** Ver [README.md](README.md) para documentación completa.
