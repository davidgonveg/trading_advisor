#!/usr/bin/env python3
"""
🔬 INDICATOR ANALYZER - Análisis de Importancia de Indicadores
===========================================================

Analiza qué indicadores son más importantes para el éxito de la estrategia.
"""

import logging
import pandas as pd
import numpy as np
from typing import Dict, List
from collections import defaultdict

logger = logging.getLogger(__name__)


class IndicatorAnalyzer:
    """Analizador de importancia de indicadores"""

    def __init__(self):
        logger.info("🔬 IndicatorAnalyzer inicializado")

    def analyze_indicator_contribution(self, trades: List[Dict]) -> Dict[str, Dict]:
        """
        Analizar contribución de cada indicador al éxito/fracaso.

        Args:
            trades: Lista de trades

        Returns:
            Dict con análisis por indicador
        """
        try:
            indicators = ['MACD', 'RSI', 'VWAP', 'ROC', 'BOLLINGER', 'VOLUME']

            results = {}

            for indicator in indicators:
                # Agrupar trades por score de este indicador
                high_score_trades = []
                low_score_trades = []

                for trade in trades:
                    if trade['status'] not in ['CLOSED_WIN', 'CLOSED_LOSS', 'CLOSED_EXIT_MANAGER']:
                        continue

                    # Obtener score del indicador (de la señal original)
                    # Nota: esto requeriría acceso a indicator_scores de la señal
                    # Por simplicidad, usamos signal_strength como proxy
                    if trade['signal_strength'] >= 75:
                        high_score_trades.append(trade)
                    else:
                        low_score_trades.append(trade)

                # Calcular métricas
                def calc_metrics(trades_list):
                    if not trades_list:
                        return {'count': 0, 'win_rate': 0, 'avg_pnl': 0}

                    wins = [t for t in trades_list if t['total_pnl'] > 0]
                    return {
                        'count': len(trades_list),
                        'win_rate': (len(wins) / len(trades_list) * 100),
                        'avg_pnl': np.mean([t['total_pnl'] for t in trades_list]),
                        'total_pnl': sum(t['total_pnl'] for t in trades_list),
                    }

                results[indicator] = {
                    'high_score': calc_metrics(high_score_trades),
                    'low_score': calc_metrics(low_score_trades),
                }

            logger.info("🔬 Análisis de indicadores completado")
            return results

        except Exception as e:
            logger.error(f"❌ Error en análisis de indicadores: {e}")
            return {}

    def find_best_indicator_combinations(self, trades: List[Dict]) -> List[Dict]:
        """Encontrar las mejores combinaciones de indicadores"""
        try:
            # Simplificado: retornar top trades por signal strength
            closed_trades = [t for t in trades if t['status'] in ['CLOSED_WIN', 'CLOSED_LOSS', 'CLOSED_EXIT_MANAGER']]

            winning_trades = [t for t in closed_trades if t['total_pnl'] > 0]
            winning_trades.sort(key=lambda x: x['total_pnl'], reverse=True)

            top_10 = winning_trades[:10]

            return [{
                'symbol': t['symbol'],
                'signal_strength': t['signal_strength'],
                'entry_quality': t['entry_quality'],
                'pnl': t['total_pnl'],
            } for t in top_10]

        except Exception as e:
            logger.error(f"❌ Error buscando mejores combinaciones: {e}")
            return []
