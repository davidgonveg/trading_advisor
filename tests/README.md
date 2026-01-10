# 🧪 Guía de Pruebas - Trading Advisor

Este directorio contiene la suite de pruebas automatizadas para validar el correcto funcionamiento del sistema.

## 🚀 Cómo ejecutar los tests

Asegúrate de estar en la carpeta raíz del proyecto (`trading advisor`).

### 1. Ejecutar todos los tests (Recomendado)
El comando básico correrá todas las pruebas disponibles:
```bash
pytest
```

### 2. Ejecutar con detalle y logs
Para ver los mensajes de éxito y los logs de lo que está pasando:
```bash
pytest -v -s
```
* `-v`: Verbose (muestra cada test individualmente)
* `-s`: Show output (muestra los prints y logs del código)

### 3. Ejecutar un módulo específico
Si solo quieres probar una parte del sistema:

**Scanner de Señales:**
```bash
pytest tests/test_scanner.py
```

**Gestor de Posiciones:**
```bash
pytest tests/test_position_mgmt.py
```

**Calculadora de Riesgo:**
```bash
pytest tests/test_calculator.py
```

**Telegram Bot:**
```bash
pytest tests/test_telegram.py
```

**Base de Datos:**
```bash
pytest tests/test_database.py
```

## 📊 Interpretación de Resultados

* **PUNTOS VERDES (`.`) o `PASSED`**: El test pasó correctamente.
* **LETRAS ROJAS (`F`) o `FAILED`**: Algo falló. Mira el reporte de error para ver qué pasó.
* **LETRAS AMARILLAS (`s`) o `SKIPPED`**: El test se saltó (intencionalmente).

## ⚠️ Notas Importantes
* **Entorno Simulado**: La mayoría de los tests usan "mocks" (simulaciones) para `yfinance` y `Telegram`, por lo que **no necesitan internet** ni envían mensajes reales.
* **Infrastructure**: Los tests de `test_infrastructure.py` pueden fallar si no están configurados todos los módulos globales. Esto es esperado por ahora.
