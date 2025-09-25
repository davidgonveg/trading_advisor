#!/usr/bin/env python3
"""
🔄 POSITION STATE MACHINE - Máquina de Estados para Posiciones
=============================================================

Implementa la lógica de transiciones entre estados, validaciones y
automatización de cambios de estado basados en condiciones.

Garantiza que las transiciones sean válidas y mantiene la consistencia
del sistema de tracking de posiciones.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Set, Any, Callable
from dataclasses import dataclass
from enum import Enum

# Manejo de imports para testing standalone y uso en módulo
try:
    from .states import PositionStatus, PositionStateConfig, EntryStatus, ExitStatus
    from .data_models import EnhancedPosition, ExecutionLevel, StateTransition
except ImportError:
    from states import PositionStatus, PositionStateConfig, EntryStatus, ExitStatus  
    from data_models import EnhancedPosition, ExecutionLevel, StateTransition

logger = logging.getLogger(__name__)


class TransitionResult(Enum):
    """Resultado de una transición de estado"""
    SUCCESS = "SUCCESS"
    INVALID_TRANSITION = "INVALID_TRANSITION"
    FAILED_VALIDATION = "FAILED_VALIDATION"
    MISSING_CONDITIONS = "MISSING_CONDITIONS"
    ERROR = "ERROR"


class StateTransitionError(Exception):
    """Error específico para transiciones de estado inválidas"""
    
    def __init__(self, message: str, from_state: PositionStatus = None, to_state: PositionStatus = None, position_symbol: str = None):
        self.from_state = from_state
        self.to_state = to_state
        self.position_symbol = position_symbol
        
        detailed_message = f"StateTransitionError: {message}"
        if from_state and to_state:
            detailed_message += f" ({from_state.value} → {to_state.value})"
        if position_symbol:
            detailed_message += f" for {position_symbol}"
            
        super().__init__(detailed_message)


@dataclass
class TransitionContext:
    """Contexto para una transición de estado"""
    trigger: str                        # Qué causó la transición
    metadata: Dict[str, Any] = None     # Datos adicionales
    validation_data: Dict[str, Any] = None  # Datos para validación
    force: bool = False                 # Forzar transición (skip validations)
    notes: str = ""                     # Notas adicionales
    
    def __post_init__(self):
        """Post-inicialización para valores por defecto"""
        if self.metadata is None:
            self.metadata = {}
        if self.validation_data is None:
            self.validation_data = {}


class PositionStateMachine:
    """
    Máquina de estados para gestión de posiciones
    
    Maneja:
    - Validación de transiciones
    - Automatización de cambios de estado
    - Detección de inconsistencias
    - Timeouts y limpieza automática
    """
    
    def __init__(self, enable_auto_transitions: bool = True, enable_timeouts: bool = True):
        """
        Inicializar la máquina de estados
        
        Args:
            enable_auto_transitions: Habilitar transiciones automáticas
            enable_timeouts: Habilitar timeouts de estado
        """
        self.enable_auto_transitions = enable_auto_transitions
        self.enable_timeouts = enable_timeouts
        
        # Callbacks para eventos
        self.transition_callbacks: Dict[PositionStatus, List[Callable]] = {}
        self.validation_callbacks: Dict[str, Callable] = {}
        
        # Estadísticas
        self.transition_count = 0
        self.failed_transitions = 0
        self.auto_transitions = 0
        
        logger.info("🔄 PositionStateMachine inicializada")
    
    def can_transition(self, 
                      position: EnhancedPosition, 
                      to_state: PositionStatus) -> Tuple[bool, str]:
        """
        Verificar si una transición es posible
        
        Returns:
            Tuple[bool, str]: (Es posible, Razón si no es posible)
        """
        current_state = position.status
        
        # 1. Verificar transición válida según configuración
        if not PositionStateConfig.is_valid_transition(current_state, to_state):
            return False, f"Transición inválida: {current_state.value} -> {to_state.value}"
        
        # 2. Verificaciones específicas por estado
        validation_result = self._validate_state_conditions(position, to_state)
        if not validation_result[0]:
            return False, validation_result[1]
        
        # 3. Verificar timeouts si está habilitado
        if self.enable_timeouts:
            timeout_result = self._check_state_timeout(position)
            if not timeout_result[0]:
                return False, timeout_result[1]
        
        return True, "Transición válida"
    
    def transition_to(self, 
                     position: EnhancedPosition, 
                     to_state: PositionStatus,
                     context: TransitionContext) -> TransitionResult:
        """
        Ejecutar transición de estado
        
        Args:
            position: Posición a transicionar
            to_state: Estado destino
            context: Contexto de la transición
            
        Returns:
            TransitionResult: Resultado de la transición
        """
        try:
            current_state = position.status
            
            # 1. Validar transición (a menos que sea forzada)
            if not context.force:
                can_transition, reason = self.can_transition(position, to_state)
                if not can_transition:
                    logger.warning(f"❌ {position.symbol}: Transición rechazada - {reason}")
                    self.failed_transitions += 1
                    return TransitionResult.INVALID_TRANSITION
            
            # 2. Ejecutar pre-transición callbacks
            self._execute_pre_transition_callbacks(position, current_state, to_state)
            
            # 3. Ejecutar la transición
            position.add_state_transition(
                to_state=to_state,
                trigger=context.trigger,
                notes=context.notes
            )
            
            # 4. Ejecutar acciones post-transición
            self._execute_post_transition_actions(position, current_state, to_state, context)
            
            # 5. Ejecutar callbacks de estado destino
            self._execute_post_transition_callbacks(position, current_state, to_state)
            
            # 6. Verificar si hay auto-transiciones disponibles
            if self.enable_auto_transitions:
                self._check_auto_transitions(position)
            
            self.transition_count += 1
            
            logger.info(f"✅ {position.symbol}: {current_state.value} -> {to_state.value} ({context.trigger})")
            
            return TransitionResult.SUCCESS
            
        except Exception as e:
            logger.error(f"❌ Error en transición {position.symbol}: {e}")
            return TransitionResult.ERROR
    
    def auto_evaluate_state(self, position: EnhancedPosition) -> Optional[PositionStatus]:
        """
        Evaluar automáticamente el estado correcto basado en la posición actual
        
        Returns:
            PositionStatus: Estado recomendado, o None si el actual es correcto
        """
        try:
            current_state = position.status
            
            # 1. Evaluar basado en ejecuciones
            executed_entries = position.get_executed_entries()
            pending_entries = position.get_pending_entries()
            executed_exits = position.get_executed_exits()
            
            # 2. Lógica de evaluación automática
            
            # Si no hay entradas ejecutadas pero hay señal -> ENTRY_PENDING
            if len(executed_entries) == 0 and len(pending_entries) > 0:
                if current_state != PositionStatus.ENTRY_PENDING:
                    return PositionStatus.ENTRY_PENDING
            
            # Si hay entradas ejecutadas pero faltan más -> PARTIALLY_FILLED
            elif len(executed_entries) > 0 and len(pending_entries) > 0:
                if current_state != PositionStatus.PARTIALLY_FILLED:
                    return PositionStatus.PARTIALLY_FILLED
            
            # Si todas las entradas están ejecutadas -> FULLY_ENTERED
            elif len(executed_entries) > 0 and len(pending_entries) == 0:
                if current_state != PositionStatus.FULLY_ENTERED:
                    return PositionStatus.FULLY_ENTERED
            
            # Si hay salidas ejecutadas -> PARTIALLY_EXITED o CLOSED
            elif len(executed_exits) > 0:
                if position.summary.total_shares <= 0:
                    if current_state != PositionStatus.CLOSED:
                        return PositionStatus.CLOSED
                else:
                    if current_state != PositionStatus.PARTIALLY_EXITED:
                        return PositionStatus.PARTIALLY_EXITED
            
            return None  # Estado actual es correcto
            
        except Exception as e:
            logger.error(f"❌ Error evaluando estado automático {position.symbol}: {e}")
            return None
    
    def _validate_state_conditions(self, 
                                  position: EnhancedPosition, 
                                  to_state: PositionStatus) -> Tuple[bool, str]:
        """Validar condiciones específicas para transición"""
        
        # Validaciones específicas por estado destino
        if to_state == PositionStatus.PARTIALLY_FILLED:
            executed_entries = position.get_executed_entries()
            if len(executed_entries) == 0:
                return False, "No hay entradas ejecutadas para PARTIALLY_FILLED"
        
        elif to_state == PositionStatus.FULLY_ENTERED:
            pending_entries = position.get_pending_entries()
            executed_entries = position.get_executed_entries()
            if len(pending_entries) > 0:
                return False, "Hay entradas pendientes, no puede ser FULLY_ENTERED"
            if len(executed_entries) == 0:
                return False, "No hay entradas ejecutadas para FULLY_ENTERED"
        
        elif to_state == PositionStatus.CLOSED:
            if position.summary.total_shares > 0:
                return False, "Posición aún tiene shares, no puede cerrarse"
        
        return True, "Condiciones válidas"
    
    def _check_state_timeout(self, position: EnhancedPosition) -> Tuple[bool, str]:
        """Verificar timeouts de estado"""
        current_state = position.status
        timeout_minutes = PositionStateConfig.get_state_timeout(current_state)
        
        if timeout_minutes <= 0:
            return True, "Sin timeout"
        
        # Calcular tiempo en estado actual
        if position.state_history:
            last_transition = position.state_history[-1]
            time_in_state = datetime.now() - last_transition.timestamp
            time_in_state_minutes = time_in_state.total_seconds() / 60
            
            if time_in_state_minutes > timeout_minutes:
                return False, f"Timeout de estado: {time_in_state_minutes:.1f}min > {timeout_minutes}min"
        
        return True, "Sin timeout"
    
    def _execute_pre_transition_callbacks(self, 
                                        position: EnhancedPosition,
                                        from_state: PositionStatus, 
                                        to_state: PositionStatus):
        """Ejecutar callbacks pre-transición"""
        # Implementar según necesidad específica
        pass
    
    def _execute_post_transition_actions(self, 
                                       position: EnhancedPosition,
                                       from_state: PositionStatus,
                                       to_state: PositionStatus,
                                       context: TransitionContext):
        """Ejecutar acciones automáticas post-transición"""
        
        # Actualizar resumen cuando cambia a estados con ejecuciones
        if to_state in [PositionStatus.PARTIALLY_FILLED, PositionStatus.FULLY_ENTERED]:
            position.update_summary()
        
        # Cancelar entradas pendientes si se cierra la posición
        if to_state in [PositionStatus.CLOSED, PositionStatus.STOPPED_OUT]:
            self._cancel_pending_entries(position)
        
        # Incrementar alertas si es necesario
        if PositionStateConfig.requires_immediate_alert(to_state):
            position.alerts_sent += 1
    
    def _execute_post_transition_callbacks(self, 
                                         position: EnhancedPosition,
                                         from_state: PositionStatus,
                                         to_state: PositionStatus):
        """Ejecutar callbacks post-transición"""
        callbacks = self.transition_callbacks.get(to_state, [])
        for callback in callbacks:
            try:
                callback(position, from_state, to_state)
            except Exception as e:
                logger.error(f"❌ Error en callback {position.symbol}: {e}")
    
    def _check_auto_transitions(self, position: EnhancedPosition):
        """Verificar y ejecutar transiciones automáticas"""
        recommended_state = self.auto_evaluate_state(position)
        
        if recommended_state and recommended_state != position.status:
            logger.info(f"🤖 {position.symbol}: Auto-transición detectada -> {recommended_state.value}")
            
            context = TransitionContext(
                trigger="auto_evaluation",
                metadata={"auto_transition": True},
                validation_data={}
            )
            
            result = self.transition_to(position, recommended_state, context)
            if result == TransitionResult.SUCCESS:
                self.auto_transitions += 1
    
    def _cancel_pending_entries(self, position: EnhancedPosition):
        """Cancelar entradas pendientes"""
        for entry in position.entries:
            if entry.is_pending():
                entry.status = EntryStatus.CANCELLED
                entry.cancelled_at = datetime.now()
    
    def register_callback(self, state: PositionStatus, callback: Callable):
        """Registrar callback para estado específico"""
        if state not in self.transition_callbacks:
            self.transition_callbacks[state] = []
        self.transition_callbacks[state].append(callback)
    
    def get_statistics(self) -> Dict[str, Any]:
        """Obtener estadísticas de la máquina de estados"""
        return {
            'total_transitions': self.transition_count,
            'failed_transitions': self.failed_transitions,
            'auto_transitions': self.auto_transitions,
            'success_rate': (self.transition_count / max(1, self.transition_count + self.failed_transitions)) * 100,
            'auto_transition_rate': (self.auto_transitions / max(1, self.transition_count)) * 100
        }


# Factory functions para crear contextos comunes
def create_entry_filled_context(level: int, executed_price: float) -> TransitionContext:
    """Crear contexto para entrada ejecutada"""
    return TransitionContext(
        trigger=f"entry_level_{level}_filled",
        metadata={"level": level, "executed_price": executed_price},
        validation_data={},
        notes=f"Entrada nivel {level} ejecutada a ${executed_price:.2f}"
    )

def create_exit_signal_context(reason: str) -> TransitionContext:
    """Crear contexto para señal de salida"""
    return TransitionContext(
        trigger="exit_signal_generated", 
        metadata={"exit_reason": reason},
        validation_data={},
        notes=f"Señal de salida generada: {reason}"
    )

def create_timeout_context(state: PositionStatus) -> TransitionContext:
    """Crear contexto para timeout"""
    return TransitionContext(
        trigger="state_timeout",
        metadata={"timed_out_state": state.value},
        validation_data={},
        notes=f"Timeout del estado {state.value}"
    )


if __name__ == "__main__":
    # Demo básico
    print("🔄 POSITION STATE MACHINE - Demo")
    print("=" * 50)
    
    # Importar para demo
    from data_models import EnhancedPosition, ExecutionLevel, create_execution_level
    from states import SignalDirection, ExecutionType, EntryStatus
    
    # Crear máquina de estados
    state_machine = PositionStateMachine()
    
    # Crear posición de prueba
    position = EnhancedPosition(
        symbol="MSFT",
        direction=SignalDirection.LONG,
        signal_strength=90
    )
    
    # Agregar niveles de entrada
    entry1 = create_execution_level(1, ExecutionType.ENTRY, 400.0, 50, 50.0)
    entry2 = create_execution_level(2, ExecutionType.ENTRY, 399.0, 50, 50.0) 
    position.entries = [entry1, entry2]
    
    print(f"✅ Posición inicial: {position.status.value}")
    
    # Test 1: Transición a ENTRY_PENDING
    context1 = TransitionContext(trigger="signal_generated")
    result1 = state_machine.transition_to(position, PositionStatus.ENTRY_PENDING, context1)
    print(f"📊 Transición 1: {result1.value} -> {position.status.value}")
    
    # Test 2: Simular ejecución parcial
    entry1.status = EntryStatus.FILLED
    entry1.executed_price = 400.05
    position.update_summary()
    
    context2 = create_entry_filled_context(1, 400.05)
    result2 = state_machine.transition_to(position, PositionStatus.PARTIALLY_FILLED, context2)
    print(f"📊 Transición 2: {result2.value} -> {position.status.value}")
    
    # Test 3: Auto-evaluación
    recommended = state_machine.auto_evaluate_state(position)
    print(f"🤖 Estado recomendado: {recommended.value if recommended else 'Correcto actual'}")
    
    # Estadísticas
    stats = state_machine.get_statistics()
    print(f"\n📈 Estadísticas:")
    print(f"  Total transiciones: {stats['total_transitions']}")
    print(f"  Tasa éxito: {stats['success_rate']:.1f}%")
    print(f"  Auto-transiciones: {stats['auto_transitions']}")