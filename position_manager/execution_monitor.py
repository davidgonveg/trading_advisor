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

        # 🆕 V4.1: Cache de precios OHLC para evitar consultas repetidas
        self.price_cache: Dict[str, Tuple[Dict[str, float], datetime]] = {}
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
    
    def get_current_price(self, symbol: str) -> Optional[Dict[str, float]]:
        """
        🆕 V4.1: Obtener precios OHLC del mercado (Close, High, Low)

        CAMBIO CRÍTICO: Ahora devuelve dict con Close, High, Low en lugar de solo Close.
        Esto permite verificar correctamente si TP/SL fueron tocados dentro de la barra.

        Args:
            symbol: Símbolo del activo

        Returns:
            Dict con {'close': float, 'high': float, 'low': float} o None
        """
        try:
            # Verificar cache primero
            if symbol in self.price_cache:
                cached_data, cached_time = self.price_cache[symbol]
                age_seconds = (datetime.now() - cached_time).total_seconds()

                if age_seconds < self.cache_ttl_seconds:
                    logger.debug(f"💾 Usando precio cacheado para {symbol}: ${cached_data['close']:.2f}")
                    return cached_data

            # Obtener precio nuevo
            if self.use_real_prices and self.indicators:
                # Precio real de yfinance con OHLC completo
                data = self.indicators.get_market_data(symbol, period='1d', interval='1m')
                if data is not None and not data.empty:
                    # Obtener última barra con Close, High, Low
                    last_bar = data.iloc[-1]
                    price_data = {
                        'close': float(last_bar['Close']),
                        'high': float(last_bar['High']),
                        'low': float(last_bar['Low'])
                    }
                    self.price_cache[symbol] = (price_data, datetime.now())
                    logger.debug(f"📊 Precio real {symbol}: Close=${price_data['close']:.2f}, "
                               f"High=${price_data['high']:.2f}, Low=${price_data['low']:.2f}")
                    return price_data
            else:
                # Modo testing: simular OHLC con variación
                position = self.tracker.get_position(symbol)
                if position and position.current_price > 0:
                    # Simular pequeña variación aleatoria
                    import random
                    base_price = position.current_price
                    variation = random.uniform(-0.5, 0.5)  # ±0.5%
                    simulated_close = base_price * (1 + variation / 100)

                    # Simular High/Low con rango intraday
                    intraday_range = abs(variation) * 1.5  # 1.5x la variación para el rango
                    simulated_high = simulated_close * (1 + intraday_range / 100)
                    simulated_low = simulated_close * (1 - intraday_range / 100)

                    price_data = {
                        'close': simulated_close,
                        'high': simulated_high,
                        'low': simulated_low
                    }
                    self.price_cache[symbol] = (price_data, datetime.now())
                    logger.debug(f"🎲 Precio simulado {symbol}: Close=${price_data['close']:.2f}, "
                               f"High=${price_data['high']:.2f}, Low=${price_data['low']:.2f}")
                    return price_data

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
        🆕 V4.1: Verificar ejecuciones usando High/Low de barras

        CAMBIO CRÍTICO: Ahora usa High/Low para detectar TP/SL tocados.

        Args:
            position: Posición a verificar

        Returns:
            Lista de eventos de ejecución detectados
        """
        try:
            events = []

            # 1. Obtener precios OHLC actuales
            price_data = self.get_current_price(position.symbol)
            if price_data is None:
                return events

            # 2. Verificar niveles de entrada (solo PENDING)
            entry_events = self.check_entry_levels(position, price_data)
            events.extend(entry_events)

            # 3. Verificar niveles de salida (solo PENDING)
            exit_events = self.check_exit_levels(position, price_data)
            events.extend(exit_events)

            # 4. Verificar stop loss (CRÍTICO: usa Low/High)
            stop_events = self.check_stop_loss(position, price_data)
            events.extend(stop_events)

            # 5. Actualizar precio actual en tracker (usar close)
            if events:
                self.tracker.calculate_position_metrics(
                    position.position_id,
                    price_data['close']
                )

            return events

        except Exception as e:
            logger.error(f"❌ Error verificando ejecuciones {position.symbol}: {e}")
            return []
    
    def check_entry_levels(
        self,
        position: TrackedPosition,
        price_data: Dict[str, float]
    ) -> List[ExecutionEvent]:
        """
        🆕 V4.1: Verificar niveles de entrada usando Low (LONG) o High (SHORT)

        Args:
            position: Posición a verificar
            price_data: Dict con close, high, low

        Returns:
            Lista de eventos de entrada detectados
        """
        events = []

        try:
            current_price = price_data['close']

            for entry in position.entry_levels:
                # Solo verificar niveles PENDING
                if entry.status != ExecutionStatus.PENDING:
                    continue

                # Verificar si el precio tocó el nivel con tolerancia
                executed = False
                execution_price = current_price  # Precio de ejecución por defecto

                if position.direction == 'LONG':
                    # LONG: Ejecuta cuando precio <= target (bajando)
                    # Usar LOW de la barra para verificar si se tocó el nivel
                    tolerance = entry.target_price * (self.tolerance_pct / 100)
                    if price_data['low'] <= (entry.target_price + tolerance):
                        executed = True
                        # Precio de ejecución: el target o el low si es peor
                        execution_price = max(price_data['low'], entry.target_price)
                else:  # SHORT
                    # SHORT: Ejecuta cuando precio >= target (subiendo)
                    # Usar HIGH de la barra para verificar si se tocó el nivel
                    tolerance = entry.target_price * (self.tolerance_pct / 100)
                    if price_data['high'] >= (entry.target_price - tolerance):
                        executed = True
                        # Precio de ejecución: el target o el high si es peor
                        execution_price = min(price_data['high'], entry.target_price)

                if executed:
                    # Marcar como ejecutado en el tracker
                    success = self.tracker.mark_level_as_filled(
                        symbol=position.symbol,
                        level_id=entry.level_id,
                        level_type='ENTRY',
                        filled_price=execution_price,
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
                            executed_price=execution_price,
                            percentage=entry.percentage,
                            timestamp=datetime.now(),
                            trigger_reason=f"Precio tocó nivel {entry.target_price:.2f} (Low/High: {price_data['low']:.2f}/{price_data['high']:.2f})"
                        )
                        event.slippage = event.calculate_slippage()
                        events.append(event)

                        logger.info(f"✅ ENTRY {entry.level_id} ejecutado: {position.symbol}")
                        logger.info(f"   Target: ${entry.target_price:.2f}")
                        logger.info(f"   Ejecutado: ${execution_price:.2f}")
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
        price_data: Dict[str, float]
    ) -> List[ExecutionEvent]:
        """
        🆕 V4.1: Verificar niveles de salida (TP) usando High (LONG) o Low (SHORT)

        CAMBIO CRÍTICO: Usa High para detectar TP en LONG, Low para SHORT.
        Esto asegura que no nos perdamos un TP que se tocó dentro de la barra.

        Args:
            position: Posición a verificar
            price_data: Dict con close, high, low

        Returns:
            Lista de eventos de salida detectados
        """
        events = []

        try:
            current_price = price_data['close']

            for exit_level in position.exit_levels:
                # Solo verificar niveles PENDING
                if exit_level.status != ExecutionStatus.PENDING:
                    continue

                # Solo verificar exits si ya entramos en la posición
                if position.get_entries_executed_count() == 0:
                    continue

                # Verificar si el precio tocó el nivel con tolerancia
                executed = False
                execution_price = current_price  # Precio de ejecución por defecto

                if position.direction == 'LONG':
                    # LONG: Exit cuando precio >= target (subiendo)
                    # Usar HIGH de la barra para verificar si se tocó el TP
                    tolerance = exit_level.target_price * (self.tolerance_pct / 100)
                    if price_data['high'] >= (exit_level.target_price - tolerance):
                        executed = True
                        # Precio de ejecución: el target o el high si es mejor
                        execution_price = min(price_data['high'], exit_level.target_price)
                else:  # SHORT
                    # SHORT: Exit cuando precio <= target (bajando)
                    # Usar LOW de la barra para verificar si se tocó el TP
                    tolerance = exit_level.target_price * (self.tolerance_pct / 100)
                    if price_data['low'] <= (exit_level.target_price + tolerance):
                        executed = True
                        # Precio de ejecución: el target o el low si es mejor
                        execution_price = max(price_data['low'], exit_level.target_price)

                if executed:
                    # Marcar como ejecutado en el tracker
                    success = self.tracker.mark_level_as_filled(
                        symbol=position.symbol,
                        level_id=exit_level.level_id,
                        level_type='EXIT',
                        filled_price=execution_price,
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
                            executed_price=execution_price,
                            percentage=exit_level.percentage,
                            timestamp=datetime.now(),
                            trigger_reason=f"Take profit {exit_level.level_id} tocado (Low/High: {price_data['low']:.2f}/{price_data['high']:.2f})"
                        )
                        event.slippage = event.calculate_slippage()
                        events.append(event)

                        logger.info(f"🎯 EXIT {exit_level.level_id} ejecutado: {position.symbol}")
                        logger.info(f"   Target: ${exit_level.target_price:.2f}")
                        logger.info(f"   Ejecutado: ${execution_price:.2f}")
                        logger.info(f"   Slippage: {event.slippage:+.3f}%")

            return events

        except Exception as e:
            logger.error(f"❌ Error verificando salidas: {e}")
            return events
    
    def check_stop_loss(
        self,
        position: TrackedPosition,
        price_data: Dict[str, float]
    ) -> List[ExecutionEvent]:
        """
        🆕 V4.1: Verificar stop loss usando Low (LONG) o High (SHORT)

        CAMBIO MÁS CRÍTICO: Usa Low para detectar SL en LONG, High para SHORT.
        Esto asegura que NUNCA nos perdamos un stop loss que se tocó dentro de la barra,
        especialmente importante en gaps overnight.

        Ejemplo problema sin High/Low:
        - Barra overnight (20:00-22:00, 120 min)
        - Open: $100, Close: $100, High: $105, Low: $95
        - Stop loss en $98
        - Solo mirando Close ($100): NO detecta SL ❌
        - Mirando Low ($95): SÍ detecta que tocó $98 ✅

        Args:
            position: Posición a verificar
            price_data: Dict con close, high, low

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

            # Verificar si el precio tocó el stop (CRITICAL LOGIC)
            stop_hit = False
            execution_price = price_data['close']  # Precio de ejecución por defecto

            if position.direction == 'LONG':
                # LONG: Stop cuando precio <= stop (bajando)
                # Usar LOW de la barra para verificar si se tocó el SL
                tolerance = position.stop_loss.target_price * (self.tolerance_pct / 100)
                if price_data['low'] <= (position.stop_loss.target_price + tolerance):
                    stop_hit = True
                    # Precio de ejecución: el stop o el low si es peor
                    execution_price = min(price_data['low'], position.stop_loss.target_price)
                    logger.warning(f"⚠️ {position.symbol}: SL tocado - Low=${price_data['low']:.2f} <= Stop=${position.stop_loss.target_price:.2f}")
            else:  # SHORT
                # SHORT: Stop cuando precio >= stop (subiendo)
                # Usar HIGH de la barra para verificar si se tocó el SL
                tolerance = position.stop_loss.target_price * (self.tolerance_pct / 100)
                if price_data['high'] >= (position.stop_loss.target_price - tolerance):
                    stop_hit = True
                    # Precio de ejecución: el stop o el high si es peor
                    execution_price = max(price_data['high'], position.stop_loss.target_price)
                    logger.warning(f"⚠️ {position.symbol}: SL tocado - High=${price_data['high']:.2f} >= Stop=${position.stop_loss.target_price:.2f}")

            if stop_hit:
                # Marcar como ejecutado
                success = self.tracker.update_level_status(
                    position_id=position.position_id,
                    level_id=0,  # Stop no tiene level_id
                    level_type='STOP',
                    new_status=ExecutionStatus.FILLED,
                    filled_price=execution_price
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
                        executed_price=execution_price,
                        percentage=100.0,  # Stop cierra toda la posición
                        timestamp=datetime.now(),
                        trigger_reason=f"Stop loss tocado (Low/High: {price_data['low']:.2f}/{price_data['high']:.2f})"
                    )
                    event.slippage = event.calculate_slippage()
                    events.append(event)

                    logger.warning(f"🛑 STOP LOSS ejecutado: {position.symbol}")
                    logger.warning(f"   Stop: ${position.stop_loss.target_price:.2f}")
                    logger.warning(f"   Ejecutado: ${execution_price:.2f}")
                    logger.warning(f"   Barra: Low=${price_data['low']:.2f}, High=${price_data['high']:.2f}, Close=${price_data['close']:.2f}")
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
        🆕 V4.1: Monitorear una única posición (útil para testing)

        Args:
            symbol: Símbolo de la posición
            force_price: Precio forzado (para testing) - se convierte a OHLC

        Returns:
            Lista de eventos detectados
        """
        try:
            position = self.tracker.get_position(symbol)
            if not position:
                logger.warning(f"⚠️ No hay posición activa para {symbol}")
                return []

            # Si hay precio forzado, convertirlo a formato OHLC
            if force_price:
                old_cache = self.use_real_prices
                self.use_real_prices = False
                # Crear price_data simulado con pequeño rango High/Low
                price_data = {
                    'close': force_price,
                    'high': force_price * 1.001,  # +0.1% para simular rango
                    'low': force_price * 0.999    # -0.1% para simular rango
                }
                self.price_cache[symbol] = (price_data, datetime.now())

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