#!/usr/bin/env python3
"""
📡 SIGNAL REPLICATOR - Wrapper del Scanner Real
===============================================

Este módulo adapta el scanner real del sistema para usarlo en backtesting.
NO reimplementa la lógica, sino que usa DIRECTAMENTE las clases reales.
"""

import logging
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import sys
from pathlib import Path

# Añadir path del proyecto
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from scanner import SignalScanner, TradingSignal
from indicators import TechnicalIndicators
import config

logger = logging.getLogger(__name__)


class SignalReplicator:
    """
    Replica el comportamiento del scanner real usando datos históricos.

    Este wrapper toma datos históricos punto por punto y los pasa al scanner real,
    simulando el comportamiento en tiempo real pero con datos históricos.
    """

    def __init__(self):
        """Inicializar replicador con componentes reales"""
        self.scanner = SignalScanner()
        self.indicators = TechnicalIndicators()

        logger.info("📡 SignalReplicator inicializado con scanner REAL")

    def generate_signal_from_historical_data(
        self,
        symbol: str,
        current_row: pd.Series,
        historical_df: pd.DataFrame,
        current_index: int
    ) -> Optional[TradingSignal]:
        """
        Generar señal usando datos históricos como si fueran en tiempo real.

        Args:
            symbol: Símbolo del activo
            current_row: Fila actual (punto en el tiempo)
            historical_df: DataFrame con todos los datos históricos (para contexto)
            current_index: Índice actual en el DataFrame

        Returns:
            TradingSignal si se detecta señal, None si no
        """
        try:
            # Obtener datos hasta el momento actual (no look-ahead bias)
            data_until_now = historical_df.iloc[:current_index + 1].copy()

            # Construir dict de indicadores desde la fila actual
            indicators_dict = self._build_indicators_dict(current_row, data_until_now)

            # Evaluar señal LONG
            long_score, long_indicator_scores, long_signals = self.scanner.evaluate_long_signal(indicators_dict)

            # Evaluar señal SHORT
            short_score, short_indicator_scores, short_signals = self.scanner.evaluate_short_signal(indicators_dict)

            # Determinar tipo de señal
            signal_type = "NONE"
            signal_strength = 0
            indicator_scores = {}
            indicator_signals = {}

            if long_score > short_score and long_score >= config.SIGNAL_THRESHOLDS['NO_TRADE']:
                signal_type = "LONG"
                signal_strength = long_score
                indicator_scores = long_indicator_scores
                indicator_signals = long_signals
            elif short_score > long_score and short_score >= config.SIGNAL_THRESHOLDS['NO_TRADE']:
                signal_type = "SHORT"
                signal_strength = short_score
                indicator_scores = short_indicator_scores
                indicator_signals = short_signals

            # Si no hay señal válida, retornar None
            if signal_type == "NONE":
                return None

            # Determinar calidad de entrada
            entry_quality = self._determine_entry_quality(signal_strength)

            # Determinar nivel de confianza
            confidence_level = self._determine_confidence_level(signal_strength)

            # Crear señal de trading (igual que en producción)
            signal = TradingSignal(
                symbol=symbol,
                timestamp=current_row['timestamp'],
                signal_type=signal_type,
                signal_strength=signal_strength,
                confidence_level=confidence_level,
                current_price=current_row['close_price'],
                entry_quality=entry_quality,
                indicator_scores=indicator_scores,
                indicator_signals=indicator_signals,
                market_data=data_until_now  # Para position calculator
            )

            logger.debug(f"📡 Señal generada: {symbol} {signal_type} ({signal_strength} pts)")

            return signal

        except Exception as e:
            logger.error(f"❌ Error generando señal para {symbol}: {e}")
            return None

    def _build_indicators_dict(self, row: pd.Series, historical_data: pd.DataFrame) -> Dict:
        """
        Construir diccionario de indicadores desde la fila actual.

        Este diccionario tiene el mismo formato que el que retorna
        TechnicalIndicators.get_all_indicators() en producción.
        """
        try:
            indicators = {
                'symbol': row['symbol'],
                'timestamp': row['timestamp'],
                'current_price': row['close_price'],
                'open_price': row['open_price'],
                'high_price': row['high_price'],
                'low_price': row['low_price'],
                'current_volume': row['volume'],

                # MACD
                'macd': {
                    'macd': row.get('macd_line', 0),
                    'signal': row.get('macd_signal', 0),
                    'histogram': row.get('macd_histogram', 0),
                    'bullish_cross': self._detect_macd_cross(historical_data, len(historical_data) - 1, 'bullish'),
                    'bearish_cross': self._detect_macd_cross(historical_data, len(historical_data) - 1, 'bearish'),
                },

                # RSI
                'rsi': {
                    'rsi': row.get('rsi_value', 50),
                    'oversold': row.get('rsi_value', 50) < config.RSI_OVERSOLD,
                    'overbought': row.get('rsi_value', 50) > config.RSI_OVERBOUGHT,
                },

                # VWAP
                'vwap': {
                    'vwap': row.get('vwap_value', row['close_price']),
                    'deviation_pct': row.get('vwap_deviation_pct', 0),
                    'price': row['close_price'],
                },

                # ROC (momentum)
                'roc': {
                    'roc': row.get('roc_value', 0),
                },

                # Bollinger Bands
                'bollinger': {
                    'upper_band': row.get('bb_upper', row['close_price'] * 1.02),
                    'middle_band': row.get('bb_middle', row['close_price']),
                    'lower_band': row.get('bb_lower', row['close_price'] * 0.98),
                    'bb_position': row.get('bb_position', 0.5),
                },

                # Volume Oscillator
                'volume_osc': {
                    'volume_oscillator': row.get('volume_oscillator', 0),
                },

                # ATR
                'atr': {
                    'atr': row.get('atr_value', row['close_price'] * 0.02),
                    'atr_percentage': row.get('atr_percentage', 2.0),
                    'volatility_level': row.get('volatility_level', 'NORMAL'),
                },

                # Market context
                'market_regime': row.get('market_regime', 'UNKNOWN'),
            }

            return indicators

        except Exception as e:
            logger.error(f"❌ Error construyendo indicators dict: {e}")
            return {}

    def _detect_macd_cross(self, df: pd.DataFrame, current_idx: int, cross_type: str) -> bool:
        """
        Detectar cruce de MACD (bullish o bearish).

        Args:
            df: DataFrame con datos históricos
            current_idx: Índice actual
            cross_type: 'bullish' o 'bearish'

        Returns:
            True si hay cruce, False si no
        """
        try:
            if current_idx < 2:
                return False

            # Obtener valores actuales y anteriores
            current_macd = df.iloc[current_idx].get('macd_line', 0)
            current_signal = df.iloc[current_idx].get('macd_signal', 0)
            prev_macd = df.iloc[current_idx - 1].get('macd_line', 0)
            prev_signal = df.iloc[current_idx - 1].get('macd_signal', 0)

            if cross_type == 'bullish':
                # MACD cruza por encima de signal
                return prev_macd <= prev_signal and current_macd > current_signal
            elif cross_type == 'bearish':
                # MACD cruza por debajo de signal
                return prev_macd >= prev_signal and current_macd < current_signal

            return False

        except Exception as e:
            logger.error(f"❌ Error detectando MACD cross: {e}")
            return False

    def _determine_entry_quality(self, signal_strength: int) -> str:
        """Determinar calidad de entrada basada en fuerza de señal"""
        if signal_strength >= config.SIGNAL_THRESHOLDS['FULL_ENTRY']:
            return "FULL_ENTRY"
        elif signal_strength >= config.SIGNAL_THRESHOLDS['PARTIAL_ENTRY']:
            return "PARTIAL_ENTRY"
        else:
            return "NO_TRADE"

    def _determine_confidence_level(self, signal_strength: int) -> str:
        """Determinar nivel de confianza basado en fuerza de señal"""
        if signal_strength >= 85:
            return "VERY_HIGH"
        elif signal_strength >= 75:
            return "HIGH"
        elif signal_strength >= 65:
            return "MEDIUM"
        else:
            return "LOW"

    def scan_historical_dataframe(
        self,
        symbol: str,
        df: pd.DataFrame,
        min_signal_strength: int = 55
    ) -> List[Tuple[int, TradingSignal]]:
        """
        Escanear todo un DataFrame histórico y generar señales.

        Args:
            symbol: Símbolo del activo
            df: DataFrame con datos históricos ordenados
            min_signal_strength: Fuerza mínima de señal

        Returns:
            Lista de tuplas (índice, señal)
        """
        signals_found = []

        logger.info(f"📡 Escaneando {len(df)} filas de {symbol}...")

        for i in range(len(df)):
            # Generar señal para esta fila
            signal = self.generate_signal_from_historical_data(
                symbol=symbol,
                current_row=df.iloc[i],
                historical_df=df,
                current_index=i
            )

            # Si hay señal válida, añadirla
            if signal and signal.signal_strength >= min_signal_strength:
                signals_found.append((i, signal))
                logger.debug(
                    f"  [{i}] {signal.timestamp}: {signal.signal_type} "
                    f"({signal.signal_strength} pts, {signal.entry_quality})"
                )

        logger.info(f"📊 {len(signals_found)} señales encontradas en {symbol}")

        return signals_found


if __name__ == "__main__":
    # Test del replicador
    logging.basicConfig(level=logging.INFO)

    print("📡 SIGNAL REPLICATOR - TEST")
    print("=" * 70)

    # Test con datos reales de la BD
    from database.connection import get_connection

    symbol = "AAPL"
    conn = get_connection()

    query = """
    SELECT * FROM indicators_data
    WHERE symbol = ?
    ORDER BY timestamp ASC
    LIMIT 1000
    """

    df = pd.read_sql_query(query, conn, params=[symbol])
    conn.close()

    if not df.empty:
        df['timestamp'] = pd.to_datetime(df['timestamp'])

        replicator = SignalReplicator()
        signals = replicator.scan_historical_dataframe(symbol, df, min_signal_strength=65)

        print(f"\n✅ Test completado:")
        print(f"   Filas procesadas: {len(df)}")
        print(f"   Señales generadas: {len(signals)}")

        if signals:
            print(f"\n📊 Primeras 5 señales:")
            for i, (idx, signal) in enumerate(signals[:5], 1):
                print(f"   {i}. {signal.timestamp}: {signal.signal_type} "
                      f"({signal.signal_strength} pts)")
    else:
        print(f"❌ No hay datos para {symbol}")
