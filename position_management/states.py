#!/usr/bin/env python3
"""
🎯 POSITION STATES - Sistema de Estados para Gestión de Posiciones
================================================================

Define todos los estados, enums y constantes para el sistema de tracking
de posiciones con entradas escalonadas.

Estados del ciclo de vida completo:
SIGNAL_GENERATED → PARTIALLY_FILLED → FULLY_ENTERED → EXITING → CLOSED
"""

from enum import Enum, auto
from typing import Dict, List, Set, Tuple
from dataclasses import dataclass

class PositionStatus(Enum):
    """Estados principales del ciclo de vida de una posición"""
    
    # Estado inicial - señal generada pero sin ejecuciones
    SIGNAL_GENERATED = "SIGNAL_GENERATED"
    
    # Estados de entrada
    ENTRY_PENDING = "ENTRY_PENDING"           # Esperando primera entrada
    PARTIALLY_FILLED = "PARTIALLY_FILLED"     # Algunas entradas ejecutadas
    FULLY_ENTERED = "FULLY_ENTERED"           # Todas las entradas completadas
    
    # Estados de salida
    EXITING = "EXITING"                       # En proceso de salidas escalonadas  
    PARTIALLY_EXITED = "PARTIALLY_EXITED"     # Algunas salidas ejecutadas
    
    # Estados finales
    CLOSED = "CLOSED"                         # Posición cerrada completamente
    STOPPED_OUT = "STOPPED_OUT"               # Cerrada por stop loss
    CANCELLED = "CANCELLED"                   # Señal cancelada sin entradas
    
    # Estados de error
    ERROR = "ERROR"                           # Error en el sistema
    INCONSISTENT = "INCONSISTENT"             # Estado inconsistente detectado


class EntryStatus(Enum):
    """Estados específicos de niveles de entrada"""
    PENDING = "PENDING"           # Esperando ejecución
    FILLED = "FILLED"             # Ejecutado completamente
    PARTIALLY_FILLED = "PARTIALLY_FILLED"  # Ejecutado parcialmente
    CANCELLED = "CANCELLED"       # Cancelado (timeout, condiciones cambiaron)
    EXPIRED = "EXPIRED"           # Expirado por tiempo


class ExitStatus(Enum):
    """Estados específicos de niveles de salida"""
    PENDING = "PENDING"           # Esperando ejecución
    FILLED = "FILLED"             # Ejecutado completamente
    PARTIALLY_FILLED = "PARTIALLY_FILLED"  # Ejecutado parcialmente
    CANCELLED = "CANCELLED"       # Cancelado
    TRIGGERED = "TRIGGERED"       # Activado pero no ejecutado aún


class ExecutionType(Enum):
    """Tipos de ejecución"""
    ENTRY = "ENTRY"               # Entrada escalonada
    EXIT = "EXIT"                 # Salida normal (take profit)
    STOP_LOSS = "STOP_LOSS"       # Stop loss
    TRAILING_STOP = "TRAILING_STOP"  # Trailing stop
    EMERGENCY_EXIT = "EMERGENCY_EXIT"  # Salida de emergencia


class SignalDirection(Enum):
    """Dirección de la señal"""
    LONG = "LONG"
    SHORT = "SHORT"


class AlertPriority(Enum):
    """Prioridad de alertas"""
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    URGENT = 4
    CRITICAL = 5


@dataclass(frozen=True)
class StateTransitionRule:
    """Regla de transición entre estados"""
    from_state: PositionStatus
    to_state: PositionStatus
    required_conditions: List[str]
    optional_conditions: List[str] = None


