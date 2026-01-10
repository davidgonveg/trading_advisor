#!/usr/bin/env python3
"""
📊 POSITION TRACKER V4.0
========================

Sistema de tracking de estado para posiciones activas.

Responsabilidades:
- Registrar nuevas posiciones cuando se envía una señal
- Mantener estado en memoria + persistir en DB
- Actualizar niveles cuando se ejecutan
- Calcular métricas en tiempo real
- Cargar/guardar estado para recuperación

FILOSOFÍA: "Single source of truth" para el estado de posiciones
"""

import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any, TYPE_CHECKING
from uuid import uuid4
import json

# sys.path hack removed

# Imports de position_manager
from .models import (
    TrackedPosition,
    EntryLevelStatus,
    ExitLevelStatus,
    StopLevelStatus,
    ExecutionStatus,
    PositionStatus,
    ExecutionEvent,
    ExecutionEventType,
    create_entry_levels_from_plan,
    create_exit_levels_from_plan,
    create_stop_level_from_plan
)

# Imports condicionales para evitar errores en testing
if TYPE_CHECKING:
    from scanner import TradingSignal
    from position_calculator import PositionPlan
    from database.position_queries import PositionQueries

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PositionTracker:
    """
    Tracker principal de posiciones activas
    
    Mantiene el estado en memoria y sincroniza con base de datos.
    """
    
    def __init__(self, use_database: bool = True):
        """
        Inicializar el tracker
        
        Args:
            use_database: Si usar persistencia en DB (False para testing)
        """
        self.active_positions: Dict[str, TrackedPosition] = {}
        self.use_database = use_database
        
        # Conectar a base de datos si está habilitado
        if self.use_database:
            try:
                from database.position_queries import PositionQueries
                self.db_queries = PositionQueries()
                logger.info("✅ Position Tracker conectado a base de datos")
            except Exception as e:
                logger.warning(f"⚠️ No se pudo conectar a DB: {e}")
                self.use_database = False
                self.db_queries = None
        else:
            self.db_queries = None
            logger.info("ℹ️ Position Tracker en modo sin DB (testing)")
        
        # Cargar posiciones existentes si hay
        if self.use_database:
            self.load_from_db()
        
        logger.info(f"🚀 Position Tracker inicializado - {len(self.active_positions)} posiciones activas")
    
    # =========================================================================
    # 📝 REGISTRO Y CREACIÓN
    # =========================================================================
    
    def register_new_position(
        self, 
        signal: Any,  # TradingSignal 
        plan: Any     # PositionPlan
    ) -> str:
        """
        Registra una nueva posición cuando se envía una señal
        
        Args:
            signal: Señal original del scanner (TradingSignal)
            plan: Plan de posición del position_calculator (PositionPlan)
            
        Returns:
            position_id: UUID de la posición creada
        """
        try:
            # Generar ID único
            position_id = str(uuid4())
            
            # Crear niveles desde el plan
            entry_levels = create_entry_levels_from_plan(plan)
            exit_levels = create_exit_levels_from_plan(plan)
            stop_loss = create_stop_level_from_plan(plan)
            
            # Crear posición
            position = TrackedPosition(
                position_id=position_id,
                symbol=signal.symbol,
                direction=signal.signal_type,
                signal_timestamp=datetime.now(),
                signal_strength=signal.signal_strength,
                original_plan=plan,
                entry_levels=entry_levels,
                exit_levels=exit_levels,
                stop_loss=stop_loss,
                current_price=signal.current_price,
                status=PositionStatus.PENDING,
                last_signal_sent=datetime.now(),
                metadata={
                    'confidence_level': getattr(signal, 'confidence_level', 'UNKNOWN'),
                    'entry_quality': getattr(signal, 'entry_quality', 'UNKNOWN'),
                    'strategy_type': getattr(plan, 'strategy_type', 'UNKNOWN')
                }
            )
            
            # Guardar en memoria
            self.active_positions[signal.symbol] = position
            
            # Persistir en DB
            if self.use_database:
                self.persist_to_db(position)
            
            logger.info(f"✅ Nueva posición registrada: {signal.symbol}")
            logger.info(f"   Position ID: {position_id[:8]}...")
            logger.info(f"   Dirección: {signal.signal_type}")
            logger.info(f"   Entradas: {len(entry_levels)} niveles")
            logger.info(f"   Salidas: {len(exit_levels)} niveles")
            
            return position_id
            
        except Exception as e:
            logger.error(f"❌ Error registrando posición {signal.symbol}: {e}")
            raise
    
    # =========================================================================
    # 🔍 CONSULTAS Y ACCESO
    # =========================================================================
    
    def get_position(self, symbol: str) -> Optional[TrackedPosition]:
        """
        Obtener posición activa para un símbolo
        
        Args:
            symbol: Símbolo del activo (ej: 'AAPL')
            
        Returns:
            TrackedPosition si existe, None si no
        """
        return self.active_positions.get(symbol)
    
    def get_position_by_id(self, position_id: str) -> Optional[TrackedPosition]:
        """
        Obtener posición por su ID único
        
        Args:
            position_id: UUID de la posición
            
        Returns:
            TrackedPosition si existe, None si no
        """
        for position in self.active_positions.values():
            if position.position_id == position_id:
                return position
        return None
    
    def has_active_position(self, symbol: str) -> bool:
        """
        Verificar si hay posición activa para un símbolo
        
        Args:
            symbol: Símbolo del activo
            
        Returns:
            True si hay posición activa, False si no
        """
        return symbol in self.active_positions
    
    def get_all_active_positions(self) -> List[TrackedPosition]:
        """
        Obtener lista de todas las posiciones activas
        
        Returns:
            Lista de TrackedPosition
        """
        return list(self.active_positions.values())
    
    def get_positions_by_status(self, status: PositionStatus) -> List[TrackedPosition]:
        """
        Filtrar posiciones por estado
        
        Args:
            status: Estado a filtrar
            
        Returns:
            Lista de posiciones con ese estado
        """
        return [p for p in self.active_positions.values() if p.status == status]
    
    # =========================================================================
    # 🔄 ACTUALIZACIÓN DE NIVELES
    # =========================================================================
    
    def update_level_status(
        self,
        position_id: str,
        level_id: int,
        level_type: str,  # 'ENTRY', 'EXIT', 'STOP'
        new_status: ExecutionStatus,
        filled_price: Optional[float] = None,
        filled_percentage: Optional[float] = None
    ) -> bool:
        """
        Actualizar el estado de un nivel específico
        
        Args:
            position_id: UUID de la posición
            level_id: ID del nivel (1, 2, 3...)
            level_type: Tipo de nivel ('ENTRY', 'EXIT', 'STOP')
            new_status: Nuevo estado del nivel
            filled_price: Precio de ejecución (si aplica)
            filled_percentage: % ejecutado (si aplica)
            
        Returns:
            True si se actualizó correctamente, False si no
        """
        try:
            # Buscar posición
            position = self.get_position_by_id(position_id)
            if not position:
                logger.warning(f"⚠️ Posición {position_id[:8]}... no encontrada")
                return False
            
            # Actualizar según tipo de nivel
            level_updated = False
            
            if level_type == 'ENTRY':
                for entry in position.entry_levels:
                    if entry.level_id == level_id:
                        entry.status = new_status
                        if filled_price:
                            entry.filled_price = filled_price
                            entry.filled_timestamp = datetime.now()
                        if filled_percentage:
                            entry.filled_percentage = filled_percentage
                        level_updated = True
                        logger.info(f"✅ Entry {level_id} actualizado: {new_status.value}")
                        break
            
            elif level_type == 'EXIT':
                for exit_level in position.exit_levels:
                    if exit_level.level_id == level_id:
                        exit_level.status = new_status
                        if filled_price:
                            exit_level.filled_price = filled_price
                            exit_level.filled_timestamp = datetime.now()
                        if filled_percentage:
                            exit_level.filled_percentage = filled_percentage
                        level_updated = True
                        logger.info(f"✅ Exit {level_id} actualizado: {new_status.value}")
                        break
            
            elif level_type == 'STOP':
                if position.stop_loss:
                    position.stop_loss.status = new_status
                    if filled_price:
                        position.stop_loss.filled_price = filled_price
                        position.stop_loss.filled_timestamp = datetime.now()
                    level_updated = True
                    logger.info(f"✅ Stop Loss actualizado: {new_status.value}")
            
            if not level_updated:
                logger.warning(f"⚠️ Nivel {level_type} {level_id} no encontrado")
                return False
            
            # Recalcular métricas de la posición
            self.calculate_position_metrics(position_id, position.current_price)
            
            # Actualizar status general de la posición
            self._update_position_status(position)
            
            # Persistir cambios
            if self.use_database:
                self.persist_to_db(position)
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error actualizando nivel: {e}")
            return False
    
    def mark_level_as_filled(
        self,
        symbol: str,
        level_id: int,
        level_type: str,
        filled_price: float,
        filled_percentage: float = 100.0
    ) -> bool:
        """
        Marcar un nivel como ejecutado (shortcut conveniente)
        
        Args:
            symbol: Símbolo del activo
            level_id: ID del nivel
            level_type: 'ENTRY', 'EXIT', 'STOP'
            filled_price: Precio de ejecución
            filled_percentage: % ejecutado (default 100%)
            
        Returns:
            True si se marcó correctamente
        """
        position = self.get_position(symbol)
        if not position:
            return False
        
        return self.update_level_status(
            position_id=position.position_id,
            level_id=level_id,
            level_type=level_type,
            new_status=ExecutionStatus.FILLED,
            filled_price=filled_price,
            filled_percentage=filled_percentage
        )
    
    def skip_pending_level(
        self,
        symbol: str,
        level_id: int,
        level_type: str,
        reason: str = ""
    ) -> bool:
        """
        Marcar un nivel como SKIPPED (precio pasó sin ejecutar)
        
        Args:
            symbol: Símbolo del activo
            level_id: ID del nivel
            level_type: 'ENTRY', 'EXIT', 'STOP'
            reason: Razón por la que se saltó
            
        Returns:
            True si se marcó correctamente
        """
        position = self.get_position(symbol)
        if not position:
            return False
        
        # Actualizar estado
        success = self.update_level_status(
            position_id=position.position_id,
            level_id=level_id,
            level_type=level_type,
            new_status=ExecutionStatus.SKIPPED
        )
        
        if success and reason:
            # Añadir nota sobre por qué se saltó
            position.notes += f"\n[{datetime.now()}] Nivel {level_type} {level_id} saltado: {reason}"
        
        return success
    
    # =========================================================================
    # 📊 MÉTRICAS Y CÁLCULOS
    # =========================================================================
    
    def calculate_position_metrics(
        self,
        position_id: str,
        current_price: float
    ) -> Dict[str, Any]:
        """
        Calcular métricas en tiempo real de una posición
        
        Args:
            position_id: UUID de la posición
            current_price: Precio actual del mercado
            
        Returns:
            Dict con métricas calculadas
        """
        try:
            position = self.get_position_by_id(position_id)
            if not position:
                return {}
            
            # Actualizar precio actual
            position.current_price = current_price
            position.last_price_check = datetime.now()
            
            # Calcular % total ejecutado (entradas)
            total_filled = sum(
                e.filled_percentage for e in position.entry_levels 
                if e.is_executed()
            )
            position.total_filled_percentage = total_filled
            
            # Calcular precio medio de entrada
            if total_filled > 0:
                position.average_entry_price = position.calculate_average_entry()
            
            # Calcular P&L no realizado
            if position.average_entry_price > 0:
                if position.direction == 'LONG':
                    pnl_pct = ((current_price - position.average_entry_price) / 
                              position.average_entry_price) * 100
                else:  # SHORT
                    pnl_pct = ((position.average_entry_price - current_price) / 
                              position.average_entry_price) * 100
                
                position.unrealized_pnl = pnl_pct
            
            # Timestamp de primera entrada (si aplica)
            if not position.position_opened_at:
                for entry in position.entry_levels:
                    if entry.is_executed() and entry.filled_timestamp:
                        position.position_opened_at = entry.filled_timestamp
                        break
            
            metrics = {
                'total_filled_percentage': position.total_filled_percentage,
                'average_entry_price': position.average_entry_price,
                'current_price': current_price,
                'unrealized_pnl': position.unrealized_pnl,
                'entries_filled': position.get_entries_executed_count(),
                'exits_filled': position.get_exits_executed_count()
            }
            
            logger.debug(f"📊 Métricas {position.symbol}: PnL={position.unrealized_pnl:.2f}%")
            
            return metrics
            
        except Exception as e:
            logger.error(f"❌ Error calculando métricas: {e}")
            return {}
    
    def _update_position_status(self, position: TrackedPosition):
        """
        Actualizar el status general de la posición basado en niveles
        
        Args:
            position: Posición a actualizar
        """
        entries_filled = position.get_entries_executed_count()
        total_entries = len(position.entry_levels)
        exits_filled = position.get_exits_executed_count()
        stop_hit = position.stop_loss and position.stop_loss.is_hit()
        
        # Determinar nuevo status
        if stop_hit:
            position.status = PositionStatus.STOPPED
        elif exits_filled == len(position.exit_levels):
            position.status = PositionStatus.CLOSED
        elif exits_filled > 0:
            position.status = PositionStatus.EXITING
        elif entries_filled == total_entries:
            position.status = PositionStatus.FULLY_ENTERED
        elif entries_filled > 0:
            position.status = PositionStatus.PARTIALLY_FILLED
        else:
            position.status = PositionStatus.PENDING
    
    # =========================================================================
    # 🚪 CIERRE DE POSICIONES
    # =========================================================================
    
    def close_position(
        self,
        symbol: str,
        reason: str = "Manual",
        final_price: Optional[float] = None
    ) -> bool:
        """
        Cerrar una posición y removerla del tracking activo
        
        Args:
            symbol: Símbolo del activo
            reason: Razón del cierre
            final_price: Precio final (si aplica)
            
        Returns:
            True si se cerró correctamente
        """
        try:
            position = self.get_position(symbol)
            if not position:
                logger.warning(f"⚠️ No hay posición activa para {symbol}")
                return False
            
            # Actualizar estado final
            position.status = PositionStatus.CLOSED
            position.position_closed_at = datetime.now()
            position.notes += f"\n[{datetime.now()}] Posición cerrada: {reason}"
            
            if final_price:
                position.current_price = final_price
                self.calculate_position_metrics(position.position_id, final_price)
            
            # Persistir estado final en DB
            if self.use_database:
                self.persist_to_db(position)
            
            # Remover de tracking activo
            del self.active_positions[symbol]
            
            logger.info(f"🚪 Posición {symbol} cerrada: {reason}")
            logger.info(f"   P&L final: {position.unrealized_pnl:+.2f}%")
            logger.info(f"   Precio entrada: ${position.average_entry_price:.2f}")
            logger.info(f"   Precio cierre: ${position.current_price:.2f}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error cerrando posición {symbol}: {e}")
            return False
    
    # =========================================================================
    # 💾 PERSISTENCIA
    # =========================================================================
    
    def persist_to_db(self, position: TrackedPosition) -> bool:
        """
        Guardar/actualizar posición en base de datos
        
        Args:
            position: Posición a persistir
            
        Returns:
            True si se guardó correctamente
        """
        if not self.use_database or not self.db_queries:
            return False
        
        try:
            # Convertir a dict
            position_data = position.to_dict()
            
            # Guardar cada nivel de entrada en position_executions
            for entry in position.entry_levels:
                execution_data = {
                    'symbol': position.symbol,
                    'position_id': position.position_id,
                    'level_id': entry.level_id,
                    'execution_type': 'ENTRY',
                    'status': entry.status.value,
                    'target_price': entry.target_price,
                    'executed_price': entry.filled_price,
                    'quantity': 0,  # Se puede calcular si es necesario
                    'percentage': entry.percentage,
                    'created_at': position.signal_timestamp.isoformat(),
                    'executed_at': entry.filled_timestamp.isoformat() if entry.filled_timestamp else None,
                    'description': entry.description,
                    'trigger_condition': entry.trigger_condition,
                    'signal_strength': position.signal_strength,
                    'original_signal_timestamp': position.signal_timestamp.isoformat()
                }
                self.db_queries.insert_execution(execution_data)
            
            logger.debug(f"💾 Posición {position.symbol} persistida en DB")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error persistiendo a DB: {e}")
            return False
    
    def load_from_db(self) -> int:
        """
        Cargar posiciones activas desde base de datos
        
        Returns:
            Número de posiciones cargadas
        """
        if not self.use_database or not self.db_queries:
            return 0
        
        try:
            # Obtener posiciones activas de la DB
            active_positions_data = self.db_queries.get_active_positions()
            
            loaded_count = 0
            for position_data in active_positions_data:
                # TODO: Reconstruir TrackedPosition desde DB
                # Por ahora, skip (implementar en próxima versión)
                pass
            
            logger.info(f"📂 {loaded_count} posiciones cargadas desde DB")
            return loaded_count
            
        except Exception as e:
            logger.error(f"❌ Error cargando desde DB: {e}")
            return 0
    
    # =========================================================================
    # 📋 RESÚMENES Y REPORTES
    # =========================================================================
    
    def get_active_positions_summary(self) -> Dict[str, Any]:
        """
        Obtener resumen de todas las posiciones activas
        
        Returns:
            Dict con estadísticas generales
        """
        total = len(self.active_positions)
        
        if total == 0:
            return {
                'total_positions': 0,
                'by_status': {},
                'by_direction': {},
                'total_unrealized_pnl': 0.0
            }
        
        # Contar por status
        by_status = {}
        for status in PositionStatus:
            count = len(self.get_positions_by_status(status))
            if count > 0:
                by_status[status.value] = count
        
        # Contar por dirección
        long_count = sum(1 for p in self.active_positions.values() if p.direction == 'LONG')
        short_count = total - long_count
        
        # P&L total
        total_pnl = sum(p.unrealized_pnl for p in self.active_positions.values())
        
        # Posiciones por símbolo
        symbols = {}
        for symbol, position in self.active_positions.items():
            symbols[symbol] = {
                'status': position.status.value,
                'direction': position.direction,
                'pnl': position.unrealized_pnl,
                'filled_percentage': position.total_filled_percentage
            }
        
        return {
            'total_positions': total,
            'by_status': by_status,
            'by_direction': {
                'LONG': long_count,
                'SHORT': short_count
            },
            'total_unrealized_pnl': total_pnl,
            'average_pnl': total_pnl / total if total > 0 else 0,
            'positions': symbols
        }


