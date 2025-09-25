#!/usr/bin/env python3
"""
🎯 POSITION TRACKER - Sistema Unificado de Tracking de Posiciones V3.0
======================================================================

Componente central que coordina y unifica el tracking de todas las posiciones
activas, integrando state_manager, execution_tracker y persistence_manager.

🎯 FUNCIONALIDADES PRINCIPALES:
1. Registro y tracking centralizado de todas las posiciones activas
2. Coordinación entre componentes (state, execution, persistence)
3. Monitoreo en tiempo real de salud y performance
4. Consolidación de métricas y reportes
5. Auto-recovery de estados inconsistentes
6. Pipeline de procesamiento de señales

🔧 ARQUITECTURA:
┌─────────────────────────────────────────────────────────────┐
│                    POSITION TRACKER                        │
│  ┌───────────────┐ ┌─────────────────┐ ┌─────────────────┐ │
│  │ State Manager │ │ Execution Track │ │ Persistence Mgr │ │
│  │   (Estados)   │ │  (Ejecuciones)  │ │   (Cache/BD)    │ │
│  └───────────────┘ └─────────────────┘ └─────────────────┘ │
│           │                 │                 │           │
│           └─────────────────┼─────────────────┘           │
│                             │                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              UNIFIED POSITION VIEW                  │   │
│  │         (Vista consolidada de posiciones)           │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘

🚀 FLUJO DE DATOS:
1. Nueva señal → Crear posición → Registrar en tracker
2. Ejecuciones → Update state → Persist changes
3. Monitoring → Health check → Auto-recovery si es necesario
4. Reportes → Consolidar métricas → Dashboard/alerts

💡 RESPONSABILIDADES:
- Mantener registry completo de posiciones activas
- Coordinar transiciones de estado automáticas  
- Consolidar datos de múltiples fuentes
- Detectar y resolver inconsistencias
- Proporcionar API unificada para consultas
- Generar métricas agregadas de performance
"""

import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Callable, Any, Tuple, Union
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict
import uuid
import pytz
from concurrent.futures import ThreadPoolExecutor, as_completed
import asyncio

# Imports de position management
from .states import PositionStatus, EntryStatus, ExitStatus, ExecutionType, SignalDirection
from .data_models import EnhancedPosition, ExecutionLevel, PositionSummary, StateTransition
from .state_manager import get_state_manager, reset_state_manager, StateChangeNotification
from .execution_tracker import get_execution_tracker, ExecutionAttempt, ExecutionMetrics
from .persistence_manager import get_persistence_manager, CacheStrategy

# Database imports
from database.position_queries import PositionQueries

import config

logger = logging.getLogger(__name__)


# ==============================================
# ENUMS Y CONSTANTES
# ==============================================

class TrackingStatus(Enum):
    """Estados del sistema de tracking"""
    INITIALIZING = "initializing"
    ACTIVE = "active"
    PAUSED = "paused"
    SHUTTING_DOWN = "shutting_down"
    STOPPED = "stopped"
    ERROR = "error"


class HealthStatus(Enum):
    """Estados de salud del sistema"""
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    DEGRADED = "degraded"
    OFFLINE = "offline"


class RecoveryAction(Enum):
    """Acciones de recovery disponibles"""
    RELOAD_FROM_DB = "reload_from_db"
    SYNC_STATE = "sync_state"
    RESTART_COMPONENT = "restart_component"
    MANUAL_INTERVENTION = "manual_intervention"
    NO_ACTION = "no_action"


# ==============================================
# DATA MODELS
# ==============================================

@dataclass
class PositionSnapshot:
    """Snapshot consolidado de una posición"""
    position_id: str
    symbol: str
    status: PositionStatus
    direction: SignalDirection
    
    # Estado actual
    created_at: datetime
    last_updated: datetime
    
    # Ejecuciones
    total_entry_levels: int = 0
    executed_entries: int = 0
    pending_entries: int = 0
    total_exit_levels: int = 0
    executed_exits: int = 0
    pending_exits: int = 0
    
    # Métricas financieras
    total_quantity_target: float = 0.0
    current_position_size: float = 0.0
    avg_entry_price: float = 0.0
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    
    # Estado de salud
    is_healthy: bool = True
    inconsistencies_detected: List[str] = field(default_factory=list)
    last_execution_time: Optional[datetime] = None
    
    # Metadatos
    confidence_level: str = ""
    signal_strength: float = 0.0
    tags: List[str] = field(default_factory=list)


@dataclass
class SystemHealthReport:
    """Reporte de salud del sistema completo"""
    timestamp: datetime = field(default_factory=lambda: datetime.now(pytz.UTC))
    overall_status: HealthStatus = HealthStatus.HEALTHY
    
    # Estadísticas generales
    total_positions: int = 0
    active_positions: int = 0
    positions_with_issues: int = 0
    
    # Estado de componentes
    state_manager_status: str = "unknown"
    execution_tracker_status: str = "unknown"
    persistence_manager_status: str = "unknown"
    
    # Métricas de performance
    avg_response_time_ms: float = 0.0
    cache_hit_rate: float = 0.0
    execution_success_rate: float = 0.0
    
    # Issues detectados
    critical_issues: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    # Recomendaciones
    recommended_actions: List[RecoveryAction] = field(default_factory=list)


