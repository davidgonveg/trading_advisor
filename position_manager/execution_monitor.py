#!/usr/bin/env python3
"""
🔍 EXECUTION MONITOR V4.0
=========================

Sistema de monitoreo continuo de ejecuciones de niveles.

Responsabilidades:
- Polling continuo del precio actual
- Detectar cuando un nivel de entrada/salida se ha tocado
- Actualizar automáticamente el estado en PositionTracker
- Gestión inteligente de tolerancias y slippage
- Detectar niveles que deben ser saltados (SKIPPED)

FILOSOFÍA: "Watch dog" que nunca duerme - detecta ejecuciones en tiempo real
"""

import logging
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from uuid import uuid4

# Añadir path del proyecto para imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Imports de position_manager
from .models import (
    TrackedPosition,
    ExecutionEvent,
    ExecutionEventType,
    ExecutionStatus,
    PositionStatus
)
from .position_tracker import PositionTracker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ExecutionMonitor:
    """
    Monitor de ejecuciones en tiempo real
    
    Vigila todas las posiciones activas y detecta cuando
    los niveles de entrada/salida se ejecutan.
    """
    
    def __init__(
        self,
        position_tracker: PositionTracker,
        tolerance_pct: float = 0.1,  # ±0.1% de tolerancia
        use_real_prices: bool = False
    ):
        """
        Inicializar el monitor
        
        Args:
            position_tracker: Instancia del PositionTracker
            tolerance_pct: Tolerancia en % para considerar ejecutado
            use_real_prices: Si usar precios reales de yfinance (False para testing)
        """
        self.tracker = position_tracker
        self.tolerance_pct = tolerance_pct
        self.use_real_prices = use_real_prices
        
        # Cache de precios para evitar consultas repetidas
        self.price_cache: Dict[str, Tuple[float, datetime]] = {}
        self.cache_ttl_seconds = 30  # Tiempo de vida del cache
        
        # Importar indicators solo si usamos precios reales
        if self.use_real_prices:
            try:
                from indicators import TechnicalIndicators
                self.indicators = TechnicalIndicators()
                logger.info("✅ Execution Monitor con precios REALES (yfinance)")
            except Exception as e:
                logger.warning(f"⚠️ No se pudo importar indicators: {e}")
                self.indicators = None
                self.use_real_prices = False
        else:
            self.indicators = None
            logger.info("ℹ️ Execution Monitor en modo TESTING (precios simulados)")
        
        logger.info(f"🔍 Execution Monitor inicializado - Tolerancia: ±{tolerance_pct}%")
    
    # =========================================================================
    # 💰 OBTENCIÓN DE PRECIOS
    # =========================================================================
    
    def get_current_price(self, symbol: str) -> Optional[float]:
        """
        Obtener precio actual del mercado
        
        Args:
            symbol: Símbolo del activo
            
        Returns:
            Precio actual o None si no se puede obtener
        """
        try:
            # Verificar cache primero
            if symbol in self.price_cache:
                cached_price, cached_time = self.price_cache[symbol]
                age_seconds = (datetime.now() - cached_time).total_seconds()
                
                if age_seconds < self.cache_ttl_seconds:
                    logger.debug(f"💾 Usando precio cacheado para {symbol}: ${cached_price:.2f}")
                    return cached_price
            
            # Obtener precio nuevo
            if self.use_real_prices and self.indicators:
                # Precio real de yfinance
                data = self.indicators.get_market_data(symbol, period='1d', interval='1m')
                if data is not None and not data.empty:
                    current_price = float(data['Close'].iloc[-1])
                    self.price_cache[symbol] = (current_price, datetime.now())
                    logger.debug(f"📊 Precio real {symbol}: ${current_price:.2f}")
                    return current_price
            else:
                # Modo testing: usar precio de la posición con variación simulada
                position = self.tracker.get_position(symbol)
                if position and position.current_price > 0:
                    # Simular pequeña variación aleatoria
                    import random
                    variation = random.uniform(-0.5, 0.5)  # ±0.5%
                    simulated_price = position.current_price * (1 + variation / 100)
                    self.price_cache[symbol] = (simulated_price, datetime.now())
                    logger.debug(f"🎲 Precio simulado {symbol}: ${simulated_price:.2f}")
                    return simulated_price
            
            logger.warning(f"⚠️ No se pudo obtener precio para {symbol}")
            return None
            
        except Exception as e:
            logger.error(f"❌ Error obteniendo precio {symbol}: {e}")
            return None
    
    def clear_price_cache(self):
        """Limpiar cache de precios (útil para testing)"""
        self.price_cache.clear()
        logger.debug("🗑️ Cache de precios limpiado")
    
    # =========================================================================
    # 🎯 DETECCIÓN DE EJECUCIONES
    # =========================================================================
    
    def check_position_executions(
        self,
        position: TrackedPosition
    ) -> List[ExecutionEvent]:
        """
        Verificar si algún nivel se ha ejecutado desde último check
        
        Args:
            position: Posición a verificar
            
        Returns:
            Lista de eventos de ejecución detectados
        """
        try:
            events = []
            
            # 1. Obtener precio actual
            current_price = self.get_current_price(position.symbol)
            if current_price is None:
                return events
            
            # 2. Verificar niveles de entrada (solo PENDING)
            entry_events = self.check_entry_levels(position, current_price)
            events.extend(entry_events)
            
            # 3. Verificar niveles de salida (solo PENDING)
            exit_events = self.check_exit_levels(position, current_price)
            events.extend(exit_events)
            
            # 4. Verificar stop loss
            stop_events = self.check_stop_loss(position, current_price)
            events.extend(stop_events)
            
            # 5. Actualizar precio actual en tracker
            if events:
                self.tracker.calculate_position_metrics(
                    position.position_id,
                    current_price
                )
            
            return events
            
        except Exception as e:
            logger.error(f"❌ Error verificando ejecuciones {position.symbol}: {e}")
            return []
    
    def check_entry_levels(
        self,
        position: TrackedPosition,
        current_price: float
    ) -> List[ExecutionEvent]:
        """
        Verificar niveles de entrada específicamente
        
        Args:
            position: Posición a verificar
            current_price: Precio actual del mercado
            
        Returns:
            Lista de eventos de entrada detectados
        """
        events = []
        
        try:
            for entry in position.entry_levels:
                # Solo verificar niveles PENDING
                if entry.status != ExecutionStatus.PENDING:
                    continue
                
                # Verificar si el precio tocó el nivel con tolerancia
                executed = False
                
                if position.direction == 'LONG':
                    # LONG: Ejecuta cuando precio <= target (bajando)
                    tolerance = entry.target_price * (self.tolerance_pct / 100)
                    if current_price <= (entry.target_price + tolerance):
                        executed = True
                else:  # SHORT
                    # SHORT: Ejecuta cuando precio >= target (subiendo)
                    tolerance = entry.target_price * (self.tolerance_pct / 100)
                    if current_price >= (entry.target_price - tolerance):
                        executed = True
                
                if executed:
                    # Marcar como ejecutado en el tracker
                    success = self.tracker.mark_level_as_filled(
                        symbol=position.symbol,
                        level_id=entry.level_id,
                        level_type='ENTRY',
                        filled_price=current_price,
                        filled_percentage=entry.percentage
                    )
                    
                    if success:
                        # Crear evento
                        event = ExecutionEvent(
                            event_id=str(uuid4()),
                            position_id=position.position_id,
                            symbol=position.symbol,
                            event_type=ExecutionEventType.ENTRY_FILLED,
                            level_id=entry.level_id,
                            target_price=entry.target_price,
                            executed_price=current_price,
                            percentage=entry.percentage,
                            timestamp=datetime.now(),
                            trigger_reason=f"Precio {current_price:.2f} alcanzó nivel {entry.target_price:.2f}"
                        )
                        event.slippage = event.calculate_slippage()
                        events.append(event)
                        
                        logger.info(f"✅ ENTRY {entry.level_id} ejecutado: {position.symbol}")
                        logger.info(f"   Target: ${entry.target_price:.2f}")
                        logger.info(f"   Ejecutado: ${current_price:.2f}")
                        logger.info(f"   Slippage: {event.slippage:+.3f}%")
            
            # Verificar niveles que deben ser saltados
            if position.direction == 'LONG':
                # En LONG, si precio subió mucho, saltar niveles bajos pendientes
                for entry in position.entry_levels:
                    if entry.status == ExecutionStatus.PENDING:
                        # Si precio actual está 1% arriba del target, muy probable que se saltó
                        if current_price > entry.target_price * 1.01:
                            self.tracker.skip_pending_level(
                                position.symbol,
                                entry.level_id,
                                'ENTRY',
                                f"Precio ${current_price:.2f} pasó nivel ${entry.target_price:.2f}"
                            )
                            logger.info(f"⏭️ Entry {entry.level_id} SALTADO en {position.symbol}")
            
            return events
            
        except Exception as e:
            logger.error(f"❌ Error verificando entradas: {e}")
            return events
    
    def check_exit_levels(
        self,
        position: TrackedPosition,
        current_price: float
    ) -> List[ExecutionEvent]:
        """
        Verificar niveles de salida (take profits)
        
        Args:
            position: Posición a verificar
            current_price: Precio actual del mercado
            
        Returns:
            Lista de eventos de salida detectados
        """
        events = []
        
        try:
            for exit_level in position.exit_levels:
                # Solo verificar niveles PENDING
                if exit_level.status != ExecutionStatus.PENDING:
                    continue
                
                # Solo verificar exits si ya entramos en la posición
                if position.get_entries_executed_count() == 0:
                    continue
                
                # Verificar si el precio tocó el nivel con tolerancia
                executed = False
                
                if position.direction == 'LONG':
                    # LONG: Exit cuando precio >= target (subiendo)
                    tolerance = exit_level.target_price * (self.tolerance_pct / 100)
                    if current_price >= (exit_level.target_price - tolerance):
                        executed = True
                else:  # SHORT
                    # SHORT: Exit cuando precio <= target (bajando)
                    tolerance = exit_level.target_price * (self.tolerance_pct / 100)
                    if current_price <= (exit_level.target_price + tolerance):
                        executed = True
                
                if executed:
                    # Marcar como ejecutado en el tracker
                    success = self.tracker.mark_level_as_filled(
                        symbol=position.symbol,
                        level_id=exit_level.level_id,
                        level_type='EXIT',
                        filled_price=current_price,
                        filled_percentage=exit_level.percentage
                    )
                    
                    if success:
                        # Crear evento
                        event = ExecutionEvent(
                            event_id=str(uuid4()),
                            position_id=position.position_id,
                            symbol=position.symbol,
                            event_type=ExecutionEventType.EXIT_FILLED,
                            level_id=exit_level.level_id,
                            target_price=exit_level.target_price,
                            executed_price=current_price,
                            percentage=exit_level.percentage,
                            timestamp=datetime.now(),
                            trigger_reason=f"Take profit {exit_level.level_id} alcanzado"
                        )
                        event.slippage = event.calculate_slippage()
                        events.append(event)
                        
                        logger.info(f"🎯 EXIT {exit_level.level_id} ejecutado: {position.symbol}")
                        logger.info(f"   Target: ${exit_level.target_price:.2f}")
                        logger.info(f"   Ejecutado: ${current_price:.2f}")
                        logger.info(f"   Slippage: {event.slippage:+.3f}%")
            
            return events
            
        except Exception as e:
            logger.error(f"❌ Error verificando salidas: {e}")
            return events
    
    def check_stop_loss(
        self,
        position: TrackedPosition,
        current_price: float
    ) -> List[ExecutionEvent]:
        """
        Verificar stop loss
        
        Args:
            position: Posición a verificar
            current_price: Precio actual del mercado
            
        Returns:
            Lista con evento de stop si se tocó
        """
        events = []
        
        try:
            if not position.stop_loss:
                return events
            
            # Solo verificar si stop está PENDING
            if position.stop_loss.status != ExecutionStatus.PENDING:
                return events
            
            # Solo verificar stop si ya entramos en la posición
            if position.get_entries_executed_count() == 0:
                return events
            
            # Verificar si el precio tocó el stop
            stop_hit = False
            
            if position.direction == 'LONG':
                # LONG: Stop cuando precio <= stop (bajando)
                tolerance = position.stop_loss.target_price * (self.tolerance_pct / 100)
                if current_price <= (position.stop_loss.target_price + tolerance):
                    stop_hit = True
            else:  # SHORT
                # SHORT: Stop cuando precio >= stop (subiendo)
                tolerance = position.stop_loss.target_price * (self.tolerance_pct / 100)
                if current_price >= (position.stop_loss.target_price - tolerance):
                    stop_hit = True
            
            if stop_hit:
                # Marcar como ejecutado
                success = self.tracker.update_level_status(
                    position_id=position.position_id,
                    level_id=0,  # Stop no tiene level_id
                    level_type='STOP',
                    new_status=ExecutionStatus.FILLED,
                    filled_price=current_price
                )
                
                if success:
                    # Crear evento
                    event = ExecutionEvent(
                        event_id=str(uuid4()),
                        position_id=position.position_id,
                        symbol=position.symbol,
                        event_type=ExecutionEventType.STOP_HIT,
                        level_id=0,
                        target_price=position.stop_loss.target_price,
                        executed_price=current_price,
                        percentage=100.0,  # Stop cierra toda la posición
                        timestamp=datetime.now(),
                        trigger_reason="Stop loss alcanzado"
                    )
                    event.slippage = event.calculate_slippage()
                    events.append(event)
                    
                    logger.warning(f"🛑 STOP LOSS ejecutado: {position.symbol}")
                    logger.warning(f"   Stop: ${position.stop_loss.target_price:.2f}")
                    logger.warning(f"   Ejecutado: ${current_price:.2f}")
                    logger.warning(f"   Slippage: {event.slippage:+.3f}%")
            
            return events
            
        except Exception as e:
            logger.error(f"❌ Error verificando stop loss: {e}")
            return events
    
    # =========================================================================
    # 🔄 MONITOREO CONTINUO
    # =========================================================================
    
    def monitor_all_positions(self) -> Dict[str, List[ExecutionEvent]]:
        """
        Monitorear todas las posiciones activas
        
        Este es el LOOP PRINCIPAL que se ejecuta cada X minutos.
        
        Returns:
            Dict con position_id como key y lista de eventos como value
        """
        try:
            all_events = {}
            
            # Obtener todas las posiciones activas
            active_positions = self.tracker.get_all_active_positions()
            
            if not active_positions:
                logger.debug("ℹ️ No hay posiciones activas para monitorear")
                return all_events
            
            logger.info(f"🔍 Monitoreando {len(active_positions)} posiciones...")
            
            # Verificar cada posición
            for position in active_positions:
                try:
                    # Skip posiciones ya cerradas o stopped
                    if position.status in [PositionStatus.CLOSED, PositionStatus.STOPPED]:
                        continue
                    
                    # Verificar ejecuciones
                    events = self.check_position_executions(position)
                    
                    if events:
                        all_events[position.position_id] = events
                        logger.info(f"📊 {position.symbol}: {len(events)} eventos detectados")
                
                except Exception as e:
                    logger.error(f"❌ Error monitoreando {position.symbol}: {e}")
                    continue
            
            if all_events:
                total_events = sum(len(events) for events in all_events.values())
                logger.info(f"✅ Monitoreo completado: {total_events} eventos totales")
            else:
                logger.debug("ℹ️ No hay eventos nuevos")
            
            return all_events
            
        except Exception as e:
            logger.error(f"❌ Error en monitor_all_positions: {e}")
            return {}
    
    def monitor_single_position(
        self,
        symbol: str,
        force_price: Optional[float] = None
    ) -> List[ExecutionEvent]:
        """
        Monitorear una única posición (útil para testing)
        
        Args:
            symbol: Símbolo de la posición
            force_price: Precio forzado (para testing)
            
        Returns:
            Lista de eventos detectados
        """
        try:
            position = self.tracker.get_position(symbol)
            if not position:
                logger.warning(f"⚠️ No hay posición activa para {symbol}")
                return []
            
            # Si hay precio forzado, usarlo
            if force_price:
                old_cache = self.use_real_prices
                self.use_real_prices = False
                self.price_cache[symbol] = (force_price, datetime.now())
            
            events = self.check_position_executions(position)
            
            # Restaurar modo
            if force_price:
                self.use_real_prices = old_cache
            
            return events
            
        except Exception as e:
            logger.error(f"❌ Error monitoreando {symbol}: {e}")
            return []


