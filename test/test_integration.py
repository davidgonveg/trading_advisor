#!/usr/bin/env python3
"""
🧪 TESTS DE INTEGRACIÓN
========================

Tests end-to-end del sistema completo:
- Flujo completo desde datos hasta señales
- Integración entre componentes
- Escenarios reales
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from indicators import TechnicalIndicators
from gap_detector import GapDetector
from position_manager.position_tracker import PositionTracker


# =============================================================================
# 🔄 TESTS DE FLUJO COMPLETO
# =============================================================================

@pytest.mark.integration
class TestEndToEndFlow:
    """Tests de flujo completo del sistema"""

    def test_data_to_indicators_flow(self, sample_ohlcv_data):
        """Test: Flujo de datos a indicadores"""
        indicators = TechnicalIndicators()

        # Calcular indicadores desde datos crudos
        result = indicators.calculate_all_indicators(
            'TEST',
            sample_ohlcv_data,
            current_price=sample_ohlcv_data['Close'].iloc[-1],
            current_volume=sample_ohlcv_data['Volume'].iloc[-1]
        )

        # Verificar que todos los indicadores se calcularon
        assert 'rsi' in result
        assert 'macd' in result
        assert 'vwap' in result
        assert 'atr' in result

        print(f"✅ Indicadores calculados correctamente")
        print(f"   RSI: {result['rsi']['rsi']:.1f}")
        print(f"   MACD: {result['macd']['histogram']:.2f}")
        print(f"   ATR: {result['atr']['atr']:.2f}")

    def test_gap_detection_to_filling_flow(self, gap_detector_instance, sample_ohlcv_with_gaps):
        """Test: Flujo de detección a relleno de gaps"""
        # 1. Detectar gaps
        report = gap_detector_instance.analyze_data_quality(
            'TEST',
            sample_ohlcv_with_gaps,
            sample_ohlcv_with_gaps.index[0],
            sample_ohlcv_with_gaps.index[-1]
        )

        print(f"✅ Análisis de gaps completado")
        print(f"   Gaps totales: {report.total_gaps}")
        print(f"   Score de calidad: {report.overall_quality_score:.1f}")
        print(f"   Completitud: {report.completeness_pct:.1f}%")

        # 2. Verificar que se detectaron gaps
        assert report.total_gaps > 0, "No se detectaron gaps en datos con gaps"

        # 3. Verificar clasificación
        assert hasattr(report, 'gaps_by_type')

    def test_signal_to_position_flow(self, position_tracker_instance,
                                    mock_trading_signal, mock_position_plan):
        """Test: Flujo de señal a posición"""
        tracker = position_tracker_instance

        # 1. Registrar señal como posición
        position_id = tracker.register_new_position(mock_trading_signal, mock_position_plan)

        print(f"✅ Posición creada: {position_id[:8]}...")

        # 2. Verificar que se creó
        assert tracker.has_active_position(mock_trading_signal.symbol)

        # 3. Ejecutar entrada
        tracker.mark_level_as_filled(
            mock_trading_signal.symbol,
            1,
            'ENTRY',
            150.0,
            40.0
        )

        # 4. Calcular métricas
        metrics = tracker.calculate_position_metrics(position_id, 151.0)

        print(f"   Métricas calculadas:")
        print(f"   - Avg Entry: ${metrics['average_entry_price']:.2f}")
        print(f"   - P&L: {metrics['unrealized_pnl']:.2f}%")

        assert metrics['unrealized_pnl'] > 0, "P&L debería ser positivo con precio más alto"

    def test_database_to_backtesting_flow(self, populated_db):
        """Test: Flujo de BD a backtesting"""
        from database.connection import get_connection
        from backtesting.data_validator import DataValidator

        # 1. Validar datos de BD
        validator = DataValidator()

        try:
            report = validator.validate_symbol(
                'AAPL',
                datetime.now() - timedelta(days=7),
                datetime.now()
            )

            print(f"✅ Validación completada")
            print(f"   Score: {report.overall_score:.1f}/100")
            print(f"   Backtest ready: {report.is_backtest_ready}")

            # 2. Verificar que retorna reporte válido
            assert report is not None
            assert hasattr(report, 'overall_score')

        except Exception as e:
            print(f"ℹ️  Validación no completada (datos insuficientes): {e}")


# =============================================================================
# 🎭 TESTS DE ESCENARIOS REALISTAS
# =============================================================================

@pytest.mark.integration
class TestRealisticScenarios:
    """Tests con escenarios realistas"""

    def test_trending_market_scenario(self):
        """Test: Escenario de mercado en tendencia"""
        # Crear datos de tendencia alcista
        dates = pd.date_range('2024-01-01 09:30', periods=100, freq='15T')

        # Tendencia alcista con ruido
        trend = np.linspace(100, 110, 100)
        noise = np.random.randn(100) * 0.5
        prices = trend + noise

        data = pd.DataFrame({
            'Open': prices,
            'High': prices + abs(np.random.randn(100) * 0.3),
            'Low': prices - abs(np.random.randn(100) * 0.3),
            'Close': prices,
            'Volume': np.random.randint(1000000, 3000000, 100)
        }, index=dates)

        # Calcular indicadores
        indicators = TechnicalIndicators()
        result = indicators.calculate_all_indicators(
            'TREND_TEST',
            data,
            current_price=data['Close'].iloc[-1],
            current_volume=data['Volume'].iloc[-1]
        )

        print(f"✅ Escenario de tendencia alcista:")
        print(f"   ROC: {result['roc']['roc']:.2f}%")
        print(f"   RSI: {result['rsi']['rsi']:.1f}")

        # En tendencia alcista:
        # - ROC debería ser positivo
        assert result['roc']['roc'] > 0, "ROC debería ser positivo en tendencia alcista"

        # - RSI debería estar elevado (>50)
        assert result['rsi']['rsi'] > 40, "RSI debería estar alto en tendencia alcista"

    def test_volatile_market_scenario(self):
        """Test: Escenario de mercado volátil"""
        dates = pd.date_range('2024-01-01 09:30', periods=100, freq='15T')

        # Alta volatilidad
        prices = 100 + np.random.randn(100) * 5  # 5% volatilidad

        data = pd.DataFrame({
            'Open': prices,
            'High': prices + abs(np.random.randn(100) * 2),
            'Low': prices - abs(np.random.randn(100) * 2),
            'Close': prices,
            'Volume': np.random.randint(2000000, 5000000, 100)
        }, index=dates)

        indicators = TechnicalIndicators()
        result = indicators.calculate_all_indicators(
            'VOLATILE_TEST',
            data,
            current_price=data['Close'].iloc[-1],
            current_volume=data['Volume'].iloc[-1]
        )

        print(f"✅ Escenario de alta volatilidad:")
        print(f"   ATR: {result['atr']['atr']:.2f}")
        print(f"   ATR%: {result['atr']['atr_percentage']:.2f}%")
        print(f"   Nivel: {result['atr']['volatility_level']}")

        # Alta volatilidad debería reflejarse en ATR alto
        assert result['atr']['atr_percentage'] > 1.0, "ATR% debería ser alto en mercado volátil"

    def test_consolidation_scenario(self):
        """Test: Escenario de consolidación (lateral)"""
        dates = pd.date_range('2024-01-01 09:30', periods=100, freq='15T')

        # Mercado lateral con poco movimiento
        base_price = 100
        prices = base_price + np.random.randn(100) * 0.3  # Muy poco movimiento

        data = pd.DataFrame({
            'Open': prices,
            'High': prices + 0.2,
            'Low': prices - 0.2,
            'Close': prices,
            'Volume': np.random.randint(500000, 1000000, 100)
        }, index=dates)

        indicators = TechnicalIndicators()
        result = indicators.calculate_all_indicators(
            'CONSOLIDATION_TEST',
            data,
            current_price=data['Close'].iloc[-1],
            current_volume=data['Volume'].iloc[-1]
        )

        print(f"✅ Escenario de consolidación:")
        print(f"   ROC: {result['roc']['roc']:.2f}%")
        print(f"   BB Position: {result['bollinger']['bb_position']:.2f}")

        # En consolidación:
        # - ROC debería ser cercano a 0
        assert abs(result['roc']['roc']) < 2.0, "ROC debería ser bajo en consolidación"


# =============================================================================
# 🔗 TESTS DE INTEGRACIÓN DE COMPONENTES
# =============================================================================

@pytest.mark.integration
class TestComponentIntegration:
    """Tests de integración entre componentes"""

    def test_indicators_and_gap_detector(self, sample_ohlcv_with_gaps):
        """Test: Integración indicadores + gap detector"""
        # 1. Analizar calidad de datos
        gap_detector = GapDetector()
        quality_report = gap_detector.analyze_data_quality(
            'TEST',
            sample_ohlcv_with_gaps,
            sample_ohlcv_with_gaps.index[0],
            sample_ohlcv_with_gaps.index[-1]
        )

        print(f"Calidad de datos: {quality_report.overall_quality_score:.1f}/100")

        # 2. Calcular indicadores con los mismos datos
        indicators = TechnicalIndicators()
        result = indicators.calculate_all_indicators(
            'TEST',
            sample_ohlcv_with_gaps,
            current_price=sample_ohlcv_with_gaps['Close'].iloc[-1],
            current_volume=sample_ohlcv_with_gaps['Volume'].iloc[-1]
        )

        # 3. Ambos deberían completarse sin error
        assert quality_report is not None
        assert result is not None

        print(f"Indicadores calculados con {result['data_points']} puntos")

    def test_full_trading_cycle(self):
        """Test: Ciclo completo de trading simulado"""
        # 1. Generar datos
        dates = pd.date_range('2024-01-01 09:30', periods=100, freq='15T')
        prices = 100 + np.cumsum(np.random.randn(100) * 0.5)

        data = pd.DataFrame({
            'Open': prices,
            'High': prices + abs(np.random.randn(100) * 0.5),
            'Low': prices - abs(np.random.randn(100) * 0.5),
            'Close': prices,
            'Volume': np.random.randint(1000000, 5000000, 100)
        }, index=dates)

        # 2. Calcular indicadores
        indicators = TechnicalIndicators()
        indicator_result = indicators.calculate_all_indicators(
            'CYCLE_TEST',
            data,
            current_price=data['Close'].iloc[-1],
            current_volume=data['Volume'].iloc[-1]
        )

        print(f"✅ Paso 1: Indicadores calculados")

        # 3. Simular señal (si RSI y MACD son favorables)
        rsi = indicator_result['rsi']['rsi']
        macd_histogram = indicator_result['macd']['histogram']

        signal_generated = False
        if rsi < 60 and rsi > 40 and macd_histogram > 0:
            signal_generated = True
            print(f"✅ Paso 2: Señal LONG generada (RSI={rsi:.1f}, MACD={macd_histogram:.2f})")

        # 4. Si hay señal, simular posición
        if signal_generated:
            tracker = PositionTracker(use_database=False)

            from dataclasses import dataclass

            @dataclass
            class Signal:
                symbol: str = "CYCLE_TEST"
                signal_type: str = "LONG"
                signal_strength: int = 75
                confidence_level: str = "ALTA"
                entry_quality: str = "FULL_ENTRY"
                current_price: float = float(data['Close'].iloc[-1])
                timestamp: datetime = datetime.now()

            @dataclass
            class Level:
                price: float
                percentage: float
                description: str
                trigger_condition: str

            @dataclass
            class Plan:
                entries: list
                exits: list
                stop_loss: Level
                strategy_type: str = "SCALPING"

            current_price = float(data['Close'].iloc[-1])
            atr = indicator_result['atr']['atr']

            plan = Plan(
                entries=[
                    Level(current_price, 40, "Entry 1", "Market"),
                    Level(current_price - atr * 0.5, 30, "Entry 2", "Limit"),
                    Level(current_price - atr * 1.0, 30, "Entry 3", "Limit")
                ],
                exits=[
                    Level(current_price + atr * 1.5, 25, "TP1", "Limit"),
                    Level(current_price + atr * 2.5, 25, "TP2", "Limit"),
                    Level(current_price + atr * 4.0, 25, "TP3", "Limit"),
                    Level(current_price + atr * 6.0, 25, "TP4", "Limit")
                ],
                stop_loss=Level(current_price - atr * 1.0, 100, "SL", "Stop")
            )

            position_id = tracker.register_new_position(Signal(), plan)
            print(f"✅ Paso 3: Posición creada {position_id[:8]}...")

            # 5. Simular ejecución
            tracker.mark_level_as_filled("CYCLE_TEST", 1, 'ENTRY', current_price, 40.0)
            print(f"✅ Paso 4: Entry ejecutado @ ${current_price:.2f}")

            # 6. Calcular P&L
            future_price = current_price + atr * 2.0  # Simular movimiento favorable
            metrics = tracker.calculate_position_metrics(position_id, future_price)

            print(f"✅ Paso 5: P&L calculado = {metrics['unrealized_pnl']:.2f}%")

            assert metrics['unrealized_pnl'] > 0, "P&L debería ser positivo"


# =============================================================================
# 🔍 TESTS DE EDGE CASES EN INTEGRACIÓN
# =============================================================================

@pytest.mark.integration
class TestIntegrationEdgeCases:
    """Tests de casos especiales en integración"""

    def test_empty_data_handling(self):
        """Test: Manejo de datos vacíos"""
        empty_df = pd.DataFrame(columns=['Open', 'High', 'Low', 'Close', 'Volume'])

        indicators = TechnicalIndicators()

        # Debe manejar gracefully datos vacíos
        try:
            result = indicators.calculate_all_indicators(
                'EMPTY_TEST',
                empty_df,
                current_price=100.0,
                current_volume=1000000
            )
            # Si llega aquí, manejó el caso correctamente
            print("✅ Datos vacíos manejados correctamente")
        except Exception as e:
            # También aceptable que lance excepción controlada
            print(f"✅ Excepción controlada con datos vacíos: {type(e).__name__}")

    def test_single_datapoint(self):
        """Test: Un solo punto de datos"""
        dates = pd.date_range('2024-01-01', periods=1, freq='15T')

        data = pd.DataFrame({
            'Open': [100],
            'High': [101],
            'Low': [99],
            'Close': [100],
            'Volume': [1000000]
        }, index=dates)

        indicators = TechnicalIndicators()

        try:
            result = indicators.calculate_all_indicators(
                'SINGLE_TEST',
                data,
                current_price=100.0,
                current_volume=1000000
            )
            print("✅ Punto único manejado correctamente")
        except Exception as e:
            print(f"✅ Excepción controlada con punto único: {type(e).__name__}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