@dataclass
class PositionMetrics:
    """Métricas agregadas de posiciones"""
    period_start: datetime
    period_end: datetime
    
    # Contadores
    total_positions: int = 0
    successful_positions: int = 0
    stopped_out_positions: int = 0
    cancelled_positions: int = 0
    
    # Métricas financieras
    total_pnl: float = 0.0
    avg_pnl_per_position: float = 0.0
    largest_winner: float = 0.0
    largest_loser: float = 0.0
    win_rate: float = 0.0
    
    # Métricas de ejecución
    avg_fill_time_ms: float = 0.0
    avg_slippage: float = 0.0
    fill_rate: float = 0.0
    
    # Por símbolo
    symbol_breakdown: Dict[str, Dict[str, Any]] = field(default_factory=dict)


# ==============================================
# POSITION TRACKER PRINCIPAL
# ==============================================

class PositionTracker:
    """
    Sistema unificado de tracking de posiciones
    """
    
    def __init__(self):
        """Inicializar el position tracker"""
        logger.info("🎯 Inicializando Position Tracker V3.0...")
        
        # Estado del tracker
        self.status = TrackingStatus.INITIALIZING
        self.health_status = HealthStatus.HEALTHY
        self.initialized_at = datetime.now(pytz.UTC)
        
        # Registry de posiciones activas
        self._active_positions: Dict[str, EnhancedPosition] = {}
        self._position_snapshots: Dict[str, PositionSnapshot] = {}
        self._registry_lock = threading.RLock()
        
        # Componentes integrados
        self.state_manager = get_state_manager()
        self.execution_tracker = get_execution_tracker()
        self.persistence_manager = get_persistence_manager()
        self.position_queries = PositionQueries()
        
        # Configuración
        self.monitoring_interval = timedelta(
            seconds=getattr(config, 'POSITION_MONITORING_INTERVAL_SEC', 30)
        )
        self.health_check_interval = timedelta(
            minutes=getattr(config, 'HEALTH_CHECK_INTERVAL_MIN', 5)
        )
        self.snapshot_update_interval = timedelta(
            seconds=getattr(config, 'SNAPSHOT_UPDATE_INTERVAL_SEC', 10)
        )
        
        # Background tasks
        self._shutdown = False
        self._monitoring_thread = None
        self._health_check_thread = None
        self._snapshot_update_thread = None
        
        # Callbacks y observers
        self._position_callbacks: List[Callable[[str, EnhancedPosition], None]] = []
        self._health_callbacks: List[Callable[[SystemHealthReport], None]] = []
        
        # Métricas y estadísticas
        self._stats = {
            'positions_registered': 0,
            'positions_completed': 0,
            'positions_failed': 0,
            'health_checks_performed': 0,
            'inconsistencies_resolved': 0,
            'snapshots_generated': 0
        }
        
        # Configurar observers en componentes
        self._setup_component_observers()
        
        # Inicializar background tasks
        self._start_background_tasks()
        
        self.status = TrackingStatus.ACTIVE
        logger.info("✅ Position Tracker inicializado y activo")
    
    # ==============================================
    # GESTIÓN DE POSICIONES - API PRINCIPAL
    # ==============================================
    
    def register_position(self, position: EnhancedPosition) -> bool:
        """
        Registrar nueva posición en el tracker
        
        Args:
            position: Posición a registrar
            
        Returns:
            True si se registró exitosamente
        """
        try:
            with self._registry_lock:
                # Validar posición
                if not self._validate_position(position):
                    logger.error(f"❌ Posición inválida para registro: {position.position_id}")
                    return False
                
                # Verificar duplicados
                if position.position_id in self._active_positions:
                    logger.warning(f"⚠️ Posición ya registrada: {position.position_id}")
                    return True  # Ya existe, considerar éxito
                
                # Registrar en componentes
                state_success = self.state_manager.register_position(position)
                if not state_success:
                    logger.error(f"❌ Error registrando en state_manager: {position.position_id}")
                    return False
                
                # Persistir posición
                persist_success = self.persistence_manager.save_position(position)
                if not persist_success:
                    logger.warning(f"⚠️ Warning persistiendo posición: {position.position_id}")
                    # No fallar por error de persistencia
                
                # Añadir al registry local
                self._active_positions[position.position_id] = position
                
                # Crear snapshot inicial
                snapshot = self._create_position_snapshot(position)
                self._position_snapshots[position.position_id] = snapshot
                
                # Notificar observers
                self._notify_position_change(position.position_id, position)
                
                # Actualizar stats
                self._stats['positions_registered'] += 1
                
                logger.info(f"✅ Posición registrada: {position.symbol} ({position.position_id})")
                return True
                
        except Exception as e:
            logger.error(f"❌ Error registrando posición {position.position_id}: {e}")
            return False
    
    def get_position(self, position_id: str) -> Optional[EnhancedPosition]:
        """
        Obtener posición por ID con datos consolidados
        
        Args:
            position_id: ID de la posición
            
        Returns:
            EnhancedPosition con datos actualizados o None
        """
        try:
            with self._registry_lock:
                # Buscar en registry local primero
                position = self._active_positions.get(position_id)
                
                if not position:
                    # Intentar cargar desde persistence manager
                    position = self.persistence_manager.get_position(position_id)
                    
                    if position:
                        # Añadir al registry si se encontró
                        self._active_positions[position_id] = position
                        logger.info(f"📥 Posición cargada desde persistencia: {position_id}")
                
                if position:
                    # Sincronizar con state manager
                    state_position = self.state_manager.get_position(position_id)
                    if state_position:
                        # Merge datos si hay diferencias
                        position = self._merge_position_data(position, state_position)
                
                return position
                
        except Exception as e:
            logger.error(f"❌ Error obteniendo posición {position_id}: {e}")
            return None
    
    def update_position(self, position: EnhancedPosition) -> bool:
        """
        Actualizar posición existente
        
        Args:
            position: Posición con datos actualizados
            
        Returns:
            True si se actualizó exitosamente
        """
        try:
            with self._registry_lock:
                position_id = position.position_id
                
                if position_id not in self._active_positions:
                    logger.warning(f"⚠️ Posición no registrada para update: {position_id}")
                    return self.register_position(position)
                
                # Actualizar en componentes
                state_success = self.state_manager.update_position(position)
                persist_success = self.persistence_manager.save_position(position)
                
                if not state_success:
                    logger.error(f"❌ Error actualizando en state_manager: {position_id}")
                    return False
                
                # Actualizar registry local
                self._active_positions[position_id] = position
                
                # Actualizar snapshot
                snapshot = self._create_position_snapshot(position)
                self._position_snapshots[position_id] = snapshot
                
                # Notificar cambios
                self._notify_position_change(position_id, position)
                
                logger.debug(f"🔄 Posición actualizada: {position_id}")
                return True
                
        except Exception as e:
            logger.error(f"❌ Error actualizando posición {position.position_id}: {e}")
            return False
    
    def remove_position(self, position_id: str, reason: str = "completed") -> bool:
        """
        Remover posición del tracking activo
        
        Args:
            position_id: ID de la posición
            reason: Razón de remoción
            
        Returns:
            True si se removió exitosamente
        """
        try:
            with self._registry_lock:
                position = self._active_positions.get(position_id)
                
                if not position:
                    logger.warning(f"⚠️ Posición no encontrada para remover: {position_id}")
                    return True  # Ya no existe
                
                # Verificar si está en estado final
                if position.status not in self.state_manager.FINAL_STATES:
                    logger.warning(f"⚠️ Removiendo posición no finalizada: {position_id} ({position.status})")
                
                # Remover de componentes
                self.state_manager.archive_position(position_id, reason)
                
                # Remover del registry local
                del self._active_positions[position_id]
                
                # Mantener snapshot para historial (no remover)
                if position_id in self._position_snapshots:
                    self._position_snapshots[position_id].last_updated = datetime.now(pytz.UTC)
                
                # Actualizar stats
                if reason == "completed":
                    self._stats['positions_completed'] += 1
                elif reason == "failed":
                    self._stats['positions_failed'] += 1
                
                logger.info(f"✅ Posición removida del tracking: {position_id} - {reason}")
                return True
                
        except Exception as e:
            logger.error(f"❌ Error removiendo posición {position_id}: {e}")
            return False
    
    # ==============================================
    # CONSULTAS Y REPORTS
    # ==============================================
    
    def get_active_positions(self) -> Dict[str, EnhancedPosition]:
        """Obtener todas las posiciones activas"""
        with self._registry_lock:
            return self._active_positions.copy()
    
    def get_position_snapshots(self) -> Dict[str, PositionSnapshot]:
        """Obtener snapshots de todas las posiciones"""
        with self._registry_lock:
            return self._position_snapshots.copy()
    
    def get_positions_by_symbol(self, symbol: str) -> List[EnhancedPosition]:
        """Obtener posiciones de un símbolo específico"""
        with self._registry_lock:
            return [pos for pos in self._active_positions.values() if pos.symbol == symbol]
    
    def get_positions_by_status(self, status: PositionStatus) -> List[EnhancedPosition]:
        """Obtener posiciones en un estado específico"""
        with self._registry_lock:
            return [pos for pos in self._active_positions.values() if pos.status == status]
    
    def get_unhealthy_positions(self) -> List[Tuple[str, List[str]]]:
        """Obtener posiciones con problemas detectados"""
        unhealthy = []
        
        with self._registry_lock:
            for pos_id, snapshot in self._position_snapshots.items():
                if not snapshot.is_healthy or snapshot.inconsistencies_detected:
                    unhealthy.append((pos_id, snapshot.inconsistencies_detected))
        
        return unhealthy
    
    def get_system_metrics(self) -> PositionMetrics:
        """Generar métricas del sistema"""
        try:
            period_start = datetime.now(pytz.UTC) - timedelta(hours=24)
            period_end = datetime.now(pytz.UTC)
            
            metrics = PositionMetrics(
                period_start=period_start,
                period_end=period_end
            )
            
            with self._registry_lock:
                # Métricas básicas
                metrics.total_positions = len(self._active_positions)
                
                # Obtener execution metrics
                exec_metrics = self.execution_tracker.get_execution_metrics()
                metrics.avg_fill_time_ms = exec_metrics.avg_execution_time_ms
                metrics.avg_slippage = exec_metrics.avg_slippage
                metrics.fill_rate = exec_metrics.fill_rate
                
                # Breakdown por símbolo
                symbol_stats = defaultdict(lambda: {
                    'count': 0, 'avg_pnl': 0.0, 'total_pnl': 0.0
                })
                
                for position in self._active_positions.values():
                    symbol = position.symbol
                    symbol_stats[symbol]['count'] += 1
                    symbol_stats[symbol]['total_pnl'] += position.summary.total_pnl
                
                # Calcular promedios
                for symbol, stats in symbol_stats.items():
                    if stats['count'] > 0:
                        stats['avg_pnl'] = stats['total_pnl'] / stats['count']
                
                metrics.symbol_breakdown = dict(symbol_stats)
            
            return metrics
            
        except Exception as e:
            logger.error(f"❌ Error generando métricas: {e}")
            return PositionMetrics(period_start=period_start, period_end=period_end)
    
    # ==============================================
    # HEALTH MONITORING Y AUTO-RECOVERY
    # ==============================================
    
    def perform_health_check(self) -> SystemHealthReport:
        """Realizar chequeo completo de salud del sistema"""
        try:
            report = SystemHealthReport()
            
            # Stats básicas
            with self._registry_lock:
                report.total_positions = len(self._active_positions)
                report.active_positions = len([
                    p for p in self._active_positions.values()
                    if p.status in self.state_manager.ACTIVE_TRACKING_STATES
                ])
                
                unhealthy_positions = [
                    s for s in self._position_snapshots.values()
                    if not s.is_healthy
                ]
                report.positions_with_issues = len(unhealthy_positions)
            
            # Estado de componentes
            try:
                state_health = self.state_manager.get_health_status()
                report.state_manager_status = "healthy" if state_health.get('status') == 'healthy' else "degraded"
            except Exception as e:
                report.state_manager_status = f"error: {e}"
                report.critical_issues.append(f"State Manager error: {e}")
            
            try:
                exec_summary = self.execution_tracker.get_execution_summary()
                exec_health = exec_summary.get('system_health', 'UNKNOWN')
                report.execution_tracker_status = exec_health.lower()
                report.execution_success_rate = exec_summary.get('success_rate_24h', 0.0)
            except Exception as e:
                report.execution_tracker_status = f"error: {e}"
                report.critical_issues.append(f"Execution Tracker error: {e}")
            
            try:
                persist_health = self.persistence_manager.get_health_status()
                report.persistence_manager_status = persist_health.get('status', 'unknown')
                report.cache_hit_rate = self.persistence_manager.get_cache_stats().get('cache_hit_rate', 0.0)
            except Exception as e:
                report.persistence_manager_status = f"error: {e}"
                report.critical_issues.append(f"Persistence Manager error: {e}")
            
            # Determinar estado general
            if len(report.critical_issues) > 0:
                report.overall_status = HealthStatus.CRITICAL
            elif report.positions_with_issues > report.total_positions * 0.1:  # >10% posiciones con issues
                report.overall_status = HealthStatus.WARNING
            elif report.cache_hit_rate < 80.0 or report.execution_success_rate < 90.0:
                report.overall_status = HealthStatus.DEGRADED
            else:
                report.overall_status = HealthStatus.HEALTHY
            
            # Generar recomendaciones
            if report.overall_status != HealthStatus.HEALTHY:
                report.recommended_actions = self._generate_recovery_actions(report)
            
            self._stats['health_checks_performed'] += 1
            
            # Notificar observers
            for callback in self._health_callbacks:
                try:
                    callback(report)
                except Exception as e:
                    logger.error(f"❌ Error en health callback: {e}")
            
            return report
            
        except Exception as e:
            logger.error(f"❌ Error en health check: {e}")
            error_report = SystemHealthReport()
            error_report.overall_status = HealthStatus.CRITICAL
            error_report.critical_issues = [f"Health check failed: {e}"]
            return error_report
    
    def auto_resolve_inconsistencies(self) -> int:
        """Intentar resolver inconsistencias automáticamente"""
        resolved_count = 0
        
        try:
            with self._registry_lock:
                for pos_id, position in list(self._active_positions.items()):
                    inconsistencies = self._detect_position_inconsistencies(position)
                    
                    if inconsistencies:
                        logger.info(f"🔧 Resolviendo inconsistencias en {pos_id}: {inconsistencies}")
                        
                        # Intentar resolución automática
                        if self._resolve_position_inconsistencies(position, inconsistencies):
                            resolved_count += 1
                            self._stats['inconsistencies_resolved'] += 1
                            logger.info(f"✅ Inconsistencias resueltas para {pos_id}")
                        else:
                            logger.warning(f"⚠️ No se pudieron resolver inconsistencias en {pos_id}")
            
            if resolved_count > 0:
                logger.info(f"🔧 Auto-recovery completado: {resolved_count} posiciones corregidas")
            
            return resolved_count
            
        except Exception as e:
            logger.error(f"❌ Error en auto-recovery: {e}")
            return 0
    
    # ==============================================
    # UTILIDADES PRIVADAS
    # ==============================================
    
    def _validate_position(self, position: EnhancedPosition) -> bool:
        """Validar que una posición sea válida para tracking"""
        if not position.position_id or not position.symbol:
            return False
        
        if position.direction not in [SignalDirection.LONG, SignalDirection.SHORT]:
            return False
        
        return True
    
    def _create_position_snapshot(self, position: EnhancedPosition) -> PositionSnapshot:
        """Crear snapshot de una posición"""
        try:
            executed_entries = len(position.get_executed_entries())
            pending_entries = len(position.get_pending_entries())
            executed_exits = len(position.get_executed_exits())
            pending_exits = len(position.get_pending_exits())
            
            inconsistencies = self._detect_position_inconsistencies(position)
            
            snapshot = PositionSnapshot(
                position_id=position.position_id,
                symbol=position.symbol,
                status=position.status,
                direction=position.direction,
                created_at=position.created_at,
                last_updated=datetime.now(pytz.UTC),
                
                total_entry_levels=len(position.entries),
                executed_entries=executed_entries,
                pending_entries=pending_entries,
                total_exit_levels=len(position.exits),
                executed_exits=executed_exits,
                pending_exits=pending_exits,
                
                current_position_size=position.summary.current_position_size,
                avg_entry_price=position.summary.average_entry_price,
                unrealized_pnl=position.summary.unrealized_pnl,
                realized_pnl=position.summary.realized_pnl,
                
                is_healthy=len(inconsistencies) == 0,
                inconsistencies_detected=inconsistencies,
                
                confidence_level=getattr(position, 'confidence_level', ''),
                signal_strength=getattr(position, 'signal_strength', 0.0),
                tags=getattr(position, 'tags', [])
            )
            
            self._stats['snapshots_generated'] += 1
            return snapshot
            
        except Exception as e:
            logger.error(f"❌ Error creando snapshot para {position.position_id}: {e}")
            # Crear snapshot mínimo
            return PositionSnapshot(
                position_id=position.position_id,
                symbol=position.symbol,
                status=position.status,
                direction=position.direction,
                created_at=position.created_at,
                last_updated=datetime.now(pytz.UTC),
                is_healthy=False,
                inconsistencies_detected=[f"Error creating snapshot: {e}"]
            )
    
    def _detect_position_inconsistencies(self, position: EnhancedPosition) -> List[str]:
        """Detectar inconsistencias en una posición"""
        inconsistencies = []
        
        try:
            # Validar estados vs ejecuciones
            executed_entries = len(position.get_executed_entries())
            pending_entries = len(position.get_pending_entries())
            
            if position.status == PositionStatus.FULLY_ENTERED and pending_entries > 0:
                inconsistencies.append("Status FULLY_ENTERED pero hay entradas pendientes")
            
            if position.status == PositionStatus.ENTRY_PENDING and executed_entries > 0:
                inconsistencies.append("Status ENTRY_PENDING pero hay entradas ejecutadas")
            
            if position.status == PositionStatus.PARTIALLY_FILLED and executed_entries == 0:
                inconsistencies.append("Status PARTIALLY_FILLED pero no hay entradas ejecutadas")
            
            # Validar summary vs execution levels
            calculated_size = sum(level.quantity for level in position.get_executed_entries())
            if abs(position.summary.current_position_size - calculated_size) > 0.001:
                inconsistencies.append("Position size inconsistente con execution levels")
            
            # Validar timestamps
            now = datetime.now(pytz.UTC)
            if position.updated_at > now + timedelta(minutes=1):
                inconsistencies.append("Timestamp futuro en updated_at")
            
            return inconsistencies
            
        except Exception as e:
            logger.error(f"❌ Error detectando inconsistencias en {position.position_id}: {e}")
            return [f"Error during validation: {e}"]
    
    def _resolve_position_inconsistencies(self, position: EnhancedPosition, 
                                        inconsistencies: List[str]) -> bool:
        """Intentar resolver inconsistencias automáticamente"""
        try:
            resolved = False
            
            for inconsistency in inconsistencies:
                if "Position size inconsistente" in inconsistency:
                    # Recalcular summary desde execution levels
                    position.update_summary()
                    resolved = True
                    
                elif "Status FULLY_ENTERED pero hay entradas pendientes" in inconsistency:
                    # Verificar si realmente hay entradas pendientes válidas
                    pending = position.get_pending_entries()
                    if not pending or all(not level.is_pending() for level in pending):
                        # No hay entradas realmente pendientes, status correcto
                        resolved = True
                    
                elif "Status ENTRY_PENDING pero hay entradas ejecutadas" in inconsistency:
                    # Transicionar a estado apropiado
                    executed = position.get_executed_entries()
                    pending = position.get_pending_entries()
                    
                    if executed and not pending:
                        # Todas ejecutadas -> FULLY_ENTERED
                        success = self.state_manager.transition_position_to(
                            position, PositionStatus.FULLY_ENTERED, 
                            "auto_recovery", "Inconsistency resolution"
                        )
                        if success:
                            resolved = True
                    elif executed and pending:
                        # Parcialmente ejecutadas -> PARTIALLY_FILLED
                        success = self.state_manager.transition_position_to(
                            position, PositionStatus.PARTIALLY_FILLED,
                            "auto_recovery", "Inconsistency resolution"
                        )
                        if success:
                            resolved = True
                
                elif "Timestamp futuro" in inconsistency:
                    # Corregir timestamp
                    position.updated_at = datetime.now(pytz.UTC)
                    resolved = True
            
            if resolved:
                # Guardar cambios
                self.persistence_manager.save_position(position)
                # Actualizar snapshot
                self._position_snapshots[position.position_id] = self._create_position_snapshot(position)
            
            return resolved
            
        except Exception as e:
            logger.error(f"❌ Error resolviendo inconsistencias en {position.position_id}: {e}")
            return False
    
    def _merge_position_data(self, local_position: EnhancedPosition, 
                           remote_position: EnhancedPosition) -> EnhancedPosition:
        """Mergear datos de posición de diferentes fuentes"""
        try:
            # Usar la posición más reciente como base
            if remote_position.updated_at > local_position.updated_at:
                merged = remote_position
                logger.debug(f"🔄 Usando datos remotos más recientes para {merged.position_id}")
            else:
                merged = local_position
                logger.debug(f"🔄 Manteniendo datos locales para {merged.position_id}")
            
            # Asegurar que summary esté actualizado
            merged.update_summary()
            
            return merged
            
        except Exception as e:
            logger.error(f"❌ Error mergeando datos de posición: {e}")
            return local_position  # Fallback a datos locales
    
    def _generate_recovery_actions(self, report: SystemHealthReport) -> List[RecoveryAction]:
        """Generar acciones de recovery basadas en el reporte de salud"""
        actions = []
        
        try:
            if report.overall_status == HealthStatus.CRITICAL:
                if "State Manager" in str(report.critical_issues):
                    actions.append(RecoveryAction.RESTART_COMPONENT)
                
                if "database" in str(report.critical_issues).lower():
                    actions.append(RecoveryAction.RELOAD_FROM_DB)
                
                if len(actions) == 0:
                    actions.append(RecoveryAction.MANUAL_INTERVENTION)
            
            elif report.overall_status == HealthStatus.WARNING:
                if report.positions_with_issues > 0:
                    actions.append(RecoveryAction.SYNC_STATE)
                
                if report.cache_hit_rate < 50.0:
                    actions.append(RecoveryAction.RELOAD_FROM_DB)
            
            elif report.overall_status == HealthStatus.DEGRADED:
                actions.append(RecoveryAction.SYNC_STATE)
            
            return actions if actions else [RecoveryAction.NO_ACTION]
            
        except Exception as e:
            logger.error(f"❌ Error generando recovery actions: {e}")
            return [RecoveryAction.MANUAL_INTERVENTION]
    
    # ==============================================
    # BACKGROUND TASKS
    # ==============================================
    
    def _start_background_tasks(self):
        """Iniciar tareas en background"""
        try:
            # Monitoring thread
            self._monitoring_thread = threading.Thread(
                target=self._monitoring_loop, daemon=True, name="PositionTracker-Monitor"
            )
            self._monitoring_thread.start()
            
            # Health check thread
            self._health_check_thread = threading.Thread(
                target=self._health_check_loop, daemon=True, name="PositionTracker-Health"
            )
            self._health_check_thread.start()
            
            # Snapshot update thread
            self._snapshot_update_thread = threading.Thread(
                target=self._snapshot_update_loop, daemon=True, name="PositionTracker-Snapshot"
            )
            self._snapshot_update_thread.start()
            
            logger.info("✅ Background tasks iniciados")
            
        except Exception as e:
            logger.error(f"❌ Error iniciando background tasks: {e}")
    
    def _monitoring_loop(self):
        """Loop principal de monitoreo"""
        while not self._shutdown:
            try:
                # Esperar intervalo
                time.sleep(self.monitoring_interval.total_seconds())
                
                if self._shutdown:
                    break
                
                # Verificar posiciones que necesitan atención
                positions_to_check = []
                
                with self._registry_lock:
                    for position in self._active_positions.values():
                        # Verificar posiciones en estados que requieren monitoreo
                        if position.status in self.state_manager.ACTIVE_TRACKING_STATES:
                            positions_to_check.append(position.position_id)
                
                # Procesar posiciones que necesitan atención
                for pos_id in positions_to_check:
                    self._check_position_health(pos_id)
                
                logger.debug(f"🔍 Monitoring loop completado: {len(positions_to_check)} posiciones verificadas")
                
            except Exception as e:
                logger.error(f"❌ Error en monitoring loop: {e}")
                time.sleep(10)  # Esperar antes de reintentar
    
    def _health_check_loop(self):
        """Loop de verificación de salud"""
        while not self._shutdown:
            try:
                time.sleep(self.health_check_interval.total_seconds())
                
                if self._shutdown:
                    break
                
                # Realizar health check completo
                report = self.perform_health_check()
                
                # Auto-recovery si es necesario
                if report.overall_status in [HealthStatus.WARNING, HealthStatus.DEGRADED]:
                    resolved = self.auto_resolve_inconsistencies()
                    if resolved > 0:
                        logger.info(f"🔧 Auto-recovery: {resolved} inconsistencias resueltas")
                
                logger.debug(f"🏥 Health check completado: {report.overall_status.value}")
                
            except Exception as e:
                logger.error(f"❌ Error en health check loop: {e}")
                time.sleep(60)  # Esperar más tiempo en caso de error
    
    def _snapshot_update_loop(self):
        """Loop de actualización de snapshots"""
        while not self._shutdown:
            try:
                time.sleep(self.snapshot_update_interval.total_seconds())
                
                if self._shutdown:
                    break
                
                # Actualizar snapshots de posiciones activas
                updated_count = 0
                
                with self._registry_lock:
                    for pos_id, position in self._active_positions.items():
                        try:
                            snapshot = self._create_position_snapshot(position)
                            self._position_snapshots[pos_id] = snapshot
                            updated_count += 1
                        except Exception as e:
                            logger.error(f"❌ Error actualizando snapshot {pos_id}: {e}")
                
                logger.debug(f"📸 Snapshots actualizados: {updated_count}")
                
            except Exception as e:
                logger.error(f"❌ Error en snapshot update loop: {e}")
                time.sleep(30)  # Esperar antes de reintentar
    
    def _check_position_health(self, position_id: str):
        """Verificar salud de una posición específica"""
        try:
            position = self._active_positions.get(position_id)
            if not position:
                return
            
            # Detectar inconsistencias
            inconsistencies = self._detect_position_inconsistencies(position)
            
            if inconsistencies:
                logger.warning(f"⚠️ Inconsistencias detectadas en {position_id}: {inconsistencies}")
                
                # Intentar resolución automática
                if self._resolve_position_inconsistencies(position, inconsistencies):
                    logger.info(f"✅ Inconsistencias resueltas automáticamente en {position_id}")
                else:
                    logger.error(f"❌ No se pudieron resolver inconsistencias en {position_id}")
            
            # Verificar timeouts de ejecución
            self._check_execution_timeouts(position)
            
        except Exception as e:
            logger.error(f"❌ Error verificando salud de posición {position_id}: {e}")
    
    def _check_execution_timeouts(self, position: EnhancedPosition):
        """Verificar timeouts de ejecución"""
        try:
            now = datetime.now(pytz.UTC)
            timeout_threshold = timedelta(minutes=30)  # Timeout configurable
            
            for entry in position.entries:
                if (entry.status == EntryStatus.PENDING and 
                    entry.created_at and 
                    now - entry.created_at > timeout_threshold):
                    
                    logger.warning(f"⏰ Timeout en entrada: {position.position_id} - {entry.level_id}")
                    
                    # Marcar como expirada
                    entry.status = EntryStatus.EXPIRED
                    
                    # Actualizar posición
                    self.update_position(position)
            
        except Exception as e:
            logger.error(f"❌ Error verificando timeouts: {e}")
    
    # ==============================================
    # OBSERVERS Y CALLBACKS
    # ==============================================
    
    def _setup_component_observers(self):
        """Configurar observers en componentes integrados"""
        try:
            # Observer para state changes
            def on_state_change(notification: StateChangeNotification):
                try:
                    position_id = notification.position_id
                    logger.debug(f"🔄 State change recibido: {position_id} -> {notification.new_state}")
                    
                    # Actualizar snapshot
                    position = self._active_positions.get(position_id)
                    if position:
                        snapshot = self._create_position_snapshot(position)
                        with self._registry_lock:
                            self._position_snapshots[position_id] = snapshot
                
                except Exception as e:
                    logger.error(f"❌ Error procesando state change: {e}")
            
            # Registrar observer (si el state_manager lo soporta)
            if hasattr(self.state_manager, 'add_state_change_observer'):
                self.state_manager.add_state_change_observer(on_state_change)
            
        except Exception as e:
            logger.error(f"❌ Error configurando observers: {e}")
    
    def _notify_position_change(self, position_id: str, position: EnhancedPosition):
        """Notificar cambio de posición a observers"""
        for callback in self._position_callbacks:
            try:
                callback(position_id, position)
            except Exception as e:
                logger.error(f"❌ Error en position callback: {e}")
    
    def add_position_observer(self, callback: Callable[[str, EnhancedPosition], None]):
        """Añadir observer para cambios de posición"""
        self._position_callbacks.append(callback)
    
    def add_health_observer(self, callback: Callable[[SystemHealthReport], None]):
        """Añadir observer para reportes de salud"""
        self._health_callbacks.append(callback)
    
    # ==============================================
    # BATCH OPERATIONS
    # ==============================================
    
    def batch_register_positions(self, positions: List[EnhancedPosition]) -> Dict[str, bool]:
        """Registrar múltiples posiciones en batch"""
        results = {}
        
        try:
            with ThreadPoolExecutor(max_workers=5) as executor:
                future_to_position = {
                    executor.submit(self.register_position, pos): pos.position_id
                    for pos in positions
                }
                
                for future in as_completed(future_to_position):
                    pos_id = future_to_position[future]
                    try:
                        results[pos_id] = future.result()
                    except Exception as e:
                        logger.error(f"❌ Error en batch register {pos_id}: {e}")
                        results[pos_id] = False
            
            successful = sum(1 for success in results.values() if success)
            logger.info(f"📊 Batch register completado: {successful}/{len(positions)} exitosas")
            
            return results
            
        except Exception as e:
            logger.error(f"❌ Error en batch register: {e}")
            return {pos.position_id: False for pos in positions}
    
    def batch_update_positions(self, positions: List[EnhancedPosition]) -> Dict[str, bool]:
        """Actualizar múltiples posiciones en batch"""
        results = {}
        
        try:
            for position in positions:
                results[position.position_id] = self.update_position(position)
            
            successful = sum(1 for success in results.values() if success)
            logger.info(f"📊 Batch update completado: {successful}/{len(positions)} exitosas")
            
            return results
            
        except Exception as e:
            logger.error(f"❌ Error en batch update: {e}")
            return {pos.position_id: False for pos in positions}
    
    # ==============================================
    # ESTADÍSTICAS Y REPORTING
    # ==============================================
    
    def get_tracker_stats(self) -> Dict[str, Any]:
        """Obtener estadísticas del tracker"""
        with self._registry_lock:
            stats = self._stats.copy()
            
            stats.update({
                'active_positions_count': len(self._active_positions),
                'snapshots_count': len(self._position_snapshots),
                'status': self.status.value,
                'health_status': self.health_status.value,
                'uptime_seconds': (datetime.now(pytz.UTC) - self.initialized_at).total_seconds(),
                'background_threads_alive': {
                    'monitoring': self._monitoring_thread.is_alive() if self._monitoring_thread else False,
                    'health_check': self._health_check_thread.is_alive() if self._health_check_thread else False,
                    'snapshot_update': self._snapshot_update_thread.is_alive() if self._snapshot_update_thread else False
                }
            })
            
            return stats
    
    def export_positions_summary(self) -> Dict[str, Any]:
        """Exportar resumen completo de posiciones"""
        try:
            summary = {
                'timestamp': datetime.now(pytz.UTC).isoformat(),
                'tracker_stats': self.get_tracker_stats(),
                'system_health': self.perform_health_check(),
                'active_positions': {},
                'position_snapshots': {},
                'system_metrics': self.get_system_metrics()
            }
            
            # Serializar posiciones activas
            with self._registry_lock:
                for pos_id, position in self._active_positions.items():
                    summary['active_positions'][pos_id] = {
                        'position_id': position.position_id,
                        'symbol': position.symbol,
                        'status': position.status.value,
                        'direction': position.direction.value,
                        'created_at': position.created_at.isoformat(),
                        'updated_at': position.updated_at.isoformat(),
                        'entry_levels': len(position.entries),
                        'exit_levels': len(position.exits),
                        'current_pnl': position.summary.total_pnl
                    }
                
                # Serializar snapshots
                for pos_id, snapshot in self._position_snapshots.items():
                    summary['position_snapshots'][pos_id] = {
                        'position_id': snapshot.position_id,
                        'symbol': snapshot.symbol,
                        'status': snapshot.status.value,
                        'is_healthy': snapshot.is_healthy,
                        'inconsistencies': snapshot.inconsistencies_detected,
                        'last_updated': snapshot.last_updated.isoformat()
                    }
            
            return summary
            
        except Exception as e:
            logger.error(f"❌ Error exportando summary: {e}")
            return {'error': str(e), 'timestamp': datetime.now(pytz.UTC).isoformat()}
    
    # ==============================================
    # SHUTDOWN Y CLEANUP
    # ==============================================
    
    def shutdown(self):
        """Shutdown limpio del position tracker"""
        logger.info("🛑 Iniciando shutdown del Position Tracker...")
        
        self.status = TrackingStatus.SHUTTING_DOWN
        self._shutdown = True
        
        try:
            # Esperar que terminen background tasks
            if self._monitoring_thread and self._monitoring_thread.is_alive():
                self._monitoring_thread.join(timeout=10)
            
            if self._health_check_thread and self._health_check_thread.is_alive():
                self._health_check_thread.join(timeout=10)
            
            if self._snapshot_update_thread and self._snapshot_update_thread.is_alive():
                self._snapshot_update_thread.join(timeout=10)
            
            # Crear snapshot final de todas las posiciones
            logger.info("📸 Creando snapshots finales...")
            with self._registry_lock:
                for pos_id, position in self._active_positions.items():
                    try:
                        snapshot = self._create_position_snapshot(position)
                        self._position_snapshots[pos_id] = snapshot
                    except Exception as e:
                        logger.error(f"❌ Error creando snapshot final {pos_id}: {e}")
            
            # Estadísticas finales
            final_stats = self.get_tracker_stats()
            logger.info(f"📊 Stats finales: {final_stats['active_positions_count']} posiciones activas")
            
            self.status = TrackingStatus.STOPPED
            logger.info("✅ Position Tracker cerrado correctamente")
            
        except Exception as e:
            logger.error(f"❌ Error durante shutdown: {e}")
            self.status = TrackingStatus.ERROR