class PositionStateConfig:
    """Configuración y reglas del sistema de estados"""
    
    # Transiciones válidas entre estados
    VALID_TRANSITIONS: Dict[PositionStatus, Set[PositionStatus]] = {
        
        PositionStatus.SIGNAL_GENERATED: {
            PositionStatus.ENTRY_PENDING,
            PositionStatus.PARTIALLY_FILLED,  # Entrada inmediata
            PositionStatus.CANCELLED,
            PositionStatus.ERROR
        },
        
        PositionStatus.ENTRY_PENDING: {
            PositionStatus.PARTIALLY_FILLED,
            PositionStatus.FULLY_ENTERED,     # Si solo hay 1 entrada
            PositionStatus.CANCELLED,
            PositionStatus.ERROR
        },
        
        PositionStatus.PARTIALLY_FILLED: {
            PositionStatus.FULLY_ENTERED,     # Completar entradas
            PositionStatus.EXITING,           # Exit antes de completar
            PositionStatus.STOPPED_OUT,       # Stop loss
            PositionStatus.CANCELLED,         # Cancelar entradas restantes
            PositionStatus.ERROR
        },
        
        PositionStatus.FULLY_ENTERED: {
            PositionStatus.EXITING,
            PositionStatus.PARTIALLY_EXITED,
            PositionStatus.STOPPED_OUT,
            PositionStatus.CLOSED,            # Exit completo inmediato
            PositionStatus.ERROR
        },
        
        PositionStatus.EXITING: {
            PositionStatus.PARTIALLY_EXITED,
            PositionStatus.CLOSED,
            PositionStatus.STOPPED_OUT,
            PositionStatus.ERROR
        },
        
        PositionStatus.PARTIALLY_EXITED: {
            PositionStatus.CLOSED,
            PositionStatus.STOPPED_OUT,
            PositionStatus.ERROR
        },
        
        # Estados finales - solo pueden ir a ERROR para correcciones
        PositionStatus.CLOSED: {PositionStatus.ERROR},
        PositionStatus.STOPPED_OUT: {PositionStatus.ERROR},
        PositionStatus.CANCELLED: {PositionStatus.ERROR},
        
        # ERROR puede ir a cualquier estado (para correcciones)
        PositionStatus.ERROR: set(PositionStatus),
        PositionStatus.INCONSISTENT: set(PositionStatus)
    }
    
    # Estados que requieren tracking activo
    ACTIVE_TRACKING_STATES = {
        PositionStatus.ENTRY_PENDING,
        PositionStatus.PARTIALLY_FILLED,
        PositionStatus.FULLY_ENTERED,
        PositionStatus.EXITING,
        PositionStatus.PARTIALLY_EXITED
    }
    
    # Estados que requieren monitoreo del exit manager
    EXIT_MONITORING_STATES = {
        PositionStatus.PARTIALLY_FILLED,
        PositionStatus.FULLY_ENTERED,
        PositionStatus.EXITING,
        PositionStatus.PARTIALLY_EXITED
    }
    
    # Estados finales (no requieren más procesamiento)
    FINAL_STATES = {
        PositionStatus.CLOSED,
        PositionStatus.STOPPED_OUT,
        PositionStatus.CANCELLED
    }
    
    # Estados que requieren alertas inmediatas
    ALERT_STATES = {
        PositionStatus.STOPPED_OUT,
        PositionStatus.ERROR,
        PositionStatus.INCONSISTENT
    }
    
    # Timeouts por estado (en minutos)
    STATE_TIMEOUTS = {
        PositionStatus.ENTRY_PENDING: 30,      # 30 min max para primera entrada
        PositionStatus.PARTIALLY_FILLED: 120,  # 2 horas max para completar entradas
        PositionStatus.EXITING: 60,            # 1 hora max para exits
    }
    
    # Máximo número de niveles
    MAX_ENTRY_LEVELS = 4
    MAX_EXIT_LEVELS = 4
    
    @classmethod
    def is_valid_transition(cls, from_state: PositionStatus, to_state: PositionStatus) -> bool:
        """Verificar si una transición es válida"""
        return to_state in cls.VALID_TRANSITIONS.get(from_state, set())
    
    @classmethod
    def get_valid_next_states(cls, current_state: PositionStatus) -> Set[PositionStatus]:
        """Obtener estados válidos desde el estado actual"""
        return cls.VALID_TRANSITIONS.get(current_state, set())
    
    @classmethod
    def requires_active_tracking(cls, state: PositionStatus) -> bool:
        """Verificar si el estado requiere tracking activo"""
        return state in cls.ACTIVE_TRACKING_STATES
    
    @classmethod
    def requires_exit_monitoring(cls, state: PositionStatus) -> bool:
        """Verificar si el estado requiere monitoreo de exit"""
        return state in cls.EXIT_MONITORING_STATES
    
    @classmethod
    def is_final_state(cls, state: PositionStatus) -> bool:
        """Verificar si es un estado final"""
        return state in cls.FINAL_STATES
    
    @classmethod
    def requires_immediate_alert(cls, state: PositionStatus) -> bool:
        """Verificar si el estado requiere alerta inmediata"""
        return state in cls.ALERT_STATES
    
    @classmethod
    def get_state_timeout(cls, state: PositionStatus) -> int:
        """Obtener timeout en minutos para el estado"""
        return cls.STATE_TIMEOUTS.get(state, 0)


# Constantes de configuración
DEFAULT_CONFIG = {
    'ENABLE_STATE_TIMEOUTS': True,
    'ENABLE_AUTOMATIC_CANCELLATION': True,
    'ENABLE_INCONSISTENCY_DETECTION': True,
    'ALERT_ON_STATE_CHANGES': True,
    'LOG_ALL_TRANSITIONS': True,
    'VALIDATE_TRANSITIONS': True
}

# Mapeo de estados a colores para logging/UI
STATE_COLORS = {
    PositionStatus.SIGNAL_GENERATED: "🟡",
    PositionStatus.ENTRY_PENDING: "🟠", 
    PositionStatus.PARTIALLY_FILLED: "🔵",
    PositionStatus.FULLY_ENTERED: "🟢",
    PositionStatus.EXITING: "🟣",
    PositionStatus.PARTIALLY_EXITED: "🟣",
    PositionStatus.CLOSED: "⚪",
    PositionStatus.STOPPED_OUT: "🔴",
    PositionStatus.CANCELLED: "⚫",
    PositionStatus.ERROR: "❌",
    PositionStatus.INCONSISTENT: "⚠️"
}

def get_state_emoji(state: PositionStatus) -> str:
    """Obtener emoji para el estado"""
    return STATE_COLORS.get(state, "❓")


if __name__ == "__main__":
    # Demo de uso
    print("🎯 POSITION STATES - Sistema de Estados")
    print("=" * 50)
    
    print("\n📋 Estados disponibles:")
    for state in PositionStatus:
        emoji = get_state_emoji(state)
        timeout = PositionStateConfig.get_state_timeout(state)
        timeout_str = f" ({timeout}min)" if timeout > 0 else ""
        print(f"  {emoji} {state.value}{timeout_str}")
    
    print(f"\n🔄 Transiciones desde SIGNAL_GENERATED:")
    next_states = PositionStateConfig.get_valid_next_states(PositionStatus.SIGNAL_GENERATED)
    for state in next_states:
        emoji = get_state_emoji(state)
        print(f"  {emoji} {state.value}")
    
    print(f"\n✅ Estados que requieren tracking: {len(PositionStateConfig.ACTIVE_TRACKING_STATES)}")
    print(f"📊 Estados que requieren exit monitoring: {len(PositionStateConfig.EXIT_MONITORING_STATES)}")
    print(f"🏁 Estados finales: {len(PositionStateConfig.FINAL_STATES)}")