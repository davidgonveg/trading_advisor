#!/usr/bin/env python3
"""
🚪 EXIT REPLICATOR - Wrapper del Exit Manager Real (Adaptado para Backtesting)
============================================================================

Replica el comportamiento del Exit Manager pero adaptado para backtesting.
Evalúa deterioro técnico usando indicadores históricos.
"""

import logging
import pandas as pd
from datetime import datetime
from typing import Dict, Optional, Tuple
import sys
from pathlib import Path

# Añadir path del proyecto
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from exit_manager import ExitUrgency
from scanner import TradingSignal
import config

logger = logging.getLogger(__name__)


class ExitReplicator:
    """
    Replica evaluación de exit manager para backtesting.

    En backtesting, no usamos directamente el ExitManager porque necesita
    tracking de posiciones activas. En su lugar, evaluamos deterioro técnico
    punto por punto usando la misma lógica.
    """

    def __init__(self):
        """Inicializar replicador"""
        # Umbrales de deterioro (mismos que ExitManager)
        self.deterioration_thresholds = {
            'MILD': 60,      # 60-69: Deterioro leve
            'MODERATE': 70,  # 70-79: Deterioro moderado
            'SEVERE': 80,    # 80-89: Deterioro severo
            'CRITICAL': 90   # 90+: Deterioro crítico
        }

        logger.info("🚪 ExitReplicator inicializado")

    def evaluate_exit_conditions(
        self,
        original_signal: TradingSignal,
        current_row: pd.Series,
        entry_price: float,
        current_price: float,
        bars_held: int
    ) -> Tuple[bool, ExitUrgency, float, str]:
        """
        Evaluar condiciones de salida anticipada por deterioro técnico.

        Args:
            original_signal: Señal original de entrada
            current_row: Fila actual con indicadores
            entry_price: Precio de entrada
            current_price: Precio actual
            bars_held: Barras mantenidas en posición

        Returns:
            Tupla (should_exit, urgency, deterioration_score, reason)
        """
        try:
            # Construir indicadores actuales
            current_indicators = self._build_current_indicators(current_row)

            # Evaluar deterioro según dirección
            if original_signal.signal_type == "LONG":
                exit_score, reasons = self._evaluate_long_deterioration(
                    current_indicators,
                    original_signal,
                    entry_price,
                    current_price
                )
            elif original_signal.signal_type == "SHORT":
                exit_score, reasons = self._evaluate_short_deterioration(
                    current_indicators,
                    original_signal,
                    entry_price,
                    current_price
                )
            else:
                return False, ExitUrgency.NO_EXIT, 0.0, ""

            # Determinar urgencia
            urgency = self._determine_urgency(exit_score)

            # Decidir si salir
            should_exit = urgency in [ExitUrgency.EXIT_URGENT, ExitUrgency.EXIT_RECOMMENDED]

            # Si han pasado muchas barras sin progreso, considerar salida
            if bars_held > 100 and urgency == ExitUrgency.EXIT_WATCH:
                should_exit = True
                urgency = ExitUrgency.EXIT_RECOMMENDED
                reasons.append("Tiempo máximo en posición excedido")

            reason_str = " | ".join(reasons)

            if should_exit:
                logger.debug(
                    f"🚨 Exit recomendado: {original_signal.symbol} "
                    f"({urgency.value}, score={exit_score:.1f}) - {reason_str}"
                )

            return should_exit, urgency, exit_score, reason_str

        except Exception as e:
            logger.error(f"❌ Error evaluando exit conditions: {e}")
            return False, ExitUrgency.NO_EXIT, 0.0, ""

    def _build_current_indicators(self, row: pd.Series) -> Dict:
        """Construir dict de indicadores desde la fila actual"""
        return {
            'rsi': row.get('rsi_value', 50),
            'macd_histogram': row.get('macd_histogram', 0),
            'roc': row.get('roc_value', 0),
            'bb_position': row.get('bb_position', 0.5),
            'volume_osc': row.get('volume_oscillator', 0),
            'atr_pct': row.get('atr_percentage', 2.0),
        }

    def _evaluate_long_deterioration(
        self,
        indicators: Dict,
        original_signal: TradingSignal,
        entry_price: float,
        current_price: float
    ) -> Tuple[float, list]:
        """
        Evaluar deterioro en posición LONG.

        Busca señales de:
        - Momentum bajista fuerte
        - RSI en sobrecompra extrema
        - Divergencias negativas
        - Volumen vendedor
        """
        deterioration_score = 0.0
        reasons = []

        # 1. RSI en sobrecompra extrema (malo para long)
        rsi = indicators.get('rsi', 50)
        if rsi > 80:
            deterioration_score += 25
            reasons.append(f"RSI sobrecomprado extremo ({rsi:.0f})")
        elif rsi > 75:
            deterioration_score += 15
            reasons.append(f"RSI sobrecomprado ({rsi:.0f})")

        # 2. MACD histogram negativo (momentum bajista)
        macd_hist = indicators.get('macd_histogram', 0)
        if macd_hist < -0.05:
            deterioration_score += 25
            reasons.append("MACD histogram muy negativo")
        elif macd_hist < 0:
            deterioration_score += 10
            reasons.append("MACD histogram negativo")

        # 3. ROC negativo fuerte (momentum bajista)
        roc = indicators.get('roc', 0)
        if roc < -3.0:
            deterioration_score += 25
            reasons.append(f"ROC muy negativo ({roc:.1f}%)")
        elif roc < -1.5:
            deterioration_score += 15
            reasons.append(f"ROC negativo ({roc:.1f}%)")

        # 4. Bollinger Band position alta (podría revertir)
        bb_pos = indicators.get('bb_position', 0.5)
        if bb_pos > 0.95:
            deterioration_score += 15
            reasons.append("Precio en banda superior extrema")

        # 5. Volume oscillator negativo (volumen vendedor)
        vol_osc = indicators.get('volume_osc', 0)
        if vol_osc < -50:
            deterioration_score += 15
            reasons.append("Volumen vendedor fuerte")

        # 6. Precio cayendo respecto a entrada (drawdown)
        if current_price < entry_price:
            pct_down = ((entry_price - current_price) / entry_price) * 100
            if pct_down > 3.0:
                deterioration_score += 20
                reasons.append(f"Drawdown {pct_down:.1f}% desde entrada")
            elif pct_down > 1.5:
                deterioration_score += 10
                reasons.append(f"Drawdown {pct_down:.1f}%")

        return deterioration_score, reasons

    def _evaluate_short_deterioration(
        self,
        indicators: Dict,
        original_signal: TradingSignal,
        entry_price: float,
        current_price: float
    ) -> Tuple[float, list]:
        """
        Evaluar deterioro en posición SHORT.

        Busca señales de:
        - Momentum alcista fuerte
        - RSI en sobreventa extrema
        - Divergencias positivas
        - Volumen comprador
        """
        deterioration_score = 0.0
        reasons = []

        # 1. RSI en sobreventa extrema (malo para short)
        rsi = indicators.get('rsi', 50)
        if rsi < 20:
            deterioration_score += 25
            reasons.append(f"RSI sobrevendido extremo ({rsi:.0f})")
        elif rsi < 25:
            deterioration_score += 15
            reasons.append(f"RSI sobrevendido ({rsi:.0f})")

        # 2. MACD histogram positivo (momentum alcista)
        macd_hist = indicators.get('macd_histogram', 0)
        if macd_hist > 0.05:
            deterioration_score += 25
            reasons.append("MACD histogram muy positivo")
        elif macd_hist > 0:
            deterioration_score += 10
            reasons.append("MACD histogram positivo")

        # 3. ROC positivo fuerte (momentum alcista)
        roc = indicators.get('roc', 0)
        if roc > 3.0:
            deterioration_score += 25
            reasons.append(f"ROC muy positivo ({roc:.1f}%)")
        elif roc > 1.5:
            deterioration_score += 15
            reasons.append(f"ROC positivo ({roc:.1f}%)")

        # 4. Bollinger Band position baja (podría rebotar)
        bb_pos = indicators.get('bb_position', 0.5)
        if bb_pos < 0.05:
            deterioration_score += 15
            reasons.append("Precio en banda inferior extrema")

        # 5. Volume oscillator positivo (volumen comprador)
        vol_osc = indicators.get('volume_osc', 0)
        if vol_osc > 50:
            deterioration_score += 15
            reasons.append("Volumen comprador fuerte")

        # 6. Precio subiendo respecto a entrada (drawdown en short)
        if current_price > entry_price:
            pct_up = ((current_price - entry_price) / entry_price) * 100
            if pct_up > 3.0:
                deterioration_score += 20
                reasons.append(f"Drawdown {pct_up:.1f}% desde entrada")
            elif pct_up > 1.5:
                deterioration_score += 10
                reasons.append(f"Drawdown {pct_up:.1f}%")

        return deterioration_score, reasons

    def _determine_urgency(self, exit_score: float) -> ExitUrgency:
        """Determinar urgencia según score de deterioro"""
        if exit_score >= self.deterioration_thresholds['CRITICAL']:
            return ExitUrgency.EXIT_URGENT
        elif exit_score >= self.deterioration_thresholds['SEVERE']:
            return ExitUrgency.EXIT_RECOMMENDED
        elif exit_score >= self.deterioration_thresholds['MODERATE']:
            return ExitUrgency.EXIT_WATCH
        else:
            return ExitUrgency.NO_EXIT


if __name__ == "__main__":
    # Test del replicador
    logging.basicConfig(level=logging.INFO)

    print("🚪 EXIT REPLICATOR - TEST")
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
        indicator_scores={},
        indicator_signals={}
    )

    # Crear fila actual con deterioro
    test_row = pd.Series({
        'rsi_value': 82,  # Sobrecomprado extremo
        'macd_histogram': -0.1,  # Momentum bajista
        'roc_value': -2.5,  # ROC negativo
        'bb_position': 0.96,  # Banda superior
        'volume_oscillator': -60,  # Volumen vendedor
        'atr_percentage': 2.5,
    })

    replicator = ExitReplicator()

    should_exit, urgency, score, reason = replicator.evaluate_exit_conditions(
        original_signal=test_signal,
        current_row=test_row,
        entry_price=150.0,
        current_price=148.0,
        bars_held=10
    )

    print(f"\n✅ Evaluación completada:")
    print(f"   Should exit: {should_exit}")
    print(f"   Urgency: {urgency.value}")
    print(f"   Deterioration score: {score:.1f}")
    print(f"   Reason: {reason}")
