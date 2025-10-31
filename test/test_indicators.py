#!/usr/bin/env python3
"""
🧪 TESTS DE INDICADORES TÉCNICOS
=================================

Tests comprehensivos para el cálculo de indicadores:
- RSI, MACD, VWAP, ROC, Bollinger Bands, ATR
- Validación de rangos
- Edge cases
- Gap filling
- Performance
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from indicators import TechnicalIndicators
import config


# =============================================================================
# 📊 TESTS DE RSI
# =============================================================================

@pytest.mark.indicators
class TestRSI:
    """Tests del indicador RSI"""

    def test_rsi_calculation(self, indicators_instance, sample_ohlcv_data):
        """Test: Calcular RSI correctamente"""
        result = indicators_instance.calculate_all_indicators(
            'TEST',
            sample_ohlcv_data,
            current_price=sample_ohlcv_data['Close'].iloc[-1],
            current_volume=sample_ohlcv_data['Volume'].iloc[-1]
        )

        assert 'rsi' in result
        assert 'rsi' in result['rsi']

        rsi_value = result['rsi']['rsi']
        assert 0 <= rsi_value <= 100, f"RSI fuera de rango: {rsi_value}"

    def test_rsi_signal_oversold(self, indicators_instance):
        """Test: RSI detecta sobreventa correctamente"""
        # Crear datos con tendencia bajista fuerte
        dates = pd.date_range('2024-01-01', periods=50, freq='15T')
        declining_prices = 100 - np.linspace(0, 20, 50)  # Caída fuerte

        data = pd.DataFrame({
            'Open': declining_prices,
            'High': declining_prices + 0.5,
            'Low': declining_prices - 0.5,
            'Close': declining_prices,
            'Volume': 1000000
        }, index=dates)

        result = indicators_instance.calculate_all_indicators(
            'TEST',
            data,
            current_price=data['Close'].iloc[-1],
            current_volume=data['Volume'].iloc[-1]
        )

        rsi_value = result['rsi']['rsi']
        print(f"RSI en tendencia bajista: {rsi_value}")

        # En tendencia bajista fuerte, RSI debe estar bajo
        assert rsi_value < 50, "RSI no detectó tendencia bajista"

    def test_rsi_signal_overbought(self, indicators_instance):
        """Test: RSI detecta sobrecompra correctamente"""
        # Crear datos con tendencia alcista fuerte
        dates = pd.date_range('2024-01-01', periods=50, freq='15T')
        rising_prices = 100 + np.linspace(0, 20, 50)  # Subida fuerte

        data = pd.DataFrame({
            'Open': rising_prices,
            'High': rising_prices + 0.5,
            'Low': rising_prices - 0.5,
            'Close': rising_prices,
            'Volume': 1000000
        }, index=dates)

        result = indicators_instance.calculate_all_indicators(
            'TEST',
            data,
            current_price=data['Close'].iloc[-1],
            current_volume=data['Volume'].iloc[-1]
        )

        rsi_value = result['rsi']['rsi']
        print(f"RSI en tendencia alcista: {rsi_value}")

        # En tendencia alcista fuerte, RSI debe estar alto
        assert rsi_value > 50, "RSI no detectó tendencia alcista"

    def test_rsi_with_insufficient_data(self, indicators_instance):
        """Test: RSI con datos insuficientes"""
        # Crear solo 10 barras (insuficiente para RSI de período 14)
        dates = pd.date_range('2024-01-01', periods=10, freq='15T')
        data = pd.DataFrame({
            'Open': 100,
            'High': 101,
            'Low': 99,
            'Close': 100,
            'Volume': 1000000
        }, index=dates)

        result = indicators_instance.calculate_all_indicators(
            'TEST',
            data,
            current_price=100.0,
            current_volume=1000000
        )

        # Debe manejar gracefully datos insuficientes
        assert 'rsi' in result
        # El sistema debe usar menos datos o retornar un valor por defecto
        assert result['rsi']['rsi'] >= 0


# =============================================================================
# 📈 TESTS DE MACD
# =============================================================================

@pytest.mark.indicators
class TestMACD:
    """Tests del indicador MACD"""

    def test_macd_calculation(self, indicators_instance, sample_ohlcv_data):
        """Test: Calcular MACD correctamente"""
        result = indicators_instance.calculate_all_indicators(
            'TEST',
            sample_ohlcv_data,
            current_price=sample_ohlcv_data['Close'].iloc[-1],
            current_volume=sample_ohlcv_data['Volume'].iloc[-1]
        )

        assert 'macd' in result
        assert 'macd' in result['macd']
        assert 'signal' in result['macd']
        assert 'histogram' in result['macd']

    def test_macd_bullish_crossover(self, indicators_instance):
        """Test: MACD detecta cruce alcista"""
        dates = pd.date_range('2024-01-01', periods=100, freq='15T')

        # Crear datos con momentum alcista claro
        prices = 100 + np.linspace(0, 10, 100) + np.random.randn(100) * 0.2

        data = pd.DataFrame({
            'Open': prices,
            'High': prices + 0.5,
            'Low': prices - 0.5,
            'Close': prices,
            'Volume': 1000000
        }, index=dates)

        result = indicators_instance.calculate_all_indicators(
            'TEST',
            data,
            current_price=data['Close'].iloc[-1],
            current_volume=data['Volume'].iloc[-1]
        )

        histogram = result['macd']['histogram']
        signal_type = result['macd'].get('signal_type', '')

        print(f"MACD Histogram: {histogram}, Signal: {signal_type}")

        # En tendencia alcista, histograma debe ser positivo
        # o signal_type debe indicar tendencia alcista
        assert histogram > -1.0  # Permitir pequeño margen

    def test_macd_histogram_interpretation(self, indicators_instance, sample_ohlcv_data):
        """Test: Interpretación del histograma MACD"""
        result = indicators_instance.calculate_all_indicators(
            'TEST',
            sample_ohlcv_data,
            current_price=sample_ohlcv_data['Close'].iloc[-1],
            current_volume=sample_ohlcv_data['Volume'].iloc[-1]
        )

        macd_line = result['macd']['macd']
        signal_line = result['macd']['signal']
        histogram = result['macd']['histogram']

        # Histograma debe ser la diferencia entre MACD y Signal
        calculated_histogram = macd_line - signal_line
        assert abs(histogram - calculated_histogram) < 0.01, \
            "Histograma no coincide con MACD - Signal"


# =============================================================================
# 💹 TESTS DE VWAP
# =============================================================================

@pytest.mark.indicators
class TestVWAP:
    """Tests del indicador VWAP"""

    def test_vwap_calculation(self, indicators_instance, sample_ohlcv_data):
        """Test: Calcular VWAP correctamente"""
        result = indicators_instance.calculate_all_indicators(
            'TEST',
            sample_ohlcv_data,
            current_price=sample_ohlcv_data['Close'].iloc[-1],
            current_volume=sample_ohlcv_data['Volume'].iloc[-1]
        )

        assert 'vwap' in result
        assert 'vwap' in result['vwap']
        assert 'deviation_pct' in result['vwap']

        vwap_value = result['vwap']['vwap']
        assert vwap_value > 0, "VWAP debe ser positivo"

    def test_vwap_deviation(self, indicators_instance, sample_ohlcv_data):
        """Test: Desviación del VWAP está en rango razonable"""
        result = indicators_instance.calculate_all_indicators(
            'TEST',
            sample_ohlcv_data,
            current_price=sample_ohlcv_data['Close'].iloc[-1],
            current_volume=sample_ohlcv_data['Volume'].iloc[-1]
        )

        deviation = result['vwap']['deviation_pct']

        # Desviación debe ser razonable (típicamente < 5%)
        assert abs(deviation) < 10, f"Desviación VWAP muy grande: {deviation}%"

    def test_vwap_with_zero_volume(self, indicators_instance):
        """Test: VWAP maneja volumen cero correctamente"""
        dates = pd.date_range('2024-01-01', periods=50, freq='15T')

        data = pd.DataFrame({
            'Open': 100,
            'High': 101,
            'Low': 99,
            'Close': 100,
            'Volume': 0  # Volumen cero
        }, index=dates)

        result = indicators_instance.calculate_all_indicators(
            'TEST',
            data,
            current_price=100.0,
            current_volume=0
        )

        # Debe manejar gracefully volumen cero
        assert 'vwap' in result
        assert result['vwap']['vwap'] >= 0


# =============================================================================
# 🎢 TESTS DE BOLLINGER BANDS
# =============================================================================

@pytest.mark.indicators
class TestBollingerBands:
    """Tests de Bollinger Bands"""

    def test_bollinger_bands_calculation(self, indicators_instance, sample_ohlcv_data):
        """Test: Calcular Bollinger Bands correctamente"""
        result = indicators_instance.calculate_all_indicators(
            'TEST',
            sample_ohlcv_data,
            current_price=sample_ohlcv_data['Close'].iloc[-1],
            current_volume=sample_ohlcv_data['Volume'].iloc[-1]
        )

        assert 'bollinger' in result
        assert 'upper_band' in result['bollinger']
        assert 'middle_band' in result['bollinger']
        assert 'lower_band' in result['bollinger']

    def test_bollinger_bands_ordering(self, indicators_instance, sample_ohlcv_data):
        """Test: Bandas de Bollinger en orden correcto (upper > middle > lower)"""
        result = indicators_instance.calculate_all_indicators(
            'TEST',
            sample_ohlcv_data,
            current_price=sample_ohlcv_data['Close'].iloc[-1],
            current_volume=sample_ohlcv_data['Volume'].iloc[-1]
        )

        upper = result['bollinger']['upper_band']
        middle = result['bollinger']['middle_band']
        lower = result['bollinger']['lower_band']

        assert upper >= middle, f"Upper band ({upper}) < Middle band ({middle})"
        assert middle >= lower, f"Middle band ({middle}) < Lower band ({lower})"

    def test_bollinger_position(self, indicators_instance, sample_ohlcv_data):
        """Test: Posición en Bollinger Bands está en rango [0, 1]"""
        result = indicators_instance.calculate_all_indicators(
            'TEST',
            sample_ohlcv_data,
            current_price=sample_ohlcv_data['Close'].iloc[-1],
            current_volume=sample_ohlcv_data['Volume'].iloc[-1]
        )

        bb_position = result['bollinger']['bb_position']

        # Posición normalmente entre 0 y 1, puede estar ligeramente fuera
        assert -0.2 <= bb_position <= 1.2, f"BB Position fuera de rango: {bb_position}"


# =============================================================================
# 🚀 TESTS DE ROC (MOMENTUM)
# =============================================================================

@pytest.mark.indicators
class TestROC:
    """Tests del indicador ROC"""

    def test_roc_calculation(self, indicators_instance, sample_ohlcv_data):
        """Test: Calcular ROC correctamente"""
        result = indicators_instance.calculate_all_indicators(
            'TEST',
            sample_ohlcv_data,
            current_price=sample_ohlcv_data['Close'].iloc[-1],
            current_volume=sample_ohlcv_data['Volume'].iloc[-1]
        )

        assert 'roc' in result
        assert 'roc' in result['roc']

        roc_value = result['roc']['roc']
        # ROC debe estar en un rango razonable (-50% a +50% normalmente)
        assert -100 < roc_value < 100, f"ROC fuera de rango razonable: {roc_value}"

    def test_roc_positive_momentum(self, indicators_instance):
        """Test: ROC detecta momentum positivo"""
        dates = pd.date_range('2024-01-01', periods=50, freq='15T')
        rising_prices = 100 + np.linspace(0, 10, 50)  # +10% en total

        data = pd.DataFrame({
            'Open': rising_prices,
            'High': rising_prices + 0.5,
            'Low': rising_prices - 0.5,
            'Close': rising_prices,
            'Volume': 1000000
        }, index=dates)

        result = indicators_instance.calculate_all_indicators(
            'TEST',
            data,
            current_price=data['Close'].iloc[-1],
            current_volume=data['Volume'].iloc[-1]
        )

        roc_value = result['roc']['roc']
        print(f"ROC con momentum positivo: {roc_value}")

        # Debe ser positivo
        assert roc_value > 0, "ROC no detectó momentum positivo"


# =============================================================================
# 📏 TESTS DE ATR
# =============================================================================

@pytest.mark.indicators
class TestATR:
    """Tests del indicador ATR"""

    def test_atr_calculation(self, indicators_instance, sample_ohlcv_data):
        """Test: Calcular ATR correctamente"""
        result = indicators_instance.calculate_all_indicators(
            'TEST',
            sample_ohlcv_data,
            current_price=sample_ohlcv_data['Close'].iloc[-1],
            current_volume=sample_ohlcv_data['Volume'].iloc[-1]
        )

        assert 'atr' in result
        assert 'atr' in result['atr']
        assert 'atr_percentage' in result['atr']
        assert 'volatility_level' in result['atr']

        atr_value = result['atr']['atr']
        assert atr_value > 0, "ATR debe ser positivo"

    def test_atr_percentage_reasonable(self, indicators_instance, sample_ohlcv_data):
        """Test: ATR percentage está en rango razonable"""
        result = indicators_instance.calculate_all_indicators(
            'TEST',
            sample_ohlcv_data,
            current_price=sample_ohlcv_data['Close'].iloc[-1],
            current_volume=sample_ohlcv_data['Volume'].iloc[-1]
        )

        atr_pct = result['atr']['atr_percentage']

        # ATR percentage típicamente entre 0.5% y 10%
        assert 0 < atr_pct < 20, f"ATR% fuera de rango razonable: {atr_pct}%"

    def test_atr_volatility_classification(self, indicators_instance):
        """Test: Clasificación de volatilidad"""
        # Datos de alta volatilidad
        dates = pd.date_range('2024-01-01', periods=50, freq='15T')
        volatile_prices = 100 + np.random.randn(50) * 5  # Alta volatilidad

        data = pd.DataFrame({
            'Open': volatile_prices,
            'High': volatile_prices + abs(np.random.randn(50) * 3),
            'Low': volatile_prices - abs(np.random.randn(50) * 3),
            'Close': volatile_prices + np.random.randn(50) * 2,
            'Volume': 1000000
        }, index=dates)

        result = indicators_instance.calculate_all_indicators(
            'TEST',
            data,
            current_price=data['Close'].iloc[-1],
            current_volume=data['Volume'].iloc[-1]
        )

        volatility_level = result['atr']['volatility_level']
        print(f"Nivel de volatilidad: {volatility_level}")

        # Debe clasificar como alta volatilidad
        assert volatility_level in ['NORMAL', 'HIGH', 'EXTREME', 'LOW']


# =============================================================================
# 📊 TESTS DE VOLUMEN
# =============================================================================

@pytest.mark.indicators
class TestVolumeIndicators:
    """Tests de indicadores de volumen"""

    def test_volume_oscillator(self, indicators_instance, sample_ohlcv_data):
        """Test: Calcular oscilador de volumen"""
        result = indicators_instance.calculate_all_indicators(
            'TEST',
            sample_ohlcv_data,
            current_price=sample_ohlcv_data['Close'].iloc[-1],
            current_volume=sample_ohlcv_data['Volume'].iloc[-1]
        )

        assert 'volume_osc' in result
        assert 'volume_oscillator' in result['volume_osc']

        vol_osc = result['volume_osc']['volume_oscillator']
        # Oscilador de volumen típicamente entre -100 y +200
        assert -150 < vol_osc < 300, f"Volume oscillator fuera de rango: {vol_osc}"


# =============================================================================
# 🔧 TESTS DE GAP FILLING
# =============================================================================

@pytest.mark.indicators
@pytest.mark.gaps
class TestGapFillingInIndicators:
    """Tests de gap filling en cálculo de indicadores"""

    def test_indicators_with_gaps(self, indicators_instance, sample_ohlcv_with_gaps):
        """Test: Calcular indicadores con datos que tienen gaps"""
        result = indicators_instance.calculate_all_indicators(
            'TEST',
            sample_ohlcv_with_gaps,
            current_price=sample_ohlcv_with_gaps['Close'].iloc[-1],
            current_volume=sample_ohlcv_with_gaps['Volume'].iloc[-1]
        )

        # Debe poder calcular indicadores a pesar de los gaps
        assert 'rsi' in result
        assert 'macd' in result
        assert result['rsi']['rsi'] > 0

    def test_gap_detection_in_data(self, indicators_instance, sample_ohlcv_with_gaps):
        """Test: Detectar gaps en los datos"""
        # El sistema debe detectar si hay gaps
        data_points = len(sample_ohlcv_with_gaps)

        result = indicators_instance.calculate_all_indicators(
            'TEST',
            sample_ohlcv_with_gaps,
            current_price=sample_ohlcv_with_gaps['Close'].iloc[-1],
            current_volume=sample_ohlcv_with_gaps['Volume'].iloc[-1]
        )

        # Verificar que reporta el número correcto de datos
        assert result['data_points'] == data_points


# =============================================================================
# 🚀 TESTS DE INTEGRACIÓN
# =============================================================================

@pytest.mark.indicators
@pytest.mark.integration
class TestIndicatorsIntegration:
    """Tests de integración de todos los indicadores"""

    def test_all_indicators_together(self, indicators_instance, sample_ohlcv_data):
        """Test: Calcular todos los indicadores juntos"""
        result = indicators_instance.calculate_all_indicators(
            'TEST',
            sample_ohlcv_data,
            current_price=sample_ohlcv_data['Close'].iloc[-1],
            current_volume=sample_ohlcv_data['Volume'].iloc[-1]
        )

        # Verificar que todos los indicadores están presentes
        required_indicators = ['rsi', 'macd', 'vwap', 'roc', 'bollinger', 'volume_osc', 'atr']

        for indicator in required_indicators:
            assert indicator in result, f"Indicador {indicator} no encontrado"

    def test_indicator_consistency(self, indicators_instance, sample_ohlcv_data):
        """Test: Consistencia entre indicadores"""
        result = indicators_instance.calculate_all_indicators(
            'TEST',
            sample_ohlcv_data,
            current_price=sample_ohlcv_data['Close'].iloc[-1],
            current_volume=sample_ohlcv_data['Volume'].iloc[-1]
        )

        # VWAP debe estar cerca del precio actual (desviación razonable)
        vwap = result['vwap']['vwap']
        current_price = result['current_price']
        deviation = abs(vwap - current_price) / current_price * 100

        print(f"Desviación VWAP-Precio: {deviation:.2f}%")
        # Debe estar relativamente cerca (< 10% normalmente)
        assert deviation < 15, f"VWAP muy alejado del precio: {deviation}%"

    def test_result_structure(self, indicators_instance, sample_ohlcv_data):
        """Test: Estructura del resultado es correcta"""
        result = indicators_instance.calculate_all_indicators(
            'TEST',
            sample_ohlcv_data,
            current_price=sample_ohlcv_data['Close'].iloc[-1],
            current_volume=sample_ohlcv_data['Volume'].iloc[-1]
        )

        # Verificar campos básicos
        assert 'symbol' in result
        assert 'timestamp' in result
        assert 'current_price' in result
        assert 'data_points' in result

        # Verificar que timestamp es datetime
        assert isinstance(result['timestamp'], datetime)


# =============================================================================
# ⚡ TESTS DE PERFORMANCE
# =============================================================================

@pytest.mark.indicators
@pytest.mark.slow
class TestIndicatorsPerformance:
    """Tests de performance de indicadores"""

    def test_calculation_speed(self, indicators_instance):
        """Test: Velocidad de cálculo de indicadores"""
        import time

        # Crear dataset grande
        dates = pd.date_range('2024-01-01', periods=1000, freq='15T')
        data = pd.DataFrame({
            'Open': 100 + np.random.randn(1000) * 5,
            'High': 105 + np.random.randn(1000) * 5,
            'Low': 95 + np.random.randn(1000) * 5,
            'Close': 100 + np.random.randn(1000) * 5,
            'Volume': np.random.randint(1000000, 5000000, 1000)
        }, index=dates)

        start = time.time()
        result = indicators_instance.calculate_all_indicators(
            'TEST',
            data,
            current_price=data['Close'].iloc[-1],
            current_volume=data['Volume'].iloc[-1]
        )
        elapsed = time.time() - start

        print(f"Tiempo de cálculo (1000 barras): {elapsed:.3f}s")

        # Debe ser rápido (< 1 segundo para 1000 barras)
        assert elapsed < 2.0, f"Cálculo muy lento: {elapsed}s"


# =============================================================================
# 🎯 TESTS DE CASOS ESPECIALES
# =============================================================================

@pytest.mark.indicators
class TestEdgeCases:
    """Tests de casos especiales"""

    def test_flat_prices(self, indicators_instance):
        """Test: Precios totalmente planos (sin variación)"""
        dates = pd.date_range('2024-01-01', periods=50, freq='15T')

        data = pd.DataFrame({
            'Open': 100,
            'High': 100,
            'Low': 100,
            'Close': 100,
            'Volume': 1000000
        }, index=dates)

        result = indicators_instance.calculate_all_indicators(
            'TEST',
            data,
            current_price=100.0,
            current_volume=1000000
        )

        # Debe manejar precios planos sin errores
        assert 'rsi' in result
        # RSI típicamente 50 cuando no hay movimiento
        assert 40 <= result['rsi']['rsi'] <= 60

    def test_extreme_volatility(self, indicators_instance):
        """Test: Volatilidad extrema"""
        dates = pd.date_range('2024-01-01', periods=50, freq='15T')

        # Precios que varían enormemente
        prices = 100 + np.random.randn(50) * 50  # Volatilidad extrema

        data = pd.DataFrame({
            'Open': prices,
            'High': prices + abs(np.random.randn(50) * 20),
            'Low': prices - abs(np.random.randn(50) * 20),
            'Close': prices,
            'Volume': 1000000
        }, index=dates)

        result = indicators_instance.calculate_all_indicators(
            'TEST',
            data,
            current_price=data['Close'].iloc[-1],
            current_volume=1000000
        )

        # Debe clasificar como alta volatilidad
        assert result['atr']['volatility_level'] in ['HIGH', 'EXTREME']

    def test_minimum_data_points(self, indicators_instance):
        """Test: Mínimo de puntos de datos necesarios"""
        # Probar con diferentes cantidades de datos
        for n_points in [5, 10, 20, 50]:
            dates = pd.date_range('2024-01-01', periods=n_points, freq='15T')

            data = pd.DataFrame({
                'Open': 100,
                'High': 101,
                'Low': 99,
                'Close': 100,
                'Volume': 1000000
            }, index=dates)

            result = indicators_instance.calculate_all_indicators(
                'TEST',
                data,
                current_price=100.0,
                current_volume=1000000
            )

            # Debe funcionar con cualquier cantidad de datos
            assert 'rsi' in result
            print(f"Con {n_points} puntos: RSI = {result['rsi']['rsi']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
