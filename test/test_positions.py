#!/usr/bin/env python3
"""
🧪 TESTS DE POSITION TRACKING
==============================

Tests del sistema de seguimiento de posiciones:
- Registro de posiciones
- Actualización de niveles
- Cálculo de métricas
- Cierre de posiciones
"""

import pytest
from datetime import datetime
from position_manager.position_tracker import PositionTracker
from position_manager.models import PositionStatus, ExecutionStatus


# =============================================================================
# 📝 TESTS DE REGISTRO
# =============================================================================

@pytest.mark.positions
class TestPositionRegistration:
    """Tests de registro de posiciones"""

    def test_register_new_position(self, position_tracker_instance,
                                   mock_trading_signal, mock_position_plan):
        """Test: Registrar nueva posición"""
        tracker = position_tracker_instance

        position_id = tracker.register_new_position(mock_trading_signal, mock_position_plan)

        assert position_id is not None
        assert len(position_id) > 0
        assert tracker.has_active_position(mock_trading_signal.symbol)

    def test_get_position(self, position_tracker_instance,
                         mock_trading_signal, mock_position_plan):
        """Test: Obtener posición activa"""
        tracker = position_tracker_instance

        tracker.register_new_position(mock_trading_signal, mock_position_plan)
        position = tracker.get_position(mock_trading_signal.symbol)

        assert position is not None
        assert position.symbol == mock_trading_signal.symbol
        assert position.direction == mock_trading_signal.signal_type

    def test_position_initial_status(self, position_tracker_instance,
                                     mock_trading_signal, mock_position_plan):
        """Test: Estado inicial de posición"""
        tracker = position_tracker_instance

        tracker.register_new_position(mock_trading_signal, mock_position_plan)
        position = tracker.get_position(mock_trading_signal.symbol)

        assert position.status == PositionStatus.PENDING
        assert len(position.entry_levels) == 3
        assert len(position.exit_levels) == 4

    def test_multiple_positions(self, position_tracker_instance,
                               mock_position_plan):
        """Test: Múltiples posiciones activas"""
        from dataclasses import dataclass

        @dataclass
        class Signal:
            symbol: str
            signal_type: str
            signal_strength: int
            confidence_level: str
            entry_quality: str
            current_price: float
            timestamp: datetime

        tracker = position_tracker_instance

        symbols = ['AAPL', 'MSFT', 'GOOGL']

        for symbol in symbols:
            signal = Signal(
                symbol=symbol,
                signal_type='LONG',
                signal_strength=75,
                confidence_level='ALTA',
                entry_quality='FULL_ENTRY',
                current_price=150.0,
                timestamp=datetime.now()
            )
            tracker.register_new_position(signal, mock_position_plan)

        assert len(tracker.get_all_active_positions()) == 3


# =============================================================================
# 🔄 TESTS DE ACTUALIZACIÓN
# =============================================================================

@pytest.mark.positions
class TestPositionUpdates:
    """Tests de actualización de posiciones"""

    def test_mark_entry_as_filled(self, position_tracker_instance,
                                  mock_trading_signal, mock_position_plan):
        """Test: Marcar entrada como ejecutada"""
        tracker = position_tracker_instance

        tracker.register_new_position(mock_trading_signal, mock_position_plan)

        success = tracker.mark_level_as_filled(
            mock_trading_signal.symbol,
            1,
            'ENTRY',
            149.95,
            40.0
        )

        assert success is True

        position = tracker.get_position(mock_trading_signal.symbol)
        assert position.entry_levels[0].status == ExecutionStatus.FILLED
        assert position.entry_levels[0].filled_price == 149.95

    def test_position_status_progression(self, position_tracker_instance,
                                        mock_trading_signal, mock_position_plan):
        """Test: Progresión de estados de posición"""
        tracker = position_tracker_instance

        tracker.register_new_position(mock_trading_signal, mock_position_plan)
        symbol = mock_trading_signal.symbol

        # Inicial: PENDING
        position = tracker.get_position(symbol)
        assert position.status == PositionStatus.PENDING

        # Ejecutar Entry 1: PARTIALLY_FILLED
        tracker.mark_level_as_filled(symbol, 1, 'ENTRY', 150.0, 40.0)
        position = tracker.get_position(symbol)
        assert position.status == PositionStatus.PARTIALLY_FILLED

        # Ejecutar Entry 2
        tracker.mark_level_as_filled(symbol, 2, 'ENTRY', 149.0, 30.0)
        position = tracker.get_position(symbol)
        assert position.status == PositionStatus.PARTIALLY_FILLED

        # Ejecutar Entry 3: FULLY_ENTERED
        tracker.mark_level_as_filled(symbol, 3, 'ENTRY', 148.0, 30.0)
        position = tracker.get_position(symbol)
        assert position.status == PositionStatus.FULLY_ENTERED

    def test_skip_level(self, position_tracker_instance,
                       mock_trading_signal, mock_position_plan):
        """Test: Saltar nivel no ejecutado"""
        tracker = position_tracker_instance

        tracker.register_new_position(mock_trading_signal, mock_position_plan)

        success = tracker.skip_pending_level(
            mock_trading_signal.symbol,
            2,
            'ENTRY',
            'Price moved too fast'
        )

        assert success is True

        position = tracker.get_position(mock_trading_signal.symbol)
        assert position.entry_levels[1].status == ExecutionStatus.SKIPPED


