#!/usr/bin/env python3
"""
🧪 PYTEST CONFIGURATION & FIXTURES
===================================

Configuración global y fixtures compartidos para todos los tests.
"""

import pytest
import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
import sys
import os
import tempfile

# Añadir path del proyecto
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import config
from database.connection import get_connection, initialize_database
from indicators import TechnicalIndicators
from gap_detector import GapDetector
from position_manager.position_tracker import PositionTracker


# =============================================================================
# 🔧 CONFIGURACIÓN DE PYTEST
# =============================================================================

def pytest_configure(config):
    """Configuración global de pytest"""
    config.addinivalue_line("markers", "slow: marca tests lentos")
    config.addinivalue_line("markers", "integration: tests de integración")
    config.addinivalue_line("markers", "database: tests de base de datos")
    config.addinivalue_line("markers", "indicators: tests de indicadores")
    config.addinivalue_line("markers", "gaps: tests de gap filling")
    config.addinivalue_line("markers", "positions: tests de posiciones")
    config.addinivalue_line("markers", "backtest: tests de backtesting")


# =============================================================================
# 🗄️ FIXTURES DE BASE DE DATOS
# =============================================================================

@pytest.fixture(scope="function")
def temp_db():
    """
    Crear base de datos temporal para tests

    Returns:
        str: Path a la base de datos temporal
    """
    # Crear archivo temporal
    fd, temp_path = tempfile.mkstemp(suffix='.db')
    os.close(fd)

    # Guardar path original
    original_db = config.DB_PATH if hasattr(config, 'DB_PATH') else None

    # Usar temporal
    from database import connection
    original_path = connection.DB_PATH
    connection.DB_PATH = temp_path

    # Inicializar estructura
    initialize_database()

    yield temp_path

    # Cleanup
    connection.DB_PATH = original_path
    try:
        os.unlink(temp_path)
    except:
        pass


@pytest.fixture(scope="function")
def db_connection(temp_db):
    """
    Conexión a base de datos temporal

    Returns:
        sqlite3.Connection: Conexión activa
    """
    from database import connection
    conn = get_connection()
    yield conn
    if conn:
        conn.close()


