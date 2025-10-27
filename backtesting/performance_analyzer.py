#!/usr/bin/env python3
"""
📈 PERFORMANCE ANALYZER - Análisis de Rendimiento
===============================================

Analiza rendimiento por símbolo, calcula métricas detalladas,
y genera insights sobre el comportamiento de la estrategia.
"""

import logging
import pandas as pd
import numpy as np
from typing import Dict, List
from collections import defaultdict

logger = logging.getLogger(__name__)


class PerformanceAnalyzer:
    """Analizador de rendimiento por símbolo y conjunto"""

    def __init__(self):
        logger.info("📈 PerformanceAnalyzer inicializado")

    def analyze_by_symbol(self, trades: List[Dict]) -> Dict[str, Dict]:
        """
        Analizar rendimiento por símbolo individual.

        Args:
            trades: Lista de trades (dicts)

        Returns:
            Dict con métricas por símbolo
        """
        try:
            # Agrupar trades por símbolo
            trades_by_symbol = defaultdict(list)
            for trade in trades:
                if trade['status'] in ['CLOSED_WIN', 'CLOSED_LOSS', 'CLOSED_EXIT_MANAGER']:
                    trades_by_symbol[trade['symbol']].append(trade)

            # Calcular métricas por símbolo
            results = {}

            for symbol, symbol_trades in trades_by_symbol.items():
                wins = [t for t in symbol_trades if t['total_pnl'] > 0]
                losses = [t for t in symbol_trades if t['total_pnl'] <= 0]

                total_trades = len(symbol_trades)
                win_rate = (len(wins) / total_trades * 100) if total_trades > 0 else 0

                total_pnl = sum(t['total_pnl'] for t in symbol_trades)
                total_profit = sum(t['total_pnl'] for t in wins)
                total_loss = abs(sum(t['total_pnl'] for t in losses))

                profit_factor = (total_profit / total_loss) if total_loss > 0 else 0

                results[symbol] = {
                    'total_trades': total_trades,
                    'wins': len(wins),
                    'losses': len(losses),
                    'win_rate': win_rate,
                    'total_pnl': total_pnl,
                    'total_profit': total_profit,
                    'total_loss': total_loss,
                    'profit_factor': profit_factor,
                    'avg_pnl': total_pnl / total_trades if total_trades > 0 else 0,
                    'avg_win': total_profit / len(wins) if wins else 0,
                    'avg_loss': total_loss / len(losses) if losses else 0,
                    'largest_win': max((t['total_pnl'] for t in wins), default=0),
                    'largest_loss': min((t['total_pnl'] for t in symbol_trades), default=0),
                    'avg_bars_held': np.mean([t['bars_held'] for t in symbol_trades]),
                }

            logger.info(f"📊 Análisis por símbolo completado ({len(results)} símbolos)")
            return results

        except Exception as e:
            logger.error(f"❌ Error en análisis por símbolo: {e}")
            return {}

    def analyze_long_vs_short(self, trades: List[Dict]) -> Dict:
        """Analizar rendimiento de LONG vs SHORT"""
        try:
            long_trades = [t for t in trades if t['direction'] == 'LONG' and t['status'] in ['CLOSED_WIN', 'CLOSED_LOSS', 'CLOSED_EXIT_MANAGER']]
            short_trades = [t for t in trades if t['direction'] == 'SHORT' and t['status'] in ['CLOSED_WIN', 'CLOSED_LOSS', 'CLOSED_EXIT_MANAGER']]

            def calc_metrics(trades_list):
                if not trades_list:
                    return {
                        'total_trades': 0,
                        'wins': 0,
                        'win_rate': 0,
                        'total_pnl': 0,
                        'profit_factor': 0,
                    }

                wins = [t for t in trades_list if t['total_pnl'] > 0]
                total_pnl = sum(t['total_pnl'] for t in trades_list)
                total_profit = sum(t['total_pnl'] for t in wins)
                total_loss = abs(sum(t['total_pnl'] for t in trades_list if t['total_pnl'] <= 0))

                return {
                    'total_trades': len(trades_list),
                    'wins': len(wins),
                    'win_rate': (len(wins) / len(trades_list) * 100),
                    'total_pnl': total_pnl,
                    'profit_factor': (total_profit / total_loss) if total_loss > 0 else 0,
                }

            return {
                'LONG': calc_metrics(long_trades),
                'SHORT': calc_metrics(short_trades),
            }

        except Exception as e:
            logger.error(f"❌ Error en análisis LONG vs SHORT: {e}")
            return {}

    def analyze_exit_reasons(self, trades: List[Dict]) -> Dict:
        """Analizar distribución de razones de salida"""
        try:
            exit_reasons = defaultdict(lambda: {'count': 0, 'total_pnl': 0.0})

            for trade in trades:
                if trade['status'] in ['CLOSED_WIN', 'CLOSED_LOSS', 'CLOSED_EXIT_MANAGER']:
                    reason = trade['exit_reason']
                    exit_reasons[reason]['count'] += 1
                    exit_reasons[reason]['total_pnl'] += trade['total_pnl']

            return dict(exit_reasons)

        except Exception as e:
            logger.error(f"❌ Error en análisis de exit reasons: {e}")
            return {}

    def analyze_signal_strength_performance(self, trades: List[Dict]) -> Dict:
        """Analizar rendimiento por fuerza de señal"""
        try:
            # Agrupar por rangos de signal strength
            ranges = {
                '55-64': {'trades': [], 'pnl': 0},
                '65-74': {'trades': [], 'pnl': 0},
                '75-84': {'trades': [], 'pnl': 0},
                '85-100': {'trades': [], 'pnl': 0},
            }

            for trade in trades:
                if trade['status'] in ['CLOSED_WIN', 'CLOSED_LOSS', 'CLOSED_EXIT_MANAGER']:
                    strength = trade['signal_strength']
                    if 55 <= strength < 65:
                        ranges['55-64']['trades'].append(trade)
                        ranges['55-64']['pnl'] += trade['total_pnl']
                    elif 65 <= strength < 75:
                        ranges['65-74']['trades'].append(trade)
                        ranges['65-74']['pnl'] += trade['total_pnl']
                    elif 75 <= strength < 85:
                        ranges['75-84']['trades'].append(trade)
                        ranges['75-84']['pnl'] += trade['total_pnl']
                    else:
                        ranges['85-100']['trades'].append(trade)
                        ranges['85-100']['pnl'] += trade['total_pnl']

            # Calcular métricas por rango
            results = {}
            for range_name, data in ranges.items():
                trades_list = data['trades']
                if trades_list:
                    wins = [t for t in trades_list if t['total_pnl'] > 0]
                    results[range_name] = {
                        'count': len(trades_list),
                        'win_rate': (len(wins) / len(trades_list) * 100),
                        'total_pnl': data['pnl'],
                        'avg_pnl': data['pnl'] / len(trades_list),
                    }
                else:
                    results[range_name] = {
                        'count': 0,
                        'win_rate': 0,
                        'total_pnl': 0,
                        'avg_pnl': 0,
                    }

            return results

        except Exception as e:
            logger.error(f"❌ Error en análisis de signal strength: {e}")
            return {}
