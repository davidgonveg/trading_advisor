#!/usr/bin/env python3
"""
💼 POSITION REPLICATOR - Wrapper del Position Calculator Real
===========================================================

Adapta el PositionCalculatorV3 real para usarlo en backtesting.
Garantiza cálculo IDÉNTICO de entradas, TPs y SL.
"""

import logging
import pandas as pd
from datetime import datetime
from typing import Dict, List, Optional
import sys
from pathlib import Path

# Añadir path del proyecto
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from position_calculator import PositionCalculatorV3, PositionPlan
from scanner import TradingSignal
import config

logger = logging.getLogger(__name__)


class PositionReplicator:
    """
    Replica el cálculo de posiciones usando el position calculator real.
    """

    def __init__(self, capital: float = 10000.0, risk_per_trade: float = 1.5):
        """
        Inicializar replicador.

        Args:
            capital: Capital disponible
            risk_per_trade: % de capital a arriesgar por trade
        """
        self.position_calculator = PositionCalculatorV3()
        self.capital = capital
        self.risk_per_trade = risk_per_trade

        logger.info(f"💼 PositionReplicator inicializado con calculator REAL")
        logger.info(f"   Capital: ${capital:,.2f}, Risk: {risk_per_trade}%")

    def calculate_position(
        self,
        signal: TradingSignal,
        available_capital: float
    ) -> Optional[PositionPlan]:
        """
        Calcular plan de posición usando el calculator real.

        Args:
            signal: Señal de trading generada
            available_capital: Capital disponible actual

        Returns:
            PositionPlan con todos los niveles calculados
        """
        try:
            # Usar el position calculator real
            # Este método ya existe en position_calculator.py
            position_plan = self.position_calculator.calculate_position(
                signal=signal,
                capital=available_capital
            )

            if position_plan:
                logger.debug(
                    f"💼 Position calculada: {signal.symbol} "
                    f"Entry=${position_plan.entry_1_price:.2f} "
                    f"SL=${position_plan.stop_loss:.2f} "
                    f"TP4=${position_plan.take_profit_4:.2f}"
                )

            return position_plan

        except Exception as e:
            logger.error(f"❌ Error calculando position para {signal.symbol}: {e}")
            return None

    def recalculate_with_new_capital(
        self,
        signal: TradingSignal,
        new_capital: float
    ) -> Optional[PositionPlan]:
        """
        Recalcular position con nuevo capital (útil durante backtest).

        Args:
            signal: Señal original
            new_capital: Nuevo capital disponible

        Returns:
            Nuevo PositionPlan
        """
        return self.calculate_position(signal, new_capital)

    def adjust_position_size(
        self,
        position_plan: PositionPlan,
        adjustment_factor: float
    ) -> PositionPlan:
        """
        Ajustar tamaño de posición por un factor (ej. para posiciones parciales).

        Args:
            position_plan: Plan original
            adjustment_factor: Factor de ajuste (0.5 = 50%, etc.)

        Returns:
            Nuevo PositionPlan ajustado
        """
        try:
            # Crear copia del plan
            adjusted_plan = PositionPlan(
                # Basic info
                symbol=position_plan.symbol,
                direction=position_plan.direction,
                signal_strength=position_plan.signal_strength,

                # Entry levels (precios no cambian, solo cantidades)
                entry_1_price=position_plan.entry_1_price,
                entry_1_quantity=int(position_plan.entry_1_quantity * adjustment_factor),
                entry_2_price=position_plan.entry_2_price,
                entry_2_quantity=int(position_plan.entry_2_quantity * adjustment_factor),
                entry_3_price=position_plan.entry_3_price,
                entry_3_quantity=int(position_plan.entry_3_quantity * adjustment_factor),

                # Total position
                total_position_size=int(position_plan.total_position_size * adjustment_factor),
                max_capital_at_risk=position_plan.max_capital_at_risk * adjustment_factor,

                # Stop loss
                stop_loss=position_plan.stop_loss,
                stop_loss_percentage=position_plan.stop_loss_percentage,

                # Take profits (precios no cambian)
                take_profit_1=position_plan.take_profit_1,
                take_profit_2=position_plan.take_profit_2,
                take_profit_3=position_plan.take_profit_3,
                take_profit_4=position_plan.take_profit_4,

                # Otros
                atr=position_plan.atr,
                strategy_type=position_plan.strategy_type,
                max_risk_reward=position_plan.max_risk_reward,
                expected_hold_time=position_plan.expected_hold_time,
                notes=position_plan.notes,
            )

            return adjusted_plan

        except Exception as e:
            logger.error(f"❌ Error ajustando position: {e}")
            return position_plan


if __name__ == "__main__":
    # Test del replicador
    logging.basicConfig(level=logging.INFO)

    print("💼 POSITION REPLICATOR - TEST")
    print("=" * 70)

    # Crear señal de prueba
    from scanner import TradingSignal

    test_signal = TradingSignal(
        symbol="AAPL",
        timestamp=datetime.now(),
        signal_type="LONG",
        signal_strength=75,
        confidence_level="HIGH",
        current_price=150.0,
        entry_quality="FULL_ENTRY",
        indicator_scores={
            'MACD': 20,
            'RSI': 18,
            'VWAP': 15,
            'ROC': 20,
            'BOLLINGER': 15,
            'VOLUME': 10
        },
        indicator_signals={
            'MACD': 'BULLISH_CROSS',
            'RSI': 'OVERSOLD',
            'VWAP': 'AT_VWAP',
            'ROC': 'STRONG_MOMENTUM',
            'BOLLINGER': 'LOWER_BAND',
            'VOLUME': 'HIGH'
        }
    )

    # Test position calculator
    replicator = PositionReplicator(capital=10000.0, risk_per_trade=1.5)
    position_plan = replicator.calculate_position(test_signal, 10000.0)

    if position_plan:
        print(f"\n✅ Position calculada:")
        print(f"   Symbol: {position_plan.symbol}")
        print(f"   Direction: {position_plan.direction}")
        print(f"   Entry 1: ${position_plan.entry_1_price:.2f} x {position_plan.entry_1_quantity}")
        print(f"   Entry 2: ${position_plan.entry_2_price:.2f} x {position_plan.entry_2_quantity}")
        print(f"   Entry 3: ${position_plan.entry_3_price:.2f} x {position_plan.entry_3_quantity}")
        print(f"   Stop Loss: ${position_plan.stop_loss:.2f}")
        print(f"   TP1: ${position_plan.take_profit_1:.2f}")
        print(f"   TP2: ${position_plan.take_profit_2:.2f}")
        print(f"   TP3: ${position_plan.take_profit_3:.2f}")
        print(f"   TP4: ${position_plan.take_profit_4:.2f}")
        print(f"   Total size: {position_plan.total_position_size} shares")
        print(f"   Max risk: ${position_plan.max_capital_at_risk:.2f}")
        print(f"   Max R:R: {position_plan.max_risk_reward:.1f}R")
    else:
        print("❌ No se pudo calcular position")