@pytest.fixture(scope="function")
def populated_db(temp_db):
    """
    Base de datos con datos de prueba

    Returns:
        str: Path a la base de datos poblada
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Insertar datos de prueba
    symbols = ["AAPL", "MSFT", "GOOGL"]
    base_date = datetime.now() - timedelta(days=7)

    for i, symbol in enumerate(symbols):
        for day in range(7):
            for hour in range(10):
                timestamp = base_date + timedelta(days=day, hours=hour)

                # Datos OHLCV
                base_price = 150 + i * 50 + np.random.randn() * 5
                cursor.execute('''
                INSERT INTO indicators_data (
                    timestamp, symbol, open_price, high_price, low_price, close_price, volume,
                    rsi_value, macd_histogram, vwap_value, roc_value, atr_value
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    timestamp.isoformat(),
                    symbol,
                    base_price,
                    base_price + abs(np.random.randn() * 2),
                    base_price - abs(np.random.randn() * 2),
                    base_price + np.random.randn(),
                    int(1000000 + np.random.randn() * 500000),
                    50 + np.random.randn() * 15,
                    np.random.randn() * 0.5,
                    base_price,
                    np.random.randn() * 2,
                    base_price * 0.02
                ))

    conn.commit()
    conn.close()

    return temp_db


# =============================================================================
# 📊 FIXTURES DE DATOS
# =============================================================================

@pytest.fixture
def sample_ohlcv_data():
    """
    DataFrame de ejemplo con datos OHLCV

    Returns:
        pd.DataFrame: Datos OHLCV de prueba
    """
    dates = pd.date_range('2024-01-01 09:30', periods=100, freq='15T')

    # Generar precios realistas
    np.random.seed(42)
    close_prices = 100 + np.cumsum(np.random.randn(100) * 0.5)

    data = pd.DataFrame({
        'Open': close_prices + np.random.randn(100) * 0.3,
        'High': close_prices + abs(np.random.randn(100) * 0.5),
        'Low': close_prices - abs(np.random.randn(100) * 0.5),
        'Close': close_prices,
        'Volume': np.random.randint(1000000, 5000000, 100)
    }, index=dates)

    # Asegurar consistencia OHLC
    data['High'] = data[['Open', 'High', 'Low', 'Close']].max(axis=1)
    data['Low'] = data[['Open', 'High', 'Low', 'Close']].min(axis=1)

    return data


@pytest.fixture
def sample_ohlcv_with_gaps():
    """
    DataFrame con datos OHLCV que tiene gaps

    Returns:
        pd.DataFrame: Datos con gaps intencionados
    """
    dates = pd.date_range('2024-01-01 09:30', periods=150, freq='15T')

    np.random.seed(42)
    close_prices = 100 + np.cumsum(np.random.randn(150) * 0.5)

    data = pd.DataFrame({
        'Open': close_prices + np.random.randn(150) * 0.3,
        'High': close_prices + abs(np.random.randn(150) * 0.5),
        'Low': close_prices - abs(np.random.randn(150) * 0.5),
        'Close': close_prices,
        'Volume': np.random.randint(1000000, 5000000, 150)
    }, index=dates)

    # Asegurar consistencia OHLC
    data['High'] = data[['Open', 'High', 'Low', 'Close']].max(axis=1)
    data['Low'] = data[['Open', 'High', 'Low', 'Close']].min(axis=1)

    # Crear gaps eliminando datos
    # Gap 1: 2 horas (pequeño)
    gap1_start = 30
    gap1_end = 38
    data = data.drop(data.index[gap1_start:gap1_end])

    # Gap 2: 4 horas (mediano)
    gap2_start = 80
    gap2_end = 96
    data = data.drop(data.index[gap2_start:gap2_end])

    return data


@pytest.fixture
def sample_indicators_result():
    """
    Resultado de ejemplo de cálculo de indicadores

    Returns:
        Dict: Estructura de indicadores
    """
    return {
        'symbol': 'AAPL',
        'timestamp': datetime.now(),
        'current_price': 150.0,
        'open_price': 149.5,
        'high_price': 151.0,
        'low_price': 149.0,
        'close_price': 150.0,
        'current_volume': 5000000,
        'data_points': 100,
        'macd': {
            'macd': 0.5,
            'signal': 0.4,
            'histogram': 0.1,
            'signal_type': 'BULLISH',
            'signal_strength': 15
        },
        'rsi': {
            'rsi': 55.0,
            'signal_type': 'NEUTRAL',
            'signal_strength': 10
        },
        'vwap': {
            'vwap': 149.8,
            'deviation_pct': 0.13,
            'signal_type': 'NEAR_VWAP',
            'signal_strength': 15
        },
        'roc': {
            'roc': 1.8,
            'signal_type': 'BULLISH',
            'signal_strength': 15
        },
        'bollinger': {
            'upper_band': 152.0,
            'middle_band': 150.0,
            'lower_band': 148.0,
            'bb_position': 0.5,
            'signal_type': 'MIDDLE_BAND',
            'signal_strength': 5
        },
        'volume_osc': {
            'volume_oscillator': 60.0,
            'signal_type': 'HIGH_VOLUME',
            'signal_strength': 8
        },
        'atr': {
            'atr': 3.0,
            'atr_percentage': 2.0,
            'volatility_level': 'NORMAL'
        }
    }


# =============================================================================
# 🎯 FIXTURES DE TRADING
# =============================================================================

@pytest.fixture
def mock_trading_signal():
    """
    Señal de trading de ejemplo

    Returns:
        Mock object con atributos de señal
    """
    from dataclasses import dataclass

    @dataclass
    class MockSignal:
        symbol: str = "AAPL"
        signal_type: str = "LONG"
        signal_strength: int = 75
        confidence_level: str = "ALTA"
        entry_quality: str = "FULL_ENTRY"
        current_price: float = 150.0
        timestamp: datetime = datetime.now()

    return MockSignal()


@pytest.fixture
def mock_position_plan():
    """
    Plan de posición de ejemplo

    Returns:
        Mock object con plan de posición
    """
    from dataclasses import dataclass

    @dataclass
    class MockLevel:
        price: float
        percentage: float
        description: str
        trigger_condition: str

    @dataclass
    class MockPlan:
        entries: list
        exits: list
        stop_loss: MockLevel
        strategy_type: str = "SCALPING"
        entry_1_price: float = 150.0
        entry_2_price: float = 149.0
        entry_3_price: float = 148.0
        take_profit_1: float = 152.0
        take_profit_2: float = 154.0
        take_profit_3: float = 156.0
        take_profit_4: float = 158.0
        stop_loss_price: float = 147.0
        max_risk_reward: float = 3.0

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
        stop_loss=MockLevel(147.0, 100, "Stop Loss", "Price <= 147.0")
    )

    return plan


@pytest.fixture
def position_tracker_instance():
    """
    Instancia de PositionTracker sin base de datos

    Returns:
        PositionTracker: Instancia para testing
    """
    return PositionTracker(use_database=False)


# =============================================================================
# 🔧 FIXTURES DE COMPONENTES
# =============================================================================

@pytest.fixture
def indicators_instance():
    """
    Instancia de TechnicalIndicators

    Returns:
        TechnicalIndicators: Instancia para testing
    """
    return TechnicalIndicators()


@pytest.fixture
def gap_detector_instance():
    """
    Instancia de GapDetector

    Returns:
        GapDetector: Instancia para testing
    """
    return GapDetector()


# =============================================================================
# 🛠️ UTILIDADES PARA TESTS
# =============================================================================

@pytest.fixture
def assert_dataframe_valid():
    """
    Helper para validar DataFrames

    Returns:
        Callable: Función de validación
    """
    def validate(df, required_columns=None):
        """Validar que un DataFrame tiene la estructura esperada"""
        assert isinstance(df, pd.DataFrame), "No es un DataFrame"
        assert not df.empty, "DataFrame vacío"
        assert isinstance(df.index, pd.DatetimeIndex), "Índice no es DatetimeIndex"

        if required_columns:
            for col in required_columns:
                assert col in df.columns, f"Columna {col} no encontrada"

        # Validar consistencia OHLC si están presentes
        if all(col in df.columns for col in ['Open', 'High', 'Low', 'Close']):
            assert (df['High'] >= df['Low']).all(), "High < Low detectado"
            assert (df['High'] >= df['Open']).all(), "High < Open detectado"
            assert (df['High'] >= df['Close']).all(), "High < Close detectado"
            assert (df['Low'] <= df['Open']).all(), "Low > Open detectado"
            assert (df['Low'] <= df['Close']).all(), "Low > Close detectado"

        return True

    return validate


@pytest.fixture
def assert_no_gaps():
    """
    Helper para verificar que no hay gaps en datos

    Returns:
        Callable: Función de validación
    """
    def validate(df, expected_interval_minutes=15):
        """Validar que no hay gaps temporales en el DataFrame"""
        if len(df) < 2:
            return True

        time_diffs = df.index.to_series().diff()
        max_diff = time_diffs.max()
        expected_diff = timedelta(minutes=expected_interval_minutes)

        # Permitir un pequeño margen
        margin = timedelta(minutes=expected_interval_minutes * 0.1)
        assert max_diff <= expected_diff + margin, \
            f"Gap detectado: {max_diff} > esperado {expected_diff}"

        return True

    return validate


# =============================================================================
# 📝 MARKS Y SKIPPERS
# =============================================================================

@pytest.fixture
def skip_if_no_database():
    """Skip test si no hay base de datos disponible"""
    import pytest

    try:
        conn = get_connection()
        if conn:
            conn.close()
            return False
        else:
            pytest.skip("Base de datos no disponible")
    except:
        pytest.skip("Base de datos no disponible")


@pytest.fixture
def skip_if_slow(request):
    """Skip test si no se quieren ejecutar tests lentos"""
    if request.config.getoption("--fast-only", default=False):
        pytest.skip("Test lento omitido con --fast-only")


# =============================================================================
# 🧹 CLEANUP
# =============================================================================

@pytest.fixture(autouse=True, scope="function")
def cleanup_temp_files():
    """Limpiar archivos temporales después de cada test"""
    yield
    # Cleanup se ejecuta aquí después del test
    temp_dir = Path(tempfile.gettempdir())
    for temp_file in temp_dir.glob("trading_test_*.db"):
        try:
            temp_file.unlink()
        except:
            pass