# =============================================================================
# 📊 TESTS DE MÉTRICAS
# =============================================================================

@pytest.mark.positions
class TestPositionMetrics:
    """Tests de cálculo de métricas"""

    def test_calculate_metrics(self, position_tracker_instance,
                               mock_trading_signal, mock_position_plan):
        """Test: Calcular métricas de posición"""
        tracker = position_tracker_instance

        position_id = tracker.register_new_position(mock_trading_signal, mock_position_plan)

        # Ejecutar algunas entradas
        tracker.mark_level_as_filled(mock_trading_signal.symbol, 1, 'ENTRY', 150.0, 40.0)

        # Calcular métricas
        metrics = tracker.calculate_position_metrics(position_id, 151.0)

        assert 'total_filled_percentage' in metrics
        assert 'average_entry_price' in metrics
        assert 'unrealized_pnl' in metrics

    def test_average_entry_price(self, position_tracker_instance,
                                 mock_trading_signal, mock_position_plan):
        """Test: Precio medio de entrada"""
        tracker = position_tracker_instance

        tracker.register_new_position(mock_trading_signal, mock_position_plan)
        symbol = mock_trading_signal.symbol

        # Ejecutar múltiples entradas
        tracker.mark_level_as_filled(symbol, 1, 'ENTRY', 150.0, 40.0)
        tracker.mark_level_as_filled(symbol, 2, 'ENTRY', 149.0, 30.0)
        tracker.mark_level_as_filled(symbol, 3, 'ENTRY', 148.0, 30.0)

        position = tracker.get_position(symbol)

        # Calcular precio medio esperado
        # (150*40 + 149*30 + 148*30) / 100 = 149.1
        expected_avg = (150.0 * 40 + 149.0 * 30 + 148.0 * 30) / 100

        assert abs(position.average_entry_price - expected_avg) < 0.01

    def test_unrealized_pnl_long(self, position_tracker_instance,
                                 mock_trading_signal, mock_position_plan):
        """Test: P&L no realizado para posición LONG"""
        tracker = position_tracker_instance

        position_id = tracker.register_new_position(mock_trading_signal, mock_position_plan)
        symbol = mock_trading_signal.symbol

        # Ejecutar entrada
        tracker.mark_level_as_filled(symbol, 1, 'ENTRY', 150.0, 100.0)

        # Precio sube a 153
        tracker.calculate_position_metrics(position_id, 153.0)

        position = tracker.get_position(symbol)

        # P&L = (153 - 150) / 150 * 100 = 2%
        expected_pnl = ((153.0 - 150.0) / 150.0) * 100

        assert abs(position.unrealized_pnl - expected_pnl) < 0.1


# =============================================================================
# 🚪 TESTS DE CIERRE
# =============================================================================

@pytest.mark.positions
class TestPositionClosure:
    """Tests de cierre de posiciones"""

    def test_close_position(self, position_tracker_instance,
                           mock_trading_signal, mock_position_plan):
        """Test: Cerrar posición"""
        tracker = position_tracker_instance

        tracker.register_new_position(mock_trading_signal, mock_position_plan)
        symbol = mock_trading_signal.symbol

        success = tracker.close_position(symbol, "Test complete", 151.0)

        assert success is True
        assert not tracker.has_active_position(symbol)

    def test_position_closed_status(self, position_tracker_instance,
                                   mock_trading_signal, mock_position_plan):
        """Test: Estado CLOSED después de cerrar"""
        tracker = position_tracker_instance

        tracker.register_new_position(mock_trading_signal, mock_position_plan)
        symbol = mock_trading_signal.symbol

        # Antes de cerrar, registrar en memoria
        position = tracker.get_position(symbol)
        position_id = position.position_id

        tracker.close_position(symbol, "Test")

        # Position removida del tracking activo pero en memoria temporal
        assert not tracker.has_active_position(symbol)


# =============================================================================
# 📋 TESTS DE RESÚMENES
# =============================================================================

@pytest.mark.positions
class TestPositionSummary:
    """Tests de resúmenes de posiciones"""

    def test_active_positions_summary(self, position_tracker_instance,
                                      mock_position_plan):
        """Test: Resumen de posiciones activas"""
        from dataclasses import dataclass

        @dataclass
        class Signal:
            symbol: str
            signal_type: str
            signal_strength: int
            confidence_level: str
            entry_quality: str
            current_price: float
            timestamp: datetime

        tracker = position_tracker_instance

        # Crear varias posiciones
        for symbol in ['AAPL', 'MSFT']:
            signal = Signal(
                symbol=symbol,
                signal_type='LONG',
                signal_strength=75,
                confidence_level='ALTA',
                entry_quality='FULL_ENTRY',
                current_price=150.0,
                timestamp=datetime.now()
            )
            tracker.register_new_position(signal, mock_position_plan)

        summary = tracker.get_active_positions_summary()

        assert summary['total_positions'] == 2
        assert 'by_direction' in summary
        assert summary['by_direction']['LONG'] == 2

    def test_summary_with_no_positions(self, position_tracker_instance):
        """Test: Resumen sin posiciones"""
        tracker = position_tracker_instance

        summary = tracker.get_active_positions_summary()

        assert summary['total_positions'] == 0
        assert summary['total_unrealized_pnl'] == 0.0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