# =============================================================================
# 🧪 TESTING
# =============================================================================

if __name__ == "__main__":
    print("🧪 TESTING EXECUTION MONITOR V4.0")
    print("=" * 60)
    
    # Crear tracker y monitor
    tracker = PositionTracker(use_database=False)
    monitor = ExecutionMonitor(tracker, tolerance_pct=0.1, use_real_prices=False)
    
    print("\n1. Test: Crear posición de prueba")
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
        symbol="TSLA",
        signal_type="LONG",
        signal_strength=90,
        confidence_level="ALTA",
        entry_quality="EXCELENTE",
        current_price=200.0
    )
    
    plan = MockPlan(
        entries=[
            MockLevel(200.0, 40, "Entry 1", "Price <= 200.0"),
            MockLevel(198.0, 30, "Entry 2", "Price <= 198.0"),
            MockLevel(196.0, 30, "Entry 3", "Price <= 196.0")
        ],
        exits=[
            MockLevel(204.0, 25, "TP1", "Price >= 204.0"),
            MockLevel(208.0, 25, "TP2", "Price >= 208.0"),
            MockLevel(212.0, 25, "TP3", "Price >= 212.0"),
            MockLevel(216.0, 25, "TP4", "Price >= 216.0")
        ],
        stop_loss=MockLevel(194.0, 100, "Stop Loss", "Price <= 194.0"),
        strategy_type="MOMENTUM"
    )
    
    position_id = tracker.register_new_position(signal, plan)
    print(f"   ✅ Posición TSLA creada")
    
    print("\n2. Test: Simular entrada 1 ejecutándose")
    events = monitor.monitor_single_position("TSLA", force_price=199.9)
    print(f"   Eventos detectados: {len(events)}")
    if events:
        for event in events:
            print(f"   - {event.event_type.value}: ${event.executed_price:.2f}")
    
    print("\n3. Test: Simular entrada 2 ejecutándose")
    events = monitor.monitor_single_position("TSLA", force_price=197.8)
    print(f"   Eventos detectados: {len(events)}")
    
    print("\n4. Test: Verificar estado de la posición")
    position = tracker.get_position("TSLA")
    print(f"   Status: {position.status.value}")
    print(f"   Entradas ejecutadas: {position.get_entries_executed_count()}/3")
    print(f"   % Total ejecutado: {position.total_filled_percentage}%")
    
    print("\n5. Test: Simular take profit 1 ejecutándose")
    events = monitor.monitor_single_position("TSLA", force_price=204.5)
    print(f"   Eventos detectados: {len(events)}")
    if events:
        for event in events:
            print(f"   - {event.event_type.value}: ${event.executed_price:.2f}")
    
    print("\n6. Test: Monitor all positions")
    all_events = monitor.monitor_all_positions()
    print(f"   Posiciones monitoreadas: {len(all_events)}")
    
    print("\n7. Test: Resumen final")
    summary = tracker.get_active_positions_summary()
    print(f"   Total posiciones: {summary['total_positions']}")
    print(f"   P&L total: {summary['total_unrealized_pnl']:.2f}%")
    
    print("\n✅ TODOS LOS TESTS PASARON")
    print("=" * 60)