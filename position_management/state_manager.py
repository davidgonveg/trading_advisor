#!/usr/bin/env python3
"""
🎯 STATE MANAGER - CONTROLADOR PRINCIPAL DE ESTADOS V3.0
======================================================

Controlador central que gestiona el ciclo de vida completo de posiciones.
Coordina transiciones de estados, persistencia y mantiene consistencia
entre modelos en memoria y base de datos.

🎯 RESPONSABILIDADES:
1. API unificada para gestión de estados de posición
2. Coordinación entre state_machine y base de datos  
3. Validación de transiciones y consistencia de datos
4. Notificaciones de cambios de estado a otros componentes
5. Gestión de excepciones y rollback automático

🔧 ARQUITECTURA:
- StateManager: Controlador principal 
- Transaction Context: Manejo de transacciones con rollback
- Event System: Notificaciones de cambios de estado
- Validation Layer: Validación de business rules

🎯 PATRONES IMPLEMENTADOS:
- Unit of Work: Agrupa cambios en transacciones
- Observer: Notifica cambios a componentes interesados  
- Command: Encapsula operaciones de estado
- Strategy: Diferentes estrategias de transición según contexto
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional, Callable, Any, Set
from dataclasses import dataclass
from enum import Enum
import json
from contextlib import contextmanager
import uuid
import pytz

# Importar position management components
from .states import PositionStatus, EntryStatus, ExitStatus, ExecutionType, SignalDirection
from .data_models import EnhancedPosition, ExecutionLevel, StateTransition, PositionSummary
from .state_machine import PositionStateMachine, StateTransitionError

# Importar database components
from database.connection import get_connection
from database.position_queries import PositionQueries

import config

logger = logging.getLogger(__name__)


class StateChangeEvent(Enum):
    """Tipos de eventos de cambio de estado"""
    POSITION_CREATED = "position_created"
    STATUS_CHANGED = "status_changed"
    EXECUTION_RECORDED = "execution_recorded"
    POSITION_UPDATED = "position_updated"
    POSITION_CLOSED = "position_closed"
    ERROR_OCCURRED = "error_occurred"


@dataclass
class StateChangeNotification:
    """Notificación de cambio de estado"""
    event_type: StateChangeEvent
    position_id: str
    old_status: Optional[PositionStatus]
    new_status: Optional[PositionStatus]
    timestamp: datetime
    details: Dict[str, Any]
    metadata: Optional[Dict[str, Any]] = None


class ValidationError(Exception):
    """Error de validación de business rules"""
    pass


class StateManagerError(Exception):
    """Error general del state manager"""
    pass


class StateManager:
    """
    Controlador principal para gestión de estados de posición
    """
    
    def __init__(self):
        """Inicializar el State Manager"""
        self.state_machine = PositionStateMachine()
        self.position_queries = PositionQueries()
        
        # Sistema de observadores para notificaciones
        self._observers: Dict[StateChangeEvent, List[Callable]] = {}
        
        # Cache en memoria para optimización
        self._position_cache: Dict[str, EnhancedPosition] = {}
        self._cache_enabled = getattr(config, 'ENABLE_POSITION_CACHE', True)
        
        # Estadísticas
        self._stats = {
            'positions_created': 0,
            'transitions_executed': 0,
            'validations_failed': 0,
            'cache_hits': 0,
            'cache_misses': 0
        }
        
        logger.info("✅ State Manager inicializado")
    
    # ==============================================
    # GESTIÓN DE POSICIONES - API PRINCIPAL
    # ==============================================
    
    def create_position(self, symbol: str, direction: SignalDirection, 
                       entry_levels: List[ExecutionLevel], 
                       exit_levels: List[ExecutionLevel],
                       metadata: Optional[Dict[str, Any]] = None) -> EnhancedPosition:
        """
        Crear nueva posición con validaciones completas
        
        Args:
            symbol: Símbolo del activo
            direction: Dirección LONG/SHORT
            entry_levels: Niveles de entrada planificados
            exit_levels: Niveles de salida planificados
            metadata: Información adicional
            
        Returns:
            EnhancedPosition creada y persistida
            
        Raises:
            ValidationError: Si los datos no son válidos
            StateManagerError: Si hay error en la creación
        """
        logger.info(f"🎯 Creando nueva posición: {symbol} {direction.value}")
        
        try:
            with self._transaction_context() as ctx:
                # STEP 1: Validar que no hay posición activa
                existing_position = self.get_active_position(symbol)
                if existing_position:
                    raise ValidationError(f"Ya existe posición activa para {symbol}: {existing_position.position_id}")
                
                # STEP 2: Validar datos de entrada
                self._validate_position_data(symbol, direction, entry_levels, exit_levels)
                
                # STEP 3: Crear modelo de posición
                position_id = str(uuid.uuid4())
                position = EnhancedPosition(
                    position_id=position_id,
                    symbol=symbol,
                    direction=direction,
                    status=PositionStatus.PENDING,
                    entry_levels=entry_levels,
                    exit_levels=exit_levels,
                    created_at=datetime.now(pytz.UTC),
                    metadata=metadata or {}
                )
                
                # STEP 4: Validar con state machine
                if not self.state_machine.is_valid_initial_state(position.status):
                    raise ValidationError(f"Estado inicial inválido: {position.status}")
                
                # STEP 5: Persistir en base de datos
                self.position_queries.create_position(position)
                
                # STEP 6: Actualizar cache
                if self._cache_enabled:
                    self._position_cache[position_id] = position
                
                # STEP 7: Notificar creación
                self._notify_observers(StateChangeNotification(
                    event_type=StateChangeEvent.POSITION_CREATED,
                    position_id=position_id,
                    old_status=None,
                    new_status=position.status,
                    timestamp=datetime.now(pytz.UTC),
                    details={
                        'symbol': symbol,
                        'direction': direction.value,
                        'entry_levels_count': len(entry_levels),
                        'exit_levels_count': len(exit_levels)
                    }
                ))
                
                self._stats['positions_created'] += 1
                logger.info(f"✅ Posición creada exitosamente: {position_id}")
                return position
                
        except Exception as e:
            logger.error(f"❌ Error creando posición {symbol}: {e}")
            raise StateManagerError(f"Error creando posición: {e}")
        
    def register_position(self, position: EnhancedPosition) -> bool:
        """Registrar nueva posición"""
        try:
            if not position or not position.position_id:
                return False
            
            self._active_positions[position.position_id] = position
            
            # Persistir si hay BD
            if self.position_queries:
                self.position_queries.save_position(position)
            
            self._stats['positions_created'] += 1
            return True
        except Exception as e:
            logger.error(f"Error registrando posición: {e}")
            return False

    def get_position(self, position_id: str) -> Optional[EnhancedPosition]:
        """Obtener posición por ID"""
        if position_id in self._active_positions:
            return self._active_positions[position_id]
        return None
    
    def update_position_status(self, position_id: str, new_status: PositionStatus,
                              reason: str = "", metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        Actualizar estado de posición con validaciones
        
        Args:
            position_id: ID de la posición
            new_status: Nuevo estado
            reason: Razón del cambio
            metadata: Información adicional
            
        Returns:
            True si el cambio fue exitoso
            
        Raises:
            ValidationError: Si la transición no es válida
            StateManagerError: Si hay error en la actualización
        """
        logger.info(f"🔄 Actualizando posición {position_id} a estado {new_status.value}")
        
        try:
            with self._transaction_context() as ctx:
                # STEP 1: Obtener posición actual
                position = self.get_position(position_id)
                if not position:
                    raise StateManagerError(f"Posición no encontrada: {position_id}")
                
                old_status = position.status
                
                # STEP 2: Validar transición con state machine
                if not self.state_machine.can_transition(old_status, new_status):
                    raise ValidationError(
                        f"Transición inválida: {old_status.value} → {new_status.value}"
                    )
                
                # STEP 3: Actualizar modelo
                position.status = new_status
                position.updated_at = datetime.now(pytz.UTC)
                
                if metadata:
                    position.metadata.update(metadata)
                
                # STEP 4: Registrar transición
                transition = StateTransition(
                    position_id=position_id,
                    from_status=old_status,
                    to_status=new_status,
                    timestamp=datetime.now(pytz.UTC),
                    reason=reason,
                    metadata=metadata
                )
                position.state_history.append(transition)
                
                # STEP 5: Ejecutar lógica específica del estado
                self._execute_state_specific_logic(position, old_status, new_status)
                
                # STEP 6: Persistir cambios
                self.position_queries.update_position(position)
                
                # STEP 7: Actualizar cache
                if self._cache_enabled:
                    self._position_cache[position_id] = position
                
                # STEP 8: Notificar cambio
                self._notify_observers(StateChangeNotification(
                    event_type=StateChangeEvent.STATUS_CHANGED,
                    position_id=position_id,
                    old_status=old_status,
                    new_status=new_status,
                    timestamp=datetime.now(pytz.UTC),
                    details={
                        'reason': reason,
                        'symbol': position.symbol,
                        'direction': position.direction.value
                    },
                    metadata=metadata
                ))
                
                self._stats['transitions_executed'] += 1
                logger.info(f"✅ Estado actualizado: {position_id} {old_status.value} → {new_status.value}")
                return True
                
        except Exception as e:
            self._stats['validations_failed'] += 1
            logger.error(f"❌ Error actualizando estado {position_id}: {e}")
            raise StateManagerError(f"Error actualizando estado: {e}")
    
    def record_execution(self, position_id: str, level_id: str, 
                        executed_price: float, executed_quantity: float,
                        execution_time: Optional[datetime] = None,
                        execution_type: ExecutionType = ExecutionType.MARKET) -> bool:
        """
        Registrar ejecución de un nivel específico
        
        Args:
            position_id: ID de la posición
            level_id: ID del nivel ejecutado
            executed_price: Precio de ejecución
            executed_quantity: Cantidad ejecutada
            execution_time: Tiempo de ejecución
            execution_type: Tipo de ejecución
            
        Returns:
            True si la ejecución fue registrada exitosamente
        """
        logger.info(f"💰 Registrando ejecución: {position_id} nivel {level_id}")
        
        try:
            with self._transaction_context() as ctx:
                # STEP 1: Obtener posición
                position = self.get_position(position_id)
                if not position:
                    raise StateManagerError(f"Posición no encontrada: {position_id}")
                
                # STEP 2: Encontrar y actualizar nivel
                level_updated = False
                for level in position.entry_levels + position.exit_levels:
                    if level.level_id == level_id:
                        if level.executed:
                            raise ValidationError(f"Nivel ya ejecutado: {level_id}")
                        
                        level.executed = True
                        level.executed_price = executed_price
                        level.executed_quantity = executed_quantity
                        level.executed_at = execution_time or datetime.now(pytz.UTC)
                        level.execution_type = execution_type
                        level_updated = True
                        break
                
                if not level_updated:
                    raise ValidationError(f"Nivel no encontrado: {level_id}")
                
                # STEP 3: Recalcular progreso
                position.calculate_progress()
                
                # STEP 4: Determinar si necesita cambio de estado automático
                new_status = self._determine_auto_status_change(position)
                if new_status and new_status != position.status:
                    old_status = position.status
                    position.status = new_status
                    position.updated_at = datetime.now(pytz.UTC)
                    
                    # Registrar transición automática
                    transition = StateTransition(
                        position_id=position_id,
                        from_status=old_status,
                        to_status=new_status,
                        timestamp=datetime.now(pytz.UTC),
                        reason="Automatic transition after execution",
                        metadata={'execution_triggered': True}
                    )
                    position.state_history.append(transition)
                
                # STEP 5: Persistir cambios
                self.position_queries.update_position(position)
                
                # STEP 6: Actualizar cache
                if self._cache_enabled:
                    self._position_cache[position_id] = position
                
                # STEP 7: Notificar ejecución
                self._notify_observers(StateChangeNotification(
                    event_type=StateChangeEvent.EXECUTION_RECORDED,
                    position_id=position_id,
                    old_status=position.status,
                    new_status=position.status,
                    timestamp=datetime.now(pytz.UTC),
                    details={
                        'level_id': level_id,
                        'executed_price': executed_price,
                        'executed_quantity': executed_quantity,
                        'execution_type': execution_type.value,
                        'entry_progress': position.entry_progress_percent,
                        'exit_progress': position.exit_progress_percent
                    }
                ))
                
                logger.info(f"✅ Ejecución registrada exitosamente: {level_id}")
                return True
                
        except Exception as e:
            logger.error(f"❌ Error registrando ejecución {position_id}: {e}")
            raise StateManagerError(f"Error registrando ejecución: {e}")
    
    # ==============================================
    # CONSULTAS Y RETRIEVAL
    # ==============================================
    
    def get_position(self, position_id: str) -> Optional[EnhancedPosition]:
        """
        Obtener posición por ID (con cache)
        
        Args:
            position_id: ID de la posición
            
        Returns:
            EnhancedPosition si existe, None si no se encuentra
        """
        # Verificar cache primero
        if self._cache_enabled and position_id in self._position_cache:
            self._stats['cache_hits'] += 1
            return self._position_cache[position_id]
        
        # Cache miss - consultar DB
        self._stats['cache_misses'] += 1
        try:
            position = self.position_queries.get_position_by_id(position_id)
            
            # Actualizar cache si encontrado
            if position and self._cache_enabled:
                self._position_cache[position_id] = position
            
            return position
            
        except Exception as e:
            logger.error(f"❌ Error obteniendo posición {position_id}: {e}")
            return None
    
    def get_active_position(self, symbol: str) -> Optional[EnhancedPosition]:
        """
        Obtener posición activa para un símbolo
        
        Args:
            symbol: Símbolo del activo
            
        Returns:
            EnhancedPosition activa si existe
        """
        try:
            return self.position_queries.get_active_position(symbol)
        except Exception as e:
            logger.error(f"❌ Error obteniendo posición activa {symbol}: {e}")
            return None
    
    def get_positions_by_status(self, status: PositionStatus) -> List[EnhancedPosition]:
        """
        Obtener todas las posiciones en un estado específico
        
        Args:
            status: Estado a filtrar
            
        Returns:
            Lista de posiciones en el estado especificado
        """
        try:
            return self.position_queries.get_positions_by_status(status)
        except Exception as e:
            logger.error(f"❌ Error obteniendo posiciones por estado {status}: {e}")
            return []
    
    def get_position_summary(self, position_id: str) -> Optional[PositionSummary]:
        """
        Obtener resumen de posición con métricas calculadas
        
        Args:
            position_id: ID de la posición
            
        Returns:
            PositionSummary con métricas calculadas
        """
        position = self.get_position(position_id)
        if not position:
            return None
        
        try:
            return PositionSummary.from_position(position)
        except Exception as e:
            logger.error(f"❌ Error generando resumen {position_id}: {e}")
            return None
    
    # ==============================================
    # SISTEMA DE OBSERVERS Y NOTIFICACIONES
    # ==============================================
    
    def add_observer(self, event_type: StateChangeEvent, callback: Callable[[StateChangeNotification], None]):
        """
        Añadir observer para eventos de cambio de estado
        
        Args:
            event_type: Tipo de evento a observar
            callback: Función a llamar cuando ocurra el evento
        """
        if event_type not in self._observers:
            self._observers[event_type] = []
        
        self._observers[event_type].append(callback)
        logger.debug(f"📡 Observer añadido para {event_type.value}")
    
    def remove_observer(self, event_type: StateChangeEvent, callback: Callable):
        """Remover observer específico"""
        if event_type in self._observers and callback in self._observers[event_type]:
            self._observers[event_type].remove(callback)
            logger.debug(f"📡 Observer removido para {event_type.value}")
    
    def _notify_observers(self, notification: StateChangeNotification):
        """Notificar a todos los observers relevantes"""
        if notification.event_type in self._observers:
            for callback in self._observers[notification.event_type]:
                try:
                    callback(notification)
                except Exception as e:
                    logger.error(f"❌ Error en observer callback: {e}")
    
    # ==============================================
    # MÉTODOS PRIVADOS Y UTILITIES
    # ==============================================
    
    @contextmanager
    def _transaction_context(self):
        """Context manager para transacciones con rollback automático"""
        try:
            # Inicio de transacción (simplificado para SQLite)
            yield self
        except Exception as e:
            # Rollback automático en caso de error
            logger.error(f"❌ Error en transacción, ejecutando rollback: {e}")
            # Limpiar cache en caso de error
            self._position_cache.clear()
            raise
    
    def _validate_position_data(self, symbol: str, direction: SignalDirection, 
                               entry_levels: List[ExecutionLevel], 
                               exit_levels: List[ExecutionLevel]):
        """Validar datos de posición antes de crear"""
        if not symbol or len(symbol) < 2:
            raise ValidationError("Símbolo inválido")
        
        if not entry_levels:
            raise ValidationError("Se requiere al menos un nivel de entrada")
        
        if not exit_levels:
            raise ValidationError("Se requiere al menos un nivel de salida")
        
        # Validar precios de entrada están ordenados correctamente
        entry_prices = [level.target_price for level in entry_levels]
        if direction == SignalDirection.LONG:
            # Para LONG, entradas deben ser descendentes (comprar más barato)
            if not all(entry_prices[i] >= entry_prices[i+1] for i in range(len(entry_prices)-1)):
                raise ValidationError("Niveles de entrada LONG deben ser descendentes")
        else:
            # Para SHORT, entradas deben ser ascendentes (vender más caro)
            if not all(entry_prices[i] <= entry_prices[i+1] for i in range(len(entry_prices)-1)):
                raise ValidationError("Niveles de entrada SHORT deben ser ascendentes")
    
    def _execute_state_specific_logic(self, position: EnhancedPosition, 
                                    old_status: PositionStatus, new_status: PositionStatus):
        """Ejecutar lógica específica según cambio de estado"""
        if new_status == PositionStatus.ACTIVE:
            logger.info(f"🎯 Posición {position.position_id} ahora ACTIVA")
            
        elif new_status == PositionStatus.CLOSED:
            # Calcular P&L final
            position.calculate_pnl()
            logger.info(f"🏁 Posición {position.position_id} CERRADA con P&L: {position.total_pnl_percent:.2f}%")
            
        elif new_status == PositionStatus.STOPPED_OUT:
            logger.warning(f"🛑 Posición {position.position_id} STOPPED OUT")
    
    def _determine_auto_status_change(self, position: EnhancedPosition) -> Optional[PositionStatus]:
        """Determinar si una posición necesita cambio automático de estado"""
        current_status = position.status
        
        # Si todas las entradas están ejecutadas → ACTIVE
        if current_status == PositionStatus.PARTIALLY_FILLED:
            if position.entry_progress_percent >= 100:
                return PositionStatus.ACTIVE
        
        # Si todas las salidas están ejecutadas → CLOSED
        if current_status == PositionStatus.ACTIVE:
            if position.exit_progress_percent >= 100:
                return PositionStatus.CLOSED
        
        return None
    
    def clear_cache(self):
        """Limpiar cache completo"""
        self._position_cache.clear()
        logger.info("🧹 Cache de posiciones limpiado")
    
    def get_stats(self) -> Dict[str, Any]:
        """Obtener estadísticas del state manager"""
        cache_hit_ratio = 0.0
        total_cache_requests = self._stats['cache_hits'] + self._stats['cache_misses']
        if total_cache_requests > 0:
            cache_hit_ratio = self._stats['cache_hits'] / total_cache_requests
        
        return {
            **self._stats,
            'cache_size': len(self._position_cache),
            'cache_hit_ratio': cache_hit_ratio,
            'observers_count': sum(len(obs) for obs in self._observers.values())
        }


# ==============================================
# FACTORY Y SINGLETON PATTERN
# ==============================================

_state_manager_instance: Optional[StateManager] = None

def get_state_manager() -> StateManager:
    """
    Obtener instancia singleton del StateManager
    
    Returns:
        Instancia única del StateManager
    """
    global _state_manager_instance
    
    if _state_manager_instance is None:
        _state_manager_instance = StateManager()
    
    return _state_manager_instance


def reset_state_manager():
    """Resetear instancia del StateManager (útil para testing)"""
    global _state_manager_instance
    _state_manager_instance = None