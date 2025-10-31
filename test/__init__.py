#!/usr/bin/env python3
"""
🧪 Trading Advisor Test Suite
==============================

Suite comprehensiva de tests para el sistema de trading automatizado.

Incluye tests para:
- Base de datos (estructura, integridad, gaps)
- Indicadores técnicos (RSI, MACD, VWAP, etc.)
- Gap filling (detección, clasificación, relleno)
- Position tracking (registro, actualización, métricas)
- Backtesting (validación, ejecución, métricas)
- Integración (flujo completo, escenarios realistas)

Para ejecutar:
    pytest -v
    pytest -v -m database
    pytest -v -m "not slow"

Ver README.md para más detalles.
"""

__version__ = "1.0.0"
__author__ = "Trading Advisor Team"
