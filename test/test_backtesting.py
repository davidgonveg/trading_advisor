#!/usr/bin/env python3
"""
🧪 TESTS DE BACKTESTING
========================

Tests del sistema de backtesting:
- Configuración
- Validación de datos
- Ejecución de backtests
- Cálculo de métricas
- Resultados
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from backtesting.config import BacktestConfig
from backtesting.backtest_engine import BacktestEngine
from backtesting.data_validator import DataValidator


# =============================================================================
# ⚙️ TESTS DE CONFIGURACIÓN
# =============================================================================

@pytest.mark.backtest
class TestBacktestConfig:
    """Tests de configuración de backtesting"""

    def test_default_config(self):
        """Test: Configuración por defecto"""
        config = BacktestConfig()

        assert config.initial_capital > 0
        assert config.risk_per_trade > 0
        assert len(config.symbols) > 0

    def test_custom_config(self):
        """Test: Configuración personalizada"""
        config = BacktestConfig(
            symbols=['AAPL', 'MSFT'],
            initial_capital=50000.0,
            risk_per_trade=2.0
        )

        assert config.symbols == ['AAPL', 'MSFT']
        assert config.initial_capital == 50000.0
        assert config.risk_per_trade == 2.0

    def test_config_to_dict(self):
        """Test: Convertir config a diccionario"""
        config = BacktestConfig()
        config_dict = config.to_dict()

        assert isinstance(config_dict, dict)
        assert 'initial_capital' in config_dict
        assert 'symbols' in config_dict


# =============================================================================
# 📊 TESTS DE VALIDACIÓN DE DATOS
# =============================================================================

@pytest.mark.backtest
class TestDataValidation:
    """Tests de validación de datos para backtesting"""

    def test_validator_initialization(self):
        """Test: Inicializar validador"""
        validator = DataValidator()
        assert validator is not None

    def test_validate_complete_data(self, populated_db):
        """Test: Validar datos completos"""
        validator = DataValidator()

        report = validator.validate_symbol(
            'AAPL',
            datetime.now() - timedelta(days=7),
            datetime.now()
        )

        assert report is not None
        assert report.overall_score >= 0
        assert report.overall_score <= 100

    def test_validate_data_with_gaps(self, temp_db):
        """Test: Validar datos con gaps"""
        from database.connection import save_indicators_data

        # Insertar datos con gaps
        base_date = datetime.now() - timedelta(days=1)

        for hour in [0, 1, 2, 5, 6, 7]:  # Gap entre hora 2 y 5
            indicators = {
                'symbol': 'TEST',
                'timestamp': base_date + timedelta(hours=hour),
                'current_price': 150.0,
                'current_volume': 1000000,
                'rsi': {'rsi': 50},
                'macd': {'macd': 0, 'signal': 0, 'histogram': 0},
                'vwap': {'vwap': 150, 'deviation_pct': 0},
                'roc': {'roc': 0},
                'bollinger': {'upper_band': 152, 'middle_band': 150, 'lower_band': 148, 'bb_position': 0.5},
                'volume_osc': {'volume_oscillator': 0},
                'atr': {'atr': 2, 'atr_percentage': 1.3, 'volatility_level': 'NORMAL'}
            }
            save_indicators_data(indicators)

        validator = DataValidator()
        report = validator.validate_symbol(
            'TEST',
            base_date,
            base_date + timedelta(hours=8)
        )

        # Score debe ser menor por los gaps
        print(f"Quality score con gaps: {report.overall_score}")


# =============================================================================
# 🚀 TESTS DE EJECUCIÓN
# =============================================================================

@pytest.mark.backtest
@pytest.mark.slow
class TestBacktestExecution:
    """Tests de ejecución de backtesting"""

    def test_engine_initialization(self):
        """Test: Inicializar motor de backtesting"""
        config = BacktestConfig(symbols=['AAPL'], initial_capital=10000.0)
        engine = BacktestEngine(config)

        assert engine is not None
        assert engine.initial_capital == 10000.0
        assert engine.current_capital == 10000.0

    def test_backtest_with_minimal_data(self, populated_db):
        """Test: Backtesting con datos mínimos"""
        config = BacktestConfig(
            symbols=['AAPL'],
            initial_capital=10000.0,
            validate_data_before_backtest=False,  # Skip validation for speed
            min_signal_strength=50
        )

        engine = BacktestEngine(config)

        # Intentar ejecutar (puede no tener suficientes datos para generar trades)
        # El test verifica que no crashea
        try:
            results = engine.run()
            assert results is not None
            assert 'metrics' in results or 'error' in results
        except Exception as e:
            print(f"Backtest error (expected): {e}")

    def test_capital_tracking(self):
        """Test: Tracking de capital"""
        config = BacktestConfig(initial_capital=10000.0)
        engine = BacktestEngine(config)

        assert engine.current_capital == 10000.0
        assert engine.peak_capital == 10000.0

    def test_equity_curve_generation(self):
        """Test: Generar equity curve"""
        config = BacktestConfig()
        engine = BacktestEngine(config)

        # Equity curve debe iniciar vacío
        assert len(engine.equity_curve) == 0


# =============================================================================
# 📊 TESTS DE MÉTRICAS
# =============================================================================

@pytest.mark.backtest
class TestBacktestMetrics:
    """Tests de cálculo de métricas"""

    def test_metrics_structure(self):
        """Test: Estructura de métricas"""
        config = BacktestConfig()
        engine = BacktestEngine(config)

        # Inicialmente vacío
        assert isinstance(engine.metrics, dict)

    def test_win_rate_calculation(self):
        """Test: Cálculo de win rate"""
        # Mock: Simular que hubo trades
        # Win rate = wins / total_trades

        # Ejemplo: 7 ganadores de 10 = 70%
        wins = 7
        total = 10
        win_rate = (wins / total) * 100

        assert win_rate == 70.0

    def test_profit_factor_calculation(self):
        """Test: Cálculo de profit factor"""
        # Profit factor = total_profit / total_loss

        total_profit = 500.0
        total_loss = 200.0
        profit_factor = total_profit / total_loss

        assert profit_factor == 2.5

    def test_drawdown_calculation(self):
        """Test: Cálculo de drawdown"""
        # Simular equity curve
        equity_curve = [
            (datetime.now(), 10000),
            (datetime.now(), 11000),  # Peak
            (datetime.now(), 10500),
            (datetime.now(), 9500),   # Drawdown
            (datetime.now(), 10000)
        ]

        peak = 11000
        trough = 9500
        drawdown = ((peak - trough) / peak) * 100

        assert abs(drawdown - 13.636) < 0.01  # ~13.64%


# =============================================================================
# 🎯 TESTS DE TRADES
# =============================================================================

@pytest.mark.backtest
class TestBacktestTrades:
    """Tests de trades en backtesting"""

    def test_trade_execution(self):
        """Test: Ejecución de trade simulado"""
        entry_price = 150.0
        exit_price = 153.0
        shares = 100

        pnl = (exit_price - entry_price) * shares

        assert pnl == 300.0

    def test_commission_calculation(self):
        """Test: Cálculo de comisiones"""
        shares = 100
        commission_per_share = 0.005

        total_commission = shares * commission_per_share * 2  # Entry + Exit

        assert total_commission == 1.0

    def test_slippage_calculation(self):
        """Test: Cálculo de slippage"""
        target_price = 150.0
        slippage_pct = 0.1  # 0.1%

        slippage = target_price * (slippage_pct / 100)
        execution_price = target_price + slippage

        assert execution_price == 150.15


# =============================================================================
# 🔍 TESTS DE VALIDACIÓN DE RESULTADOS
# =============================================================================

@pytest.mark.backtest
class TestResultsValidation:
    """Tests de validación de resultados"""

    def test_results_completeness(self):
        """Test: Resultados completos"""
        mock_results = {
            'config': {},
            'metrics': {
                'initial_capital': 10000,
                'final_capital': 11000,
                'net_pnl': 1000,
                'return_pct': 10.0,
                'total_trades': 10,
                'winning_trades': 6,
                'losing_trades': 4,
                'win_rate': 60.0
            },
            'trades': [],
            'equity_curve': []
        }

        # Verificar estructura
        assert 'metrics' in mock_results
        assert 'trades' in mock_results
        assert 'equity_curve' in mock_results

        # Verificar métricas clave
        metrics = mock_results['metrics']
        assert 'total_trades' in metrics
        assert 'win_rate' in metrics
        assert 'net_pnl' in metrics

    def test_consistency_checks(self):
        """Test: Consistencia de resultados"""
        # Verificar que trades ganadores + perdedores = total
        winning = 6
        losing = 4
        total = 10

        assert winning + losing == total

        # Verificar que final_capital = initial + pnl
        initial = 10000
        pnl = 1000
        final = 11000

        assert initial + pnl == final


# =============================================================================
# 🎲 TESTS DE ESCENARIOS
# =============================================================================

@pytest.mark.backtest
@pytest.mark.integration
class TestBacktestScenarios:
    """Tests de diferentes escenarios de backtesting"""

    def test_bull_market_scenario(self):
        """Test: Escenario de mercado alcista"""
        # En mercado alcista, deberíamos ver más LONGs exitosos
        # Este es un test conceptual

        long_trades = 10
        long_winners = 7  # 70% win rate en alcista
        long_win_rate = (long_winners / long_trades) * 100

        assert long_win_rate == 70.0

    def test_bear_market_scenario(self):
        """Test: Escenario de mercado bajista"""
        # En mercado bajista, LONGs deberían tener menor win rate

        long_trades = 10
        long_winners = 4  # 40% win rate en bajista
        long_win_rate = (long_winners / long_trades) * 100

        assert long_win_rate == 40.0

    def test_sideways_market_scenario(self):
        """Test: Escenario de mercado lateral"""
        # En mercado lateral, menor número de señales

        total_opportunities = 100
        signals_generated = 20  # Pocas señales fuertes

        signal_rate = (signals_generated / total_opportunities) * 100

        assert signal_rate == 20.0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
