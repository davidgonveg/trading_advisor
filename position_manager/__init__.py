#!/usr/bin/env python3
"""
📦 POSITION MANAGER V4.0 - PACKAGE INITIALIZATION
=================================================

Sistema completo de gestión de posiciones para trading automatizado.

Exports principales:
- Models: TrackedPosition, ExecutionEvent, ExecutionStatus, etc.
- PositionTracker: Tracking de estado de posiciones
- ExecutionMonitor: Detección de ejecuciones en tiempo real
- SignalCoordinator: Coordinación inteligente de señales

Uso básico:
    from position_manager import PositionTracker, ExecutionMonitor, SignalCoordinator
    
    tracker = PositionTracker()
    monitor = ExecutionMonitor(tracker)
    coordinator = SignalCoordinator(tracker, monitor)
"""

__version__ = "4.0.0"
__author__ = "Trading System Team"

# =============================================================================
# 📊 MODELS
# =============================================================================

from .models import (
    # Enums
    ExecutionStatus,
    PositionStatus,
    ExecutionEventType,
    
    # Level Status Classes
    EntryLevelStatus,
    ExitLevelStatus,
    StopLevelStatus,
    
    # Main Classes
    TrackedPosition,
    ExecutionEvent,
    
    # Helper Functions
    create_entry_levels_from_plan,
    create_exit_levels_from_plan,
    create_stop_level_from_plan
)

# =============================================================================
# 🔧 CORE MODULES
# =============================================================================

from .position_tracker import PositionTracker
from .execution_monitor import ExecutionMonitor
from .signal_coordinator import SignalCoordinator

# =============================================================================
# 📋 EXPORTS
# =============================================================================

__all__ = [
    # Version
    '__version__',
    
    # Enums
    'ExecutionStatus',
    'PositionStatus',
    'ExecutionEventType',
    
    # Level Classes
    'EntryLevelStatus',
    'ExitLevelStatus',
    'StopLevelStatus',
    
    # Main Classes
    'TrackedPosition',
    'ExecutionEvent',
    
    # Core Modules
    'PositionTracker',
    'ExecutionMonitor',
    'SignalCoordinator',
    
    # Helper Functions
    'create_entry_levels_from_plan',
    'create_exit_levels_from_plan',
    'create_stop_level_from_plan',
]

# =============================================================================
# 🎯 QUICK START HELPERS
# =============================================================================

def create_position_manager_system(
    use_database: bool = True,
    use_real_prices: bool = True,
    tolerance_pct: float = 0.1,
    min_update_interval_minutes: int = 30
):
    """
    Helper para crear el sistema completo integrado
    
    Args:
        use_database: Si usar persistencia en DB
        use_real_prices: Si usar precios reales de yfinance
        tolerance_pct: Tolerancia para detección de ejecuciones
        min_update_interval_minutes: Intervalo mínimo entre updates
        
    Returns:
        Tuple (tracker, monitor, coordinator)
    
    Example:
        >>> tracker, monitor, coordinator = create_position_manager_system()
        >>> # Sistema listo para usar
    """
    tracker = PositionTracker(use_database=use_database)
    monitor = ExecutionMonitor(
        tracker,
        tolerance_pct=tolerance_pct,
        use_real_prices=use_real_prices
    )
    coordinator = SignalCoordinator(
        tracker,
        monitor,
        min_update_interval_minutes=min_update_interval_minutes
    )
    
    return tracker, monitor, coordinator


def get_version_info():
    """Obtener información de versión del sistema"""
    return {
        'version': __version__,
        'components': {
            'models': 'OK',
            'position_tracker': 'OK',
            'execution_monitor': 'OK',
            'signal_coordinator': 'OK'
        },
        'status': 'READY'
    }


# =============================================================================
# 📝 NOTA
# =============================================================================
# Para probar el package, ejecuta desde la raíz del proyecto:
#   python test_position_manager.py