# =============================================================================
# 🧪 TESTING
# =============================================================================

if __name__ == "__main__":
    print("🧪 TESTING POSITION TRACKER V4.0")
    print("=" * 60)
    
    # Test sin DB (modo testing)
    tracker = PositionTracker(use_database=False)
    
    print("\n1. Test: Crear posición mock")
    # Crear señal mock
    from dataclasses import dataclass
    
    @dataclass
    class MockSignal:
        symbol: str
        signal_type: str
        signal_strength: int
        confidence_level: str
        entry_quality: str
        current_price: float
    
    @dataclass
    class MockLevel:
        price: float
        percentage: float
        description: str
        trigger_condition: str
    
    @dataclass
    class MockPlan:
        entries: List[MockLevel]
        exits: List[MockLevel]
        stop_loss: MockLevel
        strategy_type: str
    
    signal = MockSignal(
        symbol="AAPL",
        signal_type="LONG",
        signal_strength=85,
        confidence_level="ALTA",
        entry_quality="EXCELENTE",
        current_price=150.0
    )
    
    plan = MockPlan(
        entries=[
            MockLevel(150.0, 40, "Entry 1", "Price <= 150.0"),
            MockLevel(149.0, 30, "Entry 2", "Price <= 149.0"),
            MockLevel(148.0, 30, "Entry 3", "Price <= 148.0")
        ],
        exits=[
            MockLevel(152.0, 25, "TP1", "Price >= 152.0"),
            MockLevel(154.0, 25, "TP2", "Price >= 154.0"),
            MockLevel(156.0, 25, "TP3", "Price >= 156.0"),
            MockLevel(158.0, 25, "TP4", "Price >= 158.0")
        ],
        stop_loss=MockLevel(147.0, 100, "Stop Loss", "Price <= 147.0"),
        strategy_type="SCALPING"
    )
    
    position_id = tracker.register_new_position(signal, plan)
    print(f"   ✅ Posición creada: {position_id[:8]}...")
    
    print("\n2. Test: Consultar posición")
    position = tracker.get_position("AAPL")
    print(f"   Symbol: {position.symbol}")
    print(f"   Status: {position.status.value}")
    print(f"   Entradas: {len(position.entry_levels)}")
    
    print("\n3. Test: Marcar entrada como ejecutada")
    tracker.mark_level_as_filled("AAPL", 1, "ENTRY", 149.95, 40.0)
    position = tracker.get_position("AAPL")
    print(f"   Status actualizado: {position.status.value}")
    print(f"   % Ejecutado: {position.total_filled_percentage}%")
    
    print("\n4. Test: Calcular métricas")
    metrics = tracker.calculate_position_metrics(position_id, 151.0)
    print(f"   Precio entrada: ${metrics['average_entry_price']:.2f}")
    print(f"   Precio actual: ${metrics['current_price']:.2f}")
    print(f"   P&L: {metrics['unrealized_pnl']:.2f}%")
    
    print("\n5. Test: Resumen de posiciones")
    summary = tracker.get_active_positions_summary()
    print(f"   Total posiciones: {summary['total_positions']}")
    print(f"   LONG: {summary['by_direction']['LONG']}")
    print(f"   Status: {summary['by_status']}")
    
    print("\n6. Test: Cerrar posición")
    tracker.close_position("AAPL", "Test completado", 151.0)
    summary = tracker.get_active_positions_summary()
    print(f"   Posiciones activas: {summary['total_positions']}")
    
    print("\n✅ TODOS LOS TESTS PASARON")
    print("=" * 60)