# ==============================================
# FACTORY Y SINGLETON PATTERN
# ==============================================

_position_tracker_instance: Optional[PositionTracker] = None

def get_position_tracker() -> PositionTracker:
    """
    Obtener instancia singleton del PositionTracker
    
    Returns:
        Instancia única del PositionTracker
    """
    global _position_tracker_instance
    
    if _position_tracker_instance is None:
        _position_tracker_instance = PositionTracker()
    
    return _position_tracker_instance


def reset_position_tracker():
    """Resetear instancia del PositionTracker (útil para testing)"""
    global _position_tracker_instance
    if _position_tracker_instance:
        _position_tracker_instance.shutdown()
    _position_tracker_instance = None


# ==============================================
# TESTING Y DEMO
# ==============================================

if __name__ == "__main__":
    # Demo del position tracker
    print("🎯 POSITION TRACKER - Demo")
    print("=" * 60)
    
    tracker = get_position_tracker()
    
    # Crear posición de prueba
    from .data_models import EnhancedPosition
    from .states import SignalDirection
    
    demo_position = EnhancedPosition(
        symbol="DEMO_TRACKER",
        direction=SignalDirection.LONG,
        position_id="DEMO_TRACKER_001",
        signal_strength=92,
        confidence_level="HIGH"
    )
    
    # Registrar posición
    print("📝 Registrando posición de prueba...")
    success = tracker.register_position(demo_position)
    print(f"Resultado: {'✅ Exitoso' if success else '❌ Error'}")
    
    # Obtener posición
    print("\n📊 Obteniendo posición...")
    retrieved = tracker.get_position("DEMO_TRACKER_001")
    print(f"Resultado: {'✅ Encontrada' if retrieved else '❌ No encontrada'}")
    
    # Health check
    print("\n🏥 Health check del sistema...")
    health_report = tracker.perform_health_check()
    print(f"Estado general: {health_report.overall_status.value}")
    print(f"Posiciones activas: {health_report.active_positions}")
    print(f"Posiciones con issues: {health_report.positions_with_issues}")
    
    # Estadísticas
    print("\n📈 Estadísticas del tracker:")
    stats = tracker.get_tracker_stats()
    for key, value in stats.items():
        if key != 'background_threads_alive':
            print(f"  {key}: {value}")
    
    # Métricas del sistema
    print("\n📊 Métricas del sistema:")
    metrics = tracker.get_system_metrics()
    print(f"  Total posiciones: {metrics.total_positions}")
    print(f"  Fill rate: {metrics.fill_rate:.1f}%")
    print(f"  Tiempo promedio ejecución: {metrics.avg_fill_time_ms:.0f}ms")
    
    print("\n🏁 Demo completado")
    
    # Cleanup
    time.sleep(2)  # Permitir que background tasks procesen
    tracker.shutdown()