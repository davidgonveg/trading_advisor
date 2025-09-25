"""
🎯 Position Management System - Gestión Avanzada de Posiciones
============================================================

Sistema de tracking granular de posiciones con entradas escalonadas
"""

# Importar los componentes principales para fácil acceso
from .states import PositionStatus, EntryStatus, ExitStatus, ExecutionType, SignalDirection
from .data_models import EnhancedPosition, ExecutionLevel, PositionSummary, StateTransition

__version__ = "1.0.0"
__author__ = "Trading System V3.0"

# Versión del sistema de estados
POSITION_SYSTEM_VERSION = "3.0"