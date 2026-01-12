#!/usr/bin/env python3
"""
🔙 BACKTESTING SYSTEM - Sistema Completo de Backtesting
=======================================================

Sistema profesional de backtesting que replica EXACTAMENTE el comportamiento
del sistema de trading en producción.

Características:
- ✅ Comportamiento IDÉNTICO al sistema real
- ✅ Reutiliza clases reales: Scanner, PositionCalculator, ExitManager
- ✅ Validación exhaustiva de datos históricos
- ✅ Análisis detallado por símbolo e indicadores
- ✅ Reportes completos y visualizaciones
- ✅ Time-forward testing (sin look-ahead bias)
- ✅ Gestión realista de capital y posiciones

Módulos:
- config: Configuración del backtesting
- data_validator: Validación de calidad de datos
- signal_replicator: Wrapper del scanner real
- position_replicator: Wrapper del position calculator real
- exit_replicator: Wrapper del exit manager real
- trade_manager: Gestión de trades y posiciones
- backtest_engine: Motor principal de backtesting
- performance_analyzer: Análisis de rendimiento
- indicator_analyzer: Análisis de indicadores
- report_generator: Generación de reportes
- visualization: Gráficos y visualizaciones
- run_backtest: Script principal

Autor: Claude Code
Versión: 1.0
"""

__version__ = "1.0.0"
__author__ = "Claude Code"

# Imports principales para facilitar el uso
from .config import BacktestConfig
from .backtest_engine import BacktestEngine
from .data_validator import DataValidator, ValidationReport
from .performance_analyzer import PerformanceAnalyzer
from .indicator_analyzer import IndicatorAnalyzer
from .report_generator import ReportGenerator

__all__ = [
    'BacktestConfig',
    'BacktestEngine',
    'DataValidator',
    'ValidationReport',
    'PerformanceAnalyzer',
    'IndicatorAnalyzer',
    'ReportGenerator',
]
