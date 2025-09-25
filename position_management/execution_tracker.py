#!/usr/bin/env python3
"""
🎯 EXECUTION TRACKER - Seguimiento de Ejecuciones de Posiciones V3.0
===================================================================

Componente responsable del seguimiento granular de ejecuciones parciales,
sincronización con base de datos y métricas de rendimiento de executions.

🎯 FUNCIONALIDADES:
1. Tracking en tiempo real de ejecuciones parciales
2. Sincronización bidireccional con position_executions table
3. Cálculo de métricas de slippage y timing
4. Coordinación con state_manager para transiciones automáticas
5. Alertas de execuciones fallidas o retrasadas

🔧 INTEGRACIÓN:
- Se conecta con state_manager para notificar cambios
- Usa position_queries para persistencia
- Expone métricas para reportes y análisis
- Coordina con scanner_enhancer para evitar duplicados

🎯 LÓGICA DE TRACKING:
- Recibe notificaciones de execuciones desde brokers/simuladores
- Valida y enriquece datos de ejecución
- Actualiza modelos in-memory y base de datos
- Calcula métricas de performance en tiempo real
- Dispara transiciones de estado automáticas
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import uuid
import pytz
import asyncio
from concurrent.futures import ThreadPoolExecutor
import threading

# Importar position management components
from .states import PositionStatus, EntryStatus, ExitStatus, ExecutionType
from .data_models import EnhancedPosition, ExecutionLevel, PositionSummary
from .state_manager import get_state_manager, StateChangeEvent, StateChangeNotification

# Importar database components  
from database.connection import get_connection
from database.position_queries import PositionQueries

import config

logger = logging.getLogger(__name__)


class ExecutionStatus(Enum):
    """Estados de ejecución específicos del tracker"""
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    CANCELLED = "CANCELLED"


class ExecutionResult(Enum):
    """Resultado de una ejecución"""
    SUCCESS = "SUCCESS"
    PARTIAL_FILL = "PARTIAL_FILL"
    NO_FILL = "NO_FILL"
    ERROR = "ERROR"
    TIMEOUT = "TIMEOUT"


@dataclass
class ExecutionAttempt:
    """Intento de ejecución individual"""
    attempt_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    position_id: str = ""
    level_id: str = ""
    symbol: str = ""
    
    # Timing
    started_at: datetime = field(default_factory=lambda: datetime.now(pytz.UTC))
    completed_at: Optional[datetime] = None
    timeout_at: Optional[datetime] = None
    
    # Ejecución
    target_price: float = 0.0
    target_quantity: int = 0
    executed_price: Optional[float] = None
    executed_quantity: int = 0
    
    # Estado y resultados
    status: ExecutionStatus = ExecutionStatus.PENDING
    result: Optional[ExecutionResult] = None
    slippage: float = 0.0
    execution_time_ms: Optional[int] = None
    
    # Metadatos
    broker_order_id: Optional[str] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    notes: str = ""


@dataclass
class ExecutionMetrics:
    """Métricas de rendimiento de ejecuciones"""
    
    # Contadores básicos
    total_attempts: int = 0
    successful_executions: int = 0
    failed_executions: int = 0
    partial_fills: int = 0
    timeouts: int = 0
    
    # Timing metrics
    avg_execution_time_ms: float = 0.0
    max_execution_time_ms: int = 0
    min_execution_time_ms: int = 0
    
    # Slippage metrics
    avg_slippage: float = 0.0
    max_slippage: float = 0.0
    total_slippage_cost: float = 0.0
    
    # Fill rates
    fill_rate: float = 0.0          # % de órdenes completadas
    avg_fill_ratio: float = 0.0     # % promedio ejecutado por orden
    
    # Por símbolo
    symbol_metrics: Dict[str, Dict[str, float]] = field(default_factory=dict)
    
    def calculate_success_rate(self) -> float:
        """Calcular tasa de éxito"""
        if self.total_attempts == 0:
            return 0.0
        return (self.successful_executions / self.total_attempts) * 100


class ExecutionTracker:
    """
    Tracker principal para seguimiento de ejecuciones
    """
    
    def __init__(self):
        """Inicializar el execution tracker"""
        self.state_manager = get_state_manager()
        self.position_queries = PositionQueries()
        
        # Estado interno
        self.active_attempts: Dict[str, ExecutionAttempt] = {}
        self.execution_history: List[ExecutionAttempt] = []
        self.metrics = ExecutionMetrics()
        
        # Configuración
        self.execution_timeout = timedelta(minutes=getattr(config, 'EXECUTION_TIMEOUT_MINUTES', 5))
        self.max_retries = getattr(config, 'MAX_EXECUTION_RETRIES', 3)
        self.slippage_tolerance = getattr(config, 'SLIPPAGE_TOLERANCE_PERCENT', 2.0)
        
        # Threading para operaciones asíncronas
        self.executor = ThreadPoolExecutor(max_workers=4)
        self._shutdown = False
        
        # Observers y callbacks
        self.execution_callbacks: List[Callable[[ExecutionAttempt], None]] = []
        
        # Registrar observer con state manager
        self.state_manager.add_observer(
            StateChangeEvent.EXECUTION_RECORDED,
            self._handle_state_manager_execution
        )
        
        logger.info("🎯 Execution Tracker inicializado")
    
    # ==============================================
    # TRACKING DE EJECUCIONES - API PRINCIPAL
    # ==============================================
    
    def track_execution_attempt(self, position_id: str, level_id: str, 
                               target_price: float, target_quantity: int,
                               execution_type: ExecutionType = ExecutionType.MARKET,
                               timeout_minutes: Optional[int] = None) -> str:
        """
        Iniciar tracking de un intento de ejecución
        
        Args:
            position_id: ID de la posición
            level_id: ID del nivel a ejecutar
            target_price: Precio objetivo
            target_quantity: Cantidad objetivo
            execution_type: Tipo de ejecución
            timeout_minutes: Timeout específico (opcional)
            
        Returns:
            attempt_id: ID único del intento de ejecución
        """
        logger.info(f"🎯 Iniciando tracking de ejecución: {position_id}/{level_id}")
        
        try:
            # Obtener información de la posición
            position = self.state_manager.get_position(position_id)
            if not position:
                raise ValueError(f"Posición no encontrada: {position_id}")
            
            # Crear intento de ejecución
            timeout = timeout_minutes or self.execution_timeout.total_seconds() / 60
            timeout_at = datetime.now(pytz.UTC) + timedelta(minutes=timeout)
            
            attempt = ExecutionAttempt(
                position_id=position_id,
                level_id=level_id,
                symbol=position.symbol,
                target_price=target_price,
                target_quantity=target_quantity,
                timeout_at=timeout_at,
                status=ExecutionStatus.PENDING
            )
            
            # Registrar intento
            self.active_attempts[attempt.attempt_id] = attempt
            self.metrics.total_attempts += 1
            
            # Programar timeout check
            self.executor.submit(self._schedule_timeout_check, attempt.attempt_id, timeout)
            
            logger.info(f"✅ Tracking iniciado: {attempt.attempt_id}")
            return attempt.attempt_id
            
        except Exception as e:
            logger.error(f"❌ Error iniciando tracking {position_id}/{level_id}: {e}")
            raise
    
    def record_execution_result(self, attempt_id: str, executed_price: float, 
                               executed_quantity: int, broker_order_id: Optional[str] = None,
                               execution_time_ms: Optional[int] = None) -> ExecutionResult:
        """
        Registrar resultado de una ejecución
        
        Args:
            attempt_id: ID del intento
            executed_price: Precio ejecutado
            executed_quantity: Cantidad ejecutada  
            broker_order_id: ID del broker (opcional)
            execution_time_ms: Tiempo de ejecución (opcional)
            
        Returns:
            ExecutionResult: Resultado de la ejecución
        """
        logger.info(f"📊 Registrando resultado de ejecución: {attempt_id}")
        
        try:
            attempt = self.active_attempts.get(attempt_id)
            if not attempt:
                logger.warning(f"⚠️ Intento no encontrado: {attempt_id}")
                return ExecutionResult.ERROR
            
            # Actualizar attempt
            attempt.executed_price = executed_price
            attempt.executed_quantity = executed_quantity
            attempt.broker_order_id = broker_order_id
            attempt.execution_time_ms = execution_time_ms
            attempt.completed_at = datetime.now(pytz.UTC)
            
            # Calcular slippage
            if executed_price and attempt.target_price:
                attempt.slippage = abs(executed_price - attempt.target_price) / attempt.target_price * 100
            
            # Determinar resultado
            if executed_quantity == 0:
                attempt.result = ExecutionResult.NO_FILL
                attempt.status = ExecutionStatus.FAILED
            elif executed_quantity == attempt.target_quantity:
                attempt.result = ExecutionResult.SUCCESS
                attempt.status = ExecutionStatus.COMPLETED
            else:
                attempt.result = ExecutionResult.PARTIAL_FILL
                attempt.status = ExecutionStatus.COMPLETED
            
            # Validar slippage
            if attempt.slippage > self.slippage_tolerance:
                logger.warning(f"⚠️ Slippage alto detectado: {attempt.slippage:.2f}% en {attempt_id}")
            
            # Actualizar métricas
            self._update_metrics(attempt)
            
            # Notificar callbacks
            self._notify_execution_callbacks(attempt)
            
            # Sincronizar con state manager
            self._sync_with_state_manager(attempt)
            
            # Mover a historial
            self._move_to_history(attempt_id)
            
            logger.info(f"✅ Ejecución registrada: {attempt.result.value} - {executed_quantity}/{attempt.target_quantity} @ ${executed_price:.2f}")
            return attempt.result
            
        except Exception as e:
            logger.error(f"❌ Error registrando ejecución {attempt_id}: {e}")
            return ExecutionResult.ERROR
    
    def record_execution_failure(self, attempt_id: str, error_message: str, 
                                retry: bool = True) -> bool:
        """
        Registrar fallo de ejecución
        
        Args:
            attempt_id: ID del intento
            error_message: Mensaje de error
            retry: Si debe reintentar automáticamente
            
        Returns:
            bool: True si se programa retry, False si se marca como fallido
        """
        logger.warning(f"⚠️ Fallo de ejecución reportado: {attempt_id} - {error_message}")
        
        try:
            attempt = self.active_attempts.get(attempt_id)
            if not attempt:
                logger.warning(f"⚠️ Intento no encontrado: {attempt_id}")
                return False
            
            attempt.error_message = error_message
            attempt.retry_count += 1
            
            # Decidir si reintentar
            if retry and attempt.retry_count <= self.max_retries:
                logger.info(f"🔄 Programando retry {attempt.retry_count}/{self.max_retries} para {attempt_id}")
                # Programar retry después de un delay
                delay_seconds = min(30 * attempt.retry_count, 300)  # Max 5 min
                self.executor.submit(self._schedule_retry, attempt_id, delay_seconds)
                return True
            else:
                # Marcar como fallido definitivamente
                attempt.status = ExecutionStatus.FAILED
                attempt.result = ExecutionResult.ERROR
                attempt.completed_at = datetime.now(pytz.UTC)
                
                # Actualizar métricas
                self.metrics.failed_executions += 1
                
                # Notificar callbacks
                self._notify_execution_callbacks(attempt)
                
                # Mover a historial
                self._move_to_history(attempt_id)
                
                logger.error(f"❌ Ejecución marcada como fallida: {attempt_id}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error procesando fallo {attempt_id}: {e}")
            return False
    
    # ==============================================
    # CONSULTAS Y MÉTRICAS
    # ==============================================
    
    def get_active_executions(self) -> List[ExecutionAttempt]:
        """Obtener todas las ejecuciones activas"""
        return list(self.active_attempts.values())
    
    def get_execution_attempt(self, attempt_id: str) -> Optional[ExecutionAttempt]:
        """Obtener intento específico"""
        return self.active_attempts.get(attempt_id)
    
    def get_executions_for_position(self, position_id: str) -> List[ExecutionAttempt]:
        """Obtener todas las ejecuciones para una posición"""
        active = [a for a in self.active_attempts.values() if a.position_id == position_id]
        historical = [a for a in self.execution_history if a.position_id == position_id]
        return active + historical
    
    def get_execution_metrics(self, symbol: Optional[str] = None, 
                             hours_back: int = 24) -> ExecutionMetrics:
        """
        Obtener métricas de ejecución
        
        Args:
            symbol: Filtrar por símbolo específico
            hours_back: Horas hacia atrás para el análisis
            
        Returns:
            ExecutionMetrics con estadísticas calculadas
        """
        cutoff_time = datetime.now(pytz.UTC) - timedelta(hours=hours_back)
        
        # Filtrar attempts relevantes
        relevant_attempts = []
        for attempt in self.execution_history + list(self.active_attempts.values()):
            if attempt.started_at >= cutoff_time:
                if not symbol or attempt.symbol == symbol:
                    relevant_attempts.append(attempt)
        
        if not relevant_attempts:
            return ExecutionMetrics()
        
        # Calcular métricas
        metrics = ExecutionMetrics()
        metrics.total_attempts = len(relevant_attempts)
        
        execution_times = []
        slippages = []
        fill_ratios = []
        
        for attempt in relevant_attempts:
            if attempt.status == ExecutionStatus.COMPLETED:
                if attempt.result == ExecutionResult.SUCCESS:
                    metrics.successful_executions += 1
                    fill_ratios.append(1.0)
                elif attempt.result == ExecutionResult.PARTIAL_FILL:
                    metrics.partial_fills += 1
                    if attempt.target_quantity > 0:
                        fill_ratios.append(attempt.executed_quantity / attempt.target_quantity)
                else:
                    fill_ratios.append(0.0)
                    
                if attempt.execution_time_ms:
                    execution_times.append(attempt.execution_time_ms)
                    
                if attempt.slippage > 0:
                    slippages.append(attempt.slippage)
                    
            elif attempt.status == ExecutionStatus.FAILED:
                metrics.failed_executions += 1
                fill_ratios.append(0.0)
            elif attempt.status == ExecutionStatus.TIMEOUT:
                metrics.timeouts += 1
                fill_ratios.append(0.0)
        
        # Calcular promedios
        if execution_times:
            metrics.avg_execution_time_ms = sum(execution_times) / len(execution_times)
            metrics.max_execution_time_ms = max(execution_times)
            metrics.min_execution_time_ms = min(execution_times)
        
        if slippages:
            metrics.avg_slippage = sum(slippages) / len(slippages)
            metrics.max_slippage = max(slippages)
        
        if fill_ratios:
            metrics.avg_fill_ratio = sum(fill_ratios) / len(fill_ratios)
        
        metrics.fill_rate = metrics.calculate_success_rate()
        
        return metrics
    
    def get_execution_summary(self) -> Dict[str, Any]:
        """Obtener resumen completo de execuciones"""
        active_count = len(self.active_attempts)
        recent_metrics = self.get_execution_metrics(hours_back=24)
        
        return {
            'active_executions': active_count,
            'total_attempts_today': recent_metrics.total_attempts,
            'success_rate_24h': recent_metrics.fill_rate,
            'avg_execution_time_ms': recent_metrics.avg_execution_time_ms,
            'avg_slippage_percent': recent_metrics.avg_slippage,
            'failed_executions_24h': recent_metrics.failed_executions,
            'timeouts_24h': recent_metrics.timeouts,
            'metrics': recent_metrics,
            'system_health': self._calculate_system_health()
        }
    
    # ==============================================
    # MÉTODOS PRIVADOS Y UTILITIES
    # ==============================================
    
    def _schedule_timeout_check(self, attempt_id: str, timeout_minutes: float):
        """Programar verificación de timeout"""
        import time
        time.sleep(timeout_minutes * 60)
        
        if self._shutdown:
            return
            
        attempt = self.active_attempts.get(attempt_id)
        if attempt and attempt.status == ExecutionStatus.PENDING:
            logger.warning(f"⏰ Timeout de ejecución: {attempt_id}")
            attempt.status = ExecutionStatus.TIMEOUT
            attempt.result = ExecutionResult.TIMEOUT
            attempt.completed_at = datetime.now(pytz.UTC)
            
            self.metrics.timeouts += 1
            self._notify_execution_callbacks(attempt)
            self._move_to_history(attempt_id)
    
    def _schedule_retry(self, attempt_id: str, delay_seconds: float):
        """Programar retry de ejecución"""
        import time
        time.sleep(delay_seconds)
        
        if self._shutdown:
            return
            
        attempt = self.active_attempts.get(attempt_id)
        if attempt and attempt.status == ExecutionStatus.FAILED:
            logger.info(f"🔄 Reintentando ejecución: {attempt_id}")
            attempt.status = ExecutionStatus.PENDING
            attempt.started_at = datetime.now(pytz.UTC)
            # Aquí se llamaría al broker/sistema de ejecución real
    
    def _update_metrics(self, attempt: ExecutionAttempt):
        """Actualizar métricas globales"""
        if attempt.result == ExecutionResult.SUCCESS:
            self.metrics.successful_executions += 1
        elif attempt.result == ExecutionResult.PARTIAL_FILL:
            self.metrics.partial_fills += 1
        elif attempt.result in [ExecutionResult.ERROR, ExecutionResult.NO_FILL]:
            self.metrics.failed_executions += 1
        
        if attempt.execution_time_ms:
            current_avg = self.metrics.avg_execution_time_ms
            count = max(1, self.metrics.successful_executions + self.metrics.partial_fills)
            self.metrics.avg_execution_time_ms = (current_avg * (count - 1) + attempt.execution_time_ms) / count
            
            self.metrics.max_execution_time_ms = max(self.metrics.max_execution_time_ms, attempt.execution_time_ms)
            if self.metrics.min_execution_time_ms == 0:
                self.metrics.min_execution_time_ms = attempt.execution_time_ms
            else:
                self.metrics.min_execution_time_ms = min(self.metrics.min_execution_time_ms, attempt.execution_time_ms)
        
        if attempt.slippage > 0:
            current_avg = self.metrics.avg_slippage
            slip_count = max(1, self.metrics.successful_executions + self.metrics.partial_fills)
            self.metrics.avg_slippage = (current_avg * (slip_count - 1) + attempt.slippage) / slip_count
            
            self.metrics.max_slippage = max(self.metrics.max_slippage, attempt.slippage)
            
            if attempt.executed_price and attempt.executed_quantity:
                slip_cost = abs(attempt.executed_price - attempt.target_price) * attempt.executed_quantity
                self.metrics.total_slippage_cost += slip_cost
        
        # Métricas por símbolo
        if attempt.symbol not in self.metrics.symbol_metrics:
            self.metrics.symbol_metrics[attempt.symbol] = {
                'attempts': 0,
                'successes': 0,
                'avg_slippage': 0.0,
                'avg_time_ms': 0.0
            }
        
        symbol_metrics = self.metrics.symbol_metrics[attempt.symbol]
        symbol_metrics['attempts'] += 1
        
        if attempt.result in [ExecutionResult.SUCCESS, ExecutionResult.PARTIAL_FILL]:
            symbol_metrics['successes'] += 1
            
            if attempt.slippage > 0:
                old_avg = symbol_metrics['avg_slippage']
                count = symbol_metrics['successes']
                symbol_metrics['avg_slippage'] = (old_avg * (count - 1) + attempt.slippage) / count
            
            if attempt.execution_time_ms:
                old_avg = symbol_metrics['avg_time_ms']
                count = symbol_metrics['successes']
                symbol_metrics['avg_time_ms'] = (old_avg * (count - 1) + attempt.execution_time_ms) / count
    
    def _notify_execution_callbacks(self, attempt: ExecutionAttempt):
        """Notificar a todos los callbacks registrados"""
        for callback in self.execution_callbacks:
            try:
                callback(attempt)
            except Exception as e:
                logger.error(f"❌ Error en execution callback: {e}")
    
    def _sync_with_state_manager(self, attempt: ExecutionAttempt):
        """Sincronizar con el state manager"""
        try:
            if attempt.result in [ExecutionResult.SUCCESS, ExecutionResult.PARTIAL_FILL]:
                # Registrar ejecución en el state manager
                success = self.state_manager.record_execution(
                    position_id=attempt.position_id,
                    level_id=attempt.level_id,
                    executed_price=attempt.executed_price,
                    executed_quantity=attempt.executed_quantity,
                    execution_time=attempt.completed_at,
                    execution_type=ExecutionType.MARKET
                )
                
                if success:
                    logger.info(f"✅ Sincronización con state manager exitosa: {attempt.attempt_id}")
                else:
                    logger.warning(f"⚠️ Error en sincronización con state manager: {attempt.attempt_id}")
                    
        except Exception as e:
            logger.error(f"❌ Error sincronizando con state manager {attempt.attempt_id}: {e}")
    
    def _move_to_history(self, attempt_id: str):
        """Mover intento a historial"""
        attempt = self.active_attempts.pop(attempt_id, None)
        if attempt:
            self.execution_history.append(attempt)
            
            # Mantener historial limitado
            max_history = getattr(config, 'MAX_EXECUTION_HISTORY', 1000)
            if len(self.execution_history) > max_history:
                self.execution_history = self.execution_history[-max_history:]
    
    def _handle_state_manager_execution(self, notification: StateChangeNotification):
        """Manejar notificaciones del state manager"""
        if notification.event_type == StateChangeEvent.EXECUTION_RECORDED:
            logger.debug(f"📊 State manager notificó ejecución: {notification.position_id}")
            # Aquí podríamos sincronizar estado si es necesario
    
    def _calculate_system_health(self) -> str:
        """Calcular salud general del sistema de ejecuciones"""
        recent_metrics = self.get_execution_metrics(hours_back=1)
        
        if recent_metrics.total_attempts == 0:
            return "IDLE"
        elif recent_metrics.fill_rate >= 95:
            return "EXCELLENT"
        elif recent_metrics.fill_rate >= 85:
            return "GOOD" 
        elif recent_metrics.fill_rate >= 70:
            return "FAIR"
        else:
            return "POOR"
    
    # ==============================================
    # OBSERVERS Y CALLBACKS
    # ==============================================
    
    def add_execution_callback(self, callback: Callable[[ExecutionAttempt], None]):
        """Añadir callback para eventos de ejecución"""
        self.execution_callbacks.append(callback)
        logger.debug("📡 Execution callback registrado")
    
    def remove_execution_callback(self, callback: Callable[[ExecutionAttempt], None]):
        """Remover callback específico"""
        if callback in self.execution_callbacks:
            self.execution_callbacks.remove(callback)
            logger.debug("📡 Execution callback removido")
    
    # ==============================================
    # CLEANUP Y SHUTDOWN
    # ==============================================
    
    def cleanup_old_attempts(self, hours_old: int = 24):
        """Limpiar intentos antiguos del historial"""
        cutoff_time = datetime.now(pytz.UTC) - timedelta(hours=hours_old)
        
        original_count = len(self.execution_history)
        self.execution_history = [
            attempt for attempt in self.execution_history
            if attempt.started_at >= cutoff_time
        ]
        
        cleaned_count = original_count - len(self.execution_history)
        if cleaned_count > 0:
            logger.info(f"🧹 Limpiados {cleaned_count} intentos de ejecución antiguos")
    
    def shutdown(self):
        """Cerrar el execution tracker de forma limpia"""
        logger.info("🛑 Iniciando shutdown del Execution Tracker...")
        
        self._shutdown = True
        
        # Esperar que terminen las tareas activas (Python 3.9+ soporta timeout)
        try:
            self.executor.shutdown(wait=True, timeout=30)
        except TypeError:
            # Fallback para versiones anteriores de Python
            self.executor.shutdown(wait=True)
        
        # Finalizar intentos activos
        for attempt_id, attempt in self.active_attempts.items():
            if attempt.status == ExecutionStatus.PENDING:
                attempt.status = ExecutionStatus.CANCELLED
                attempt.result = ExecutionResult.ERROR
                attempt.completed_at = datetime.now(pytz.UTC)
                attempt.notes = "Cancelled during system shutdown"
        
        logger.info("✅ Execution Tracker cerrado correctamente")


# ==============================================
# FACTORY Y SINGLETON PATTERN
# ==============================================

_execution_tracker_instance: Optional[ExecutionTracker] = None

def get_execution_tracker() -> ExecutionTracker:
    """
    Obtener instancia singleton del ExecutionTracker
    
    Returns:
        Instancia única del ExecutionTracker
    """
    global _execution_tracker_instance
    
    if _execution_tracker_instance is None:
        _execution_tracker_instance = ExecutionTracker()
    
    return _execution_tracker_instance


def reset_execution_tracker():
    """Resetear instancia del ExecutionTracker (útil para testing)"""
    global _execution_tracker_instance
    if _execution_tracker_instance:
        _execution_tracker_instance.shutdown()
    _execution_tracker_instance = None


# ==============================================
# TESTING Y DEMO
# ==============================================

if __name__ == "__main__":
    # Demo del execution tracker
    print("🎯 EXECUTION TRACKER - Demo")
    print("=" * 50)
    
    tracker = get_execution_tracker()
    
    # Simular tracking de una ejecución
    attempt_id = tracker.track_execution_attempt(
        position_id="DEMO_001",
        level_id="entry_1", 
        target_price=100.0,
        target_quantity=50
    )
    
    print(f"✅ Tracking iniciado: {attempt_id}")
    
    # Simular ejecución exitosa
    result = tracker.record_execution_result(
        attempt_id=attempt_id,
        executed_price=100.05,
        executed_quantity=50,
        execution_time_ms=250
    )
    
    print(f"📊 Resultado: {result.value}")
    
    # Obtener métricas
    metrics = tracker.get_execution_metrics()
    print(f"\n📈 Métricas:")
    print(f"  Intentos totales: {metrics.total_attempts}")
    print(f"  Ejecuciones exitosas: {metrics.successful_executions}")
    print(f"  Tasa de éxito: {metrics.fill_rate:.1f}%")
    print(f"  Tiempo promedio: {metrics.avg_execution_time_ms:.0f}ms")
    print(f"  Slippage promedio: {metrics.avg_slippage:.3f}%")
    
    # Resumen del sistema
    summary = tracker.get_execution_summary()
    print(f"\n🏥 Salud del sistema: {summary['system_health']}")
    
    print("\n🏁 Demo completado")
    
    # Cleanup
    tracker.shutdown()