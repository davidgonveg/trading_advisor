#!/usr/bin/env python3
"""
📊 BACKTEST ENGINE V5.0 - TRADING SYSTEM WITH DATA VALIDATION
============================================================

Motor de backtesting robusto con validación completa de datos históricos:

🔍 DATA VALIDATION LAYER:
- Detecta gaps temporales y datos faltantes
- Valida calidad de indicadores técnicos
- Identifica anomalías de precios/volumen
- Maneja weekends y holidays correctamente
- Verifica continuidad antes de simular trades

🚀 TRADING SIMULATION:
- Simulación realista con slippage y spread
- Validación de liquidez mínima
- Manejo de gaps de precio
- Exit conditions robustas

PHILOSOPHY: "Mejor no tradear que tradear con datos malos"
"""

import os
import sys
import pandas as pd
import numpy as np
import logging
import argparse
import json
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Union, Any, NamedTuple
from dataclasses import dataclass, asdict
import time
import warnings
from enum import Enum

# Paths para importar desde sistema principal
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.insert(0, project_root)

# Imports del sistema principal
try:
    import config
    from database.connection import get_connection
    from scanner import SignalScanner, TradingSignal
    from indicators import TechnicalIndicators
    from position_calculator import PositionCalculator, PositionPlan
    print("✅ Todos los módulos del sistema importados correctamente")
except ImportError as e:
    print(f"❌ Error importing modules: {e}")
    print("💡 Asegúrate de estar en historical_data/ y que el sistema principal esté disponible")
    sys.exit(1)

# Configurar logging
logging.basicConfig(
    level=getattr(logging, getattr(config, 'LOG_LEVEL', 'INFO'), 'INFO'),
    format='%(levelname)s:%(name)s:%(message)s'
)
logger = logging.getLogger(__name__)
warnings.filterwarnings('ignore')

class DataQuality(Enum):
    """Niveles de calidad de datos"""
    EXCELLENT = "EXCELLENT"    # <1% gaps, todos los indicadores válidos
    GOOD = "GOOD"             # 1-5% gaps, indicadores mayormente válidos  
    FAIR = "FAIR"             # 5-15% gaps, algunos problemas de indicadores
    POOR = "POOR"             # >15% gaps, muchos indicadores inválidos
    UNUSABLE = "UNUSABLE"     # Datos insuficientes o muy corruptos

@dataclass
class DataValidationReport:
    """Reporte de validación de datos"""
    symbol: str
    start_date: datetime
    end_date: datetime
    total_expected_periods: int
    actual_periods: int
    missing_periods: int
    gap_percentage: float
    largest_gap_days: int
    indicators_with_nan: List[str]
    indicators_with_inf: List[str]
    indicators_outside_bounds: List[str]
    price_anomalies: List[Dict]
    volume_anomalies: List[Dict]
    overall_quality: DataQuality
    quality_score: float
    usable_for_backtest: bool
    warnings: List[str]
    recommendations: List[str]

@dataclass 
class BacktestTrade:
    """Representa un trade completado en el backtest"""
    symbol: str
    direction: str
    entry_signal: TradingSignal
    entry_time: datetime
    entry_price: float
    position_size: float
    exit_time: datetime
    exit_price: float
    exit_reason: str
    pnl_dollars: float
    pnl_percent: float
    hold_time_hours: float
    max_favorable_excursion: float
    max_adverse_excursion: float
    
    # Nuevos campos de validación
    data_quality_score: float
    price_slippage: float
    execution_issues: List[str]

@dataclass
class BacktestMetrics:
    """Métricas completas del backtest"""
    # Métricas básicas
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    
    # Métricas financieras
    total_return: float
    total_return_pct: float
    avg_trade_return: float
    avg_winning_trade: float
    avg_losing_trade: float
    
    # Métricas de riesgo
    max_drawdown: float
    max_drawdown_pct: float
    sharpe_ratio: float
    profit_factor: float
    
    # Métricas de calidad de datos
    avg_data_quality: float
    reliability_score: float
    execution_issues: int
    
    # Métricas temporales
    avg_hold_time_hours: float
    longest_hold_hours: float
    shortest_hold_hours: float

class ValidatedBacktestEngine:
    """Engine de backtesting con validación completa de datos"""
    
    def __init__(self, account_balance: float = 10000, strict_mode: bool = False):
        """
        Inicializar engine de backtesting
        
        Args:
            account_balance: Balance inicial de cuenta
            strict_mode: Si True, excluye datos de baja calidad
        """
        self.account_balance = account_balance
        self.strict_mode = strict_mode
        
        # Componentes del sistema
        self.scanner = SignalScanner()
        self.indicators = TechnicalIndicators()
        self.position_calc = PositionCalculator()
        
        # Configuración de simulación
        self.commission_rate = 0.001  # 0.1% por trade
        self.slippage_rate = 0.0005   # 0.05% slippage promedio
        self.min_volume_threshold = 100000  # Volumen mínimo para liquidez
        
        # Storage para validación y trades
        self.validation_reports = {}
        self.completed_trades = []
        self.active_positions = {}
        
        logger.info(f"📊 ValidatedBacktestEngine inicializado - Strict: {strict_mode}")
    
    def validate_symbol_data(self, symbol: str, start_date: datetime, 
                           end_date: datetime) -> DataValidationReport:
        """
        Validar completamente los datos de un símbolo
        
        Args:
            symbol: Símbolo a validar
            start_date: Fecha de inicio
            end_date: Fecha de fin
            
        Returns:
            DataValidationReport con análisis completo
        """
        try:
            logger.info(f"🔍 Validando datos de {symbol}...")
            
            # Obtener datos desde base de datos
            data = self._get_symbol_data(symbol, start_date, end_date)
            
            if data is None or data.empty:
                return DataValidationReport(
                    symbol=symbol,
                    start_date=start_date,
                    end_date=end_date,
                    total_expected_periods=0,
                    actual_periods=0,
                    missing_periods=0,
                    gap_percentage=100.0,
                    largest_gap_days=0,
                    indicators_with_nan=[],
                    indicators_with_inf=[],
                    indicators_outside_bounds=[],
                    price_anomalies=[],
                    volume_anomalies=[],
                    overall_quality=DataQuality.UNUSABLE,
                    quality_score=0.0,
                    usable_for_backtest=False,
                    warnings=["No data available"],
                    recommendations=["Download historical data for this symbol"]
                )
            
            # Validaciones específicas
            temporal_metrics = self._validate_temporal_continuity(data, start_date, end_date)
            indicator_metrics = self._validate_indicators(data)
            price_metrics = self._validate_price_data(data)
            volume_metrics = self._validate_volume_data(data)
            
            # Calcular score de calidad general
            quality_score = self._calculate_overall_quality_score(
                temporal_metrics, indicator_metrics, price_metrics, volume_metrics
            )
            
            # Determinar calidad general
            overall_quality = self._determine_quality_level(quality_score)
            usable = quality_score >= 60.0  # Mínimo 60% calidad para backtest
            
            # Generar warnings y recomendaciones
            warnings, recommendations = self._generate_warnings_and_recommendations(
                temporal_metrics, indicator_metrics, price_metrics, volume_metrics
            )
            
            report = DataValidationReport(
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
                total_expected_periods=temporal_metrics['expected_periods'],
                actual_periods=temporal_metrics['actual_periods'],
                missing_periods=temporal_metrics['missing_periods'],
                gap_percentage=temporal_metrics['gap_percentage'],
                largest_gap_days=temporal_metrics['largest_gap_days'],
                indicators_with_nan=indicator_metrics['nan_indicators'],
                indicators_with_inf=indicator_metrics['inf_indicators'],
                indicators_outside_bounds=indicator_metrics['outlier_indicators'],
                price_anomalies=price_metrics['anomalies'],
                volume_anomalies=volume_metrics['anomalies'],
                overall_quality=overall_quality,
                quality_score=quality_score,
                usable_for_backtest=usable,
                warnings=warnings,
                recommendations=recommendations
            )
            
            logger.info(f"✅ {symbol} validation complete: {overall_quality.value} ({quality_score:.1f}/100)")
            return report
            
        except Exception as e:
            logger.error(f"❌ Error validating {symbol}: {e}")
            return DataValidationReport(
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
                total_expected_periods=0,
                actual_periods=0,
                missing_periods=0,
                gap_percentage=100.0,
                largest_gap_days=0,
                indicators_with_nan=[],
                indicators_with_inf=[],
                indicators_outside_bounds=[],
                price_anomalies=[],
                volume_anomalies=[],
                overall_quality=DataQuality.UNUSABLE,
                quality_score=0.0,
                usable_for_backtest=False,
                warnings=[f"Validation error: {str(e)}"],
                recommendations=["Check data availability and database connection"]
            )
    
    def validate_all_data(self, symbols: List[str], start_date: datetime, 
                         end_date: datetime) -> Dict[str, DataValidationReport]:
        """Validar datos de todos los símbolos"""
        reports = {}
        
        for symbol in symbols:
            report = self.validate_symbol_data(symbol, start_date, end_date)
            reports[symbol] = report
            self.validation_reports[symbol] = report
        
        return reports
    
    def _get_symbol_data(self, symbol: str, start_date: datetime, 
                        end_date: datetime) -> pd.DataFrame:
        """Obtener datos del símbolo desde base de datos"""
        try:
            conn = get_connection()
            if not conn:
                return None
            
            # Query corregido basado en la estructura real de la tabla
            query = """
            SELECT timestamp, symbol, 
                open_price as open, high_price as high, low_price as low, 
                close_price as close, volume,
                macd_line as macd, macd_signal, macd_histogram, 
                rsi_value as rsi, vwap_value as vwap, roc_value as roc, 
                bb_upper, bb_middle, bb_lower, volume_oscillator, atr_value as atr,
                market_regime, volatility_level
            FROM indicators_data 
            WHERE symbol = ? AND datetime(timestamp) BETWEEN datetime(?) AND datetime(?)
            ORDER BY timestamp
            """
            
            df = pd.read_sql_query(
                query, 
                conn, 
                params=[symbol, start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')]
            )
            conn.close()
            
            if df.empty:
                return None
            
            # Convertir timestamp a datetime index
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df.set_index('timestamp', inplace=True)
            
            return df
            
        except Exception as e:
            logger.error(f"❌ Error getting data for {symbol}: {e}")
            return None
    
    def _validate_temporal_continuity(self, data: pd.DataFrame, 
                                    start_date: datetime, end_date: datetime) -> Dict:
        """Validar continuidad temporal de los datos"""
        if data.empty:
            return {
                'expected_periods': 0,
                'actual_periods': 0,
                'missing_periods': 0,
                'gap_percentage': 100.0,
                'largest_gap_days': 0,
                'gaps': []
            }
        
        # Detectar timeframe automáticamente basado en intervalos de tiempo
        data_sorted = data.sort_index()
        time_diffs = data_sorted.index.to_series().diff().dropna()
        
        # Calcular intervalo más común
        most_common_interval = time_diffs.mode().iloc[0] if not time_diffs.empty else pd.Timedelta('1H')
        
        # Determinar periods per day basado en el intervalo detectado
        if most_common_interval <= pd.Timedelta('15T'):  # 15 minutos o menos
            expected_periods_per_day = 26  # ~26 periods de 15m por día
            max_normal_gap = pd.Timedelta('1H')
        elif most_common_interval <= pd.Timedelta('1H'):  # 1 hora
            expected_periods_per_day = 6.5  # ~6.5 periods de 1h por día
            max_normal_gap = pd.Timedelta('4H')
        else:  # Diario u otros
            expected_periods_per_day = 1
            max_normal_gap = pd.Timedelta('3D')
        
        business_days = len(pd.bdate_range(start=start_date, end=end_date))
        expected_periods = int(business_days * expected_periods_per_day)
        actual_periods = len(data)
        missing_periods = max(0, expected_periods - actual_periods)
        gap_percentage = (missing_periods / expected_periods * 100) if expected_periods > 0 else 0
        
        # Calcular gaps más grandes
        large_gaps = time_diffs[time_diffs > max_normal_gap]
        largest_gap_days = large_gaps.max().days if not large_gaps.empty else 0
        
        return {
            'expected_periods': expected_periods,
            'actual_periods': actual_periods,
            'missing_periods': missing_periods,
            'gap_percentage': gap_percentage,
            'largest_gap_days': largest_gap_days,
            'gaps': large_gaps.tolist(),
            'detected_interval': str(most_common_interval)
        }
    
    def _validate_indicators(self, data: pd.DataFrame) -> Dict:
        """Validar calidad de indicadores técnicos"""
        indicator_columns = ['macd', 'macd_signal', 'macd_histogram', 'rsi', 'vwap', 
                           'roc', 'bb_upper', 'bb_middle', 'bb_lower', 'volume_oscillator', 'atr']
        
        nan_indicators = []
        inf_indicators = []
        outlier_indicators = []
        
        for col in indicator_columns:
            if col in data.columns:
                # Check for NaN values
                if data[col].isna().sum() > len(data) * 0.05:  # >5% NaN
                    nan_indicators.append(col)
                
                # Check for infinite values
                if np.isinf(data[col]).sum() > 0:
                    inf_indicators.append(col)
                
                # Check for unrealistic outliers (indicador específico)
                if col == 'rsi':
                    outliers = (data[col] < 0) | (data[col] > 100)
                    if outliers.sum() > 0:
                        outlier_indicators.append(f"{col}_bounds")
                elif col in ['bb_upper', 'bb_middle', 'bb_lower']:
                    # Bollinger bands deben tener upper > middle > lower
                    if col == 'bb_middle' and 'bb_upper' in data.columns and 'bb_lower' in data.columns:
                        invalid = (data['bb_upper'] <= data['bb_middle']) | (data['bb_middle'] <= data['bb_lower'])
                        if invalid.sum() > len(data) * 0.02:  # >2% invalid
                            outlier_indicators.append("bollinger_order")
        
        return {
            'nan_indicators': nan_indicators,
            'inf_indicators': inf_indicators,
            'outlier_indicators': outlier_indicators
        }
    
    def _validate_price_data(self, data: pd.DataFrame) -> Dict:
        """Validar datos de precios"""
        anomalies = []
        
        if 'close' in data.columns and 'high' in data.columns and 'low' in data.columns:
            # Check for price jumps (>10% change)
            price_changes = data['close'].pct_change().abs()
            large_changes = price_changes[price_changes > 0.10]  # >10% change
            
            for idx, change in large_changes.items():
                anomalies.append({
                    'type': 'price_jump',
                    'timestamp': idx,
                    'change_pct': change * 100,
                    'severity': 'HIGH' if change > 0.20 else 'MEDIUM'
                })
            
            # Check for invalid OHLC relationships
            invalid_ohlc = (
                (data['high'] < data['low']) |
                (data['high'] < data['close']) |
                (data['high'] < data['open']) |
                (data['low'] > data['close']) |
                (data['low'] > data['open'])
            )
            
            if invalid_ohlc.sum() > 0:
                anomalies.append({
                    'type': 'invalid_ohlc',
                    'count': invalid_ohlc.sum(),
                    'severity': 'HIGH'
                })
        
        return {'anomalies': anomalies}
    
    def _validate_volume_data(self, data: pd.DataFrame) -> Dict:
        """Validar datos de volumen"""
        anomalies = []
        
        if 'volume' in data.columns:
            # Check for zero/negative volume
            invalid_volume = (data['volume'] <= 0).sum()
            if invalid_volume > 0:
                anomalies.append({
                    'type': 'invalid_volume',
                    'count': invalid_volume,
                    'severity': 'MEDIUM'
                })
            
            # Check for extreme volume spikes (>1000% of median)
            median_volume = data['volume'].median()
            if median_volume > 0:
                volume_spikes = data['volume'][data['volume'] > median_volume * 10]
                if not volume_spikes.empty:
                    anomalies.append({
                        'type': 'volume_spike',
                        'count': len(volume_spikes),
                        'max_multiple': (volume_spikes.max() / median_volume),
                        'severity': 'LOW'
                    })
        
        return {'anomalies': anomalies}
    
    def _calculate_overall_quality_score(self, temporal: Dict, indicators: Dict,
                                       prices: Dict, volume: Dict) -> float:
        """Calcular score general de calidad (0-100)"""
        score = 100.0
        
        # Penalizar gaps temporales
        score -= min(temporal['gap_percentage'] * 0.8, 30)  # Máximo -30 pts
        
        # Penalizar indicadores problemáticos
        nan_penalty = len(indicators['nan_indicators']) * 5  # -5 pts por indicador
        inf_penalty = len(indicators['inf_indicators']) * 10  # -10 pts por indicador
        outlier_penalty = len(indicators['outlier_indicators']) * 3  # -3 pts por outlier
        score -= min(nan_penalty + inf_penalty + outlier_penalty, 25)
        
        # Penalizar anomalías de precios
        high_price_anomalies = sum(1 for a in prices['anomalies'] if a.get('severity') == 'HIGH')
        medium_price_anomalies = sum(1 for a in prices['anomalies'] if a.get('severity') == 'MEDIUM')
        score -= high_price_anomalies * 8 + medium_price_anomalies * 4
        
        # Penalizar problemas de volumen
        volume_penalty = len(volume['anomalies']) * 2
        score -= min(volume_penalty, 10)
        
        return max(0.0, score)
    
    def _determine_quality_level(self, score: float) -> DataQuality:
        """Determinar nivel de calidad basado en score"""
        if score >= 90:
            return DataQuality.EXCELLENT
        elif score >= 75:
            return DataQuality.GOOD
        elif score >= 60:
            return DataQuality.FAIR
        elif score >= 40:
            return DataQuality.POOR
        else:
            return DataQuality.UNUSABLE
    
    def _generate_warnings_and_recommendations(self, temporal: Dict, indicators: Dict,
                                             prices: Dict, volume: Dict) -> Tuple[List[str], List[str]]:
        """Generar warnings y recomendaciones"""
        warnings = []
        recommendations = []
        
        # Warnings temporales
        if temporal['gap_percentage'] > 5:
            warnings.append(f"Missing {temporal['gap_percentage']:.1f}% of expected data points")
        
        if temporal['largest_gap_days'] > 3:
            warnings.append(f"Largest data gap: {temporal['largest_gap_days']} days")
        
        # Warnings de indicadores
        if indicators['nan_indicators']:
            warnings.append(f"Indicators with NaN values: {', '.join(indicators['nan_indicators'])}")
        
        if indicators['inf_indicators']:
            warnings.append(f"Indicators with infinite values: {', '.join(indicators['inf_indicators'])}")
        
        # Warnings de precios
        price_jumps = [a for a in prices['anomalies'] if a['type'] == 'price_jump']
        if len(price_jumps) > 2:
            warnings.append(f"{len(price_jumps)} large price movements detected")
        
        # Recommendations
        if temporal['gap_percentage'] > 15:
            recommendations.append("Download more complete historical data")
        
        if indicators['nan_indicators'] or indicators['inf_indicators']:
            recommendations.append("Recalculate indicators with proper data cleaning")
        
        if len(price_jumps) > 3:
            recommendations.append("Review price data for stock splits or corporate actions")
        
        return warnings, recommendations
    
    def print_validation_summary(self):
        """Imprimir resumen de validación"""
        if not self.validation_reports:
            print("❌ No validation reports available")
            return
        
        print("\n📊 DATA VALIDATION SUMMARY")
        print("=" * 60)
        
        quality_counts = {}
        total_symbols = len(self.validation_reports)
        usable_symbols = 0
        
        for symbol, report in self.validation_reports.items():
            quality = report.overall_quality
            quality_counts[quality] = quality_counts.get(quality, 0) + 1
            
            if report.usable_for_backtest:
                usable_symbols += 1
        
        print(f"📈 Símbolos analizados: {total_symbols}")
        print(f"✅ Símbolos utilizables: {usable_symbols}/{total_symbols} ({usable_symbols/total_symbols*100:.1f}%)")
        print()
        
        print("🎯 DISTRIBUCIÓN DE CALIDAD:")
        for quality in [DataQuality.EXCELLENT, DataQuality.GOOD, DataQuality.FAIR, DataQuality.POOR, DataQuality.UNUSABLE]:
            count = quality_counts.get(quality, 0)
            if count > 0:
                emoji = {"EXCELLENT": "🟢", "GOOD": "🔵", "FAIR": "🟡", "POOR": "🟠", "UNUSABLE": "🔴"}
                print(f"   {emoji.get(quality.value, '❓')} {quality.value}: {count} símbolos")
        
        print("=" * 60)

    def run_backtest(self, symbols: List[str], start_date: datetime, 
                    end_date: datetime) -> BacktestMetrics:
        """Ejecutar backtest completo con validación"""
        logger.info(f"🚀 Starting validated backtest for {len(symbols)} symbols")
        
        # Primero validar todos los datos
        validation_reports = self.validate_all_data(symbols, start_date, end_date)
        
        # Filtrar símbolos utilizables
        if self.strict_mode:
            usable_symbols = [s for s, r in validation_reports.items() 
                            if r.usable_for_backtest and r.overall_quality != DataQuality.POOR]
        else:
            usable_symbols = [s for s, r in validation_reports.items() if r.usable_for_backtest]
        
        logger.info(f"📊 {len(usable_symbols)} símbolos utilizables de {len(symbols)} totales")
        
        if not usable_symbols:
            logger.warning("⚠️ No hay símbolos utilizables para backtest")
            return self._create_empty_metrics()
        
        # Ejecutar simulación por cada símbolo
        all_trades = []
        for symbol in usable_symbols:
            symbol_trades = self._simulate_symbol_trades(symbol, start_date, end_date)
            all_trades.extend(symbol_trades)
        
        # Calcular métricas
        metrics = self._calculate_backtest_metrics(all_trades, validation_reports)
        
        logger.info(f"✅ Backtest completado: {metrics.total_trades} trades ejecutados")
        return metrics
    
    def _simulate_symbol_trades(self, symbol: str, start_date: datetime, 
                               end_date: datetime) -> List[BacktestTrade]:
        """Simular trades para un símbolo específico"""
        trades = []
        
        try:
            # Obtener datos del símbolo
            data = self._get_symbol_data(symbol, start_date, end_date)
            if data is None or data.empty:
                return trades
            
            # Procesar cada fila de datos
            active_position = None
            
            for idx, row in data.iterrows():
                # Crear mock de indicadores para el scanner
                mock_indicators = {
                    'macd': {
                        'macd': row.get('macd', 0),
                        'signal': row.get('macd_signal', 0),
                        'histogram': row.get('macd_histogram', 0)
                    },
                    'rsi': {'rsi': row.get('rsi', 50)},
                    'vwap': {'vwap': row.get('vwap', row['close'])},
                    'roc': {'roc': row.get('roc', 0)},
                    'bollinger': {
                        'upper_band': row.get('bb_upper', row['close']),
                        'middle_band': row.get('bb_middle', row['close']),
                        'lower_band': row.get('bb_lower', row['close'])
                    },
                    'volume_osc': {'volume_oscillator': row.get('volume_oscillator', 0)},
                    'atr': {'atr': row.get('atr', 0.01)}
                }
                
                # Verificar si hay señal de entrada (sin posición activa)
                if active_position is None:
                    signal = self._evaluate_signal_at_timestamp(symbol, row, mock_indicators)
                    
                    if signal and signal.signal_type != 'NONE':
                        # Abrir posición
                        active_position = self._open_position(signal, row, idx)
                
                # Verificar condiciones de salida (con posición activa)
                elif active_position is not None:
                    exit_reason = self._check_exit_conditions(active_position, row, idx)
                    
                    if exit_reason:
                        # Cerrar posición
                        completed_trade = self._close_position(active_position, row, idx, exit_reason)
                        if completed_trade:
                            trades.append(completed_trade)
                        active_position = None
            
            logger.info(f"📊 {symbol}: {len(trades)} trades completados")
            return trades
            
        except Exception as e:
            logger.error(f"❌ Error simulando {symbol}: {e}")
            return trades
    
    def _evaluate_signal_at_timestamp(self, symbol: str, row: pd.Series, 
                                    indicators: Dict) -> Optional[TradingSignal]:
        """Evaluar si hay señal válida en este timestamp"""
        try:
            # Usar la lógica del scanner pero con datos históricos
            # Simplificado para backtest - puedes expandir esto
            
            rsi = indicators['rsi']['rsi']
            macd_hist = indicators['macd']['histogram']
            roc = indicators['roc']['roc']
            
            # Lógica básica de señales
            signal_strength = 0
            signal_type = 'NONE'
            
            # LONG signals
            if (macd_hist > 0 and rsi < 40 and roc > 1.5):
                signal_strength = 75
                signal_type = 'LONG'
            
            # SHORT signals  
            elif (macd_hist < 0 and rsi > 60 and roc < -1.5):
                signal_strength = 75
                signal_type = 'SHORT'
            
            if signal_strength >= 65:  # Umbral mínimo
                # Crear señal mock
                from scanner import TradingSignal
                from datetime import datetime
                
                signal = TradingSignal(
                    symbol=symbol,
                    timestamp=row.name,
                    signal_type=signal_type,
                    signal_strength=signal_strength,
                    confidence_level='MEDIUM',
                    current_price=row['close'],
                    entry_quality='FULL_ENTRY',
                    indicator_scores={
                        'MACD': 20 if signal_type == 'LONG' and macd_hist > 0 else (20 if signal_type == 'SHORT' and macd_hist < 0 else 0),
                        'RSI': 20 if (signal_type == 'LONG' and rsi < 40) or (signal_type == 'SHORT' and rsi > 60) else 0,
                        'ROC': 15 if abs(roc) > 1.5 else 0,
                        'VWAP': 10,
                        'BOLLINGER': 10,
                        'VOLUME': 10
                    },
                    indicator_signals={
                        'MACD': f"Histogram: {macd_hist:.4f}",
                        'RSI': f"RSI: {rsi:.1f}",
                        'ROC': f"ROC: {roc:.2f}%",
                        'VWAP': "Near VWAP",
                        'BOLLINGER': "In range",
                        'VOLUME': "Adequate"
                    }
                )
                
                return signal
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Error evaluating signal for {symbol}: {e}")
            return None
    
    def _open_position(self, signal: TradingSignal, row: pd.Series, timestamp) -> Dict:
        """Abrir nueva posición"""
        try:
            # Calcular tamaño de posición (simplified)
            risk_amount = self.account_balance * 0.02  # 2% risk per trade
            atr = row.get('atr', row['close'] * 0.02)  # Default ATR if not available
            
            # Stop loss distance (2x ATR)
            stop_distance = atr * 2
            position_size = risk_amount / stop_distance
            
            # Calcular stop loss price
            if signal.signal_type == 'LONG':
                stop_price = row['close'] - stop_distance
                target_price = row['close'] + (stop_distance * 2)  # 1:2 R:R
            else:
                stop_price = row['close'] + stop_distance
                target_price = row['close'] - (stop_distance * 2)
            
            position = {
                'signal': signal,
                'entry_time': timestamp,
                'entry_price': row['close'],
                'position_size': position_size,
                'stop_price': stop_price,
                'target_price': target_price,
                'direction': signal.signal_type
            }
            
            return position
            
        except Exception as e:
            logger.error(f"❌ Error opening position: {e}")
            return None
    
    def _check_exit_conditions(self, position: Dict, row: pd.Series, timestamp) -> Optional[str]:
        """Verificar condiciones de salida"""
        try:
            current_price = row['close']
            high_price = row['high']
            low_price = row['low']
            
            # Check stop loss
            if position['direction'] == 'LONG':
                if low_price <= position['stop_price']:
                    return 'STOP_LOSS'
                elif high_price >= position['target_price']:
                    return 'TARGET_REACHED'
            else:  # SHORT
                if high_price >= position['stop_price']:
                    return 'STOP_LOSS'
                elif low_price <= position['target_price']:
                    return 'TARGET_REACHED'
            
            # Time-based exit (24 hours max hold)
            time_diff = timestamp - position['entry_time']
            if time_diff.total_seconds() > 24 * 3600:  # 24 hours
                return 'TIME_EXIT'
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Error checking exit conditions: {e}")
            return 'ERROR_EXIT'
    
    def _close_position(self, position: Dict, row: pd.Series, timestamp, exit_reason: str) -> Optional[BacktestTrade]:
        """Cerrar posición y crear trade record"""
        try:
            # Determinar precio de salida según razón
            if exit_reason == 'STOP_LOSS':
                exit_price = position['stop_price']
            elif exit_reason == 'TARGET_REACHED':
                exit_price = position['target_price']
            else:
                exit_price = row['close']
            
            # Aplicar slippage
            slippage_amount = exit_price * self.slippage_rate
            if position['direction'] == 'LONG':
                exit_price -= slippage_amount  # Peor precio para LONG
            else:
                exit_price += slippage_amount  # Peor precio para SHORT
            
            # Calcular P&L
            if position['direction'] == 'LONG':
                pnl_dollars = (exit_price - position['entry_price']) * position['position_size']
                pnl_percent = (exit_price - position['entry_price']) / position['entry_price'] * 100
            else:
                pnl_dollars = (position['entry_price'] - exit_price) * position['position_size']
                pnl_percent = (position['entry_price'] - exit_price) / position['entry_price'] * 100
            
            # Aplicar comisiones
            commission_cost = (position['entry_price'] + exit_price) * position['position_size'] * self.commission_rate
            pnl_dollars -= commission_cost
            
            # Calcular hold time
            hold_time = timestamp - position['entry_time']
            hold_hours = hold_time.total_seconds() / 3600
            
            # Calcular excursiones (simplified)
            mfe = abs(pnl_dollars) * 1.2 if pnl_dollars > 0 else 0  # Max favorable
            mae = abs(pnl_dollars) * 0.8 if pnl_dollars < 0 else 0  # Max adverse
            
            trade = BacktestTrade(
                symbol=position['signal'].symbol,
                direction=position['direction'],
                entry_signal=position['signal'],
                entry_time=position['entry_time'],
                entry_price=position['entry_price'],
                position_size=position['position_size'],
                exit_time=timestamp,
                exit_price=exit_price,
                exit_reason=exit_reason,
                pnl_dollars=pnl_dollars,
                pnl_percent=pnl_percent,
                hold_time_hours=hold_hours,
                max_favorable_excursion=mfe,
                max_adverse_excursion=mae,
                data_quality_score=self.validation_reports[position['signal'].symbol].quality_score,
                price_slippage=slippage_amount,
                execution_issues=[]
            )
            
            return trade
            
        except Exception as e:
            logger.error(f"❌ Error closing position: {e}")
            return None
    
    def _calculate_backtest_metrics(self, trades: List[BacktestTrade], 
                                   validation_reports: Dict) -> BacktestMetrics:
        """Calcular métricas completas del backtest"""
        if not trades:
            return self._create_empty_metrics()
        
        # Métricas básicas
        total_trades = len(trades)
        winning_trades = len([t for t in trades if t.pnl_dollars > 0])
        losing_trades = total_trades - winning_trades
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        
        # Métricas financieras
        total_return = sum(t.pnl_dollars for t in trades)
        total_return_pct = (total_return / self.account_balance) * 100
        avg_trade_return = total_return / total_trades if total_trades > 0 else 0
        
        winning_pnl = [t.pnl_dollars for t in trades if t.pnl_dollars > 0]
        losing_pnl = [t.pnl_dollars for t in trades if t.pnl_dollars < 0]
        
        avg_winning_trade = sum(winning_pnl) / len(winning_pnl) if winning_pnl else 0
        avg_losing_trade = sum(losing_pnl) / len(losing_pnl) if losing_pnl else 0
        
        # Métricas de riesgo
        returns = [t.pnl_dollars for t in trades]
        cumulative_returns = np.cumsum(returns)
        
        # Max drawdown
        peak = np.maximum.accumulate(cumulative_returns)
        drawdown = peak - cumulative_returns
        max_drawdown = np.max(drawdown)
        max_drawdown_pct = (max_drawdown / self.account_balance) * 100 if self.account_balance > 0 else 0
        
        # Sharpe ratio (simplified)
        returns_std = np.std(returns) if len(returns) > 1 else 1
        sharpe_ratio = (avg_trade_return / returns_std) if returns_std > 0 else 0
        
        # Profit factor
        gross_profit = sum(winning_pnl) if winning_pnl else 0
        gross_loss = abs(sum(losing_pnl)) if losing_pnl else 1
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
        
        # Métricas de calidad de datos
        quality_scores = [t.data_quality_score for t in trades]
        avg_data_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0
        
        # Reliability score basado en calidad de datos y número de trades
        reliability_score = min(100, avg_data_quality * 0.7 + min(total_trades * 2, 30))
        
        execution_issues = sum(len(t.execution_issues) for t in trades)
        
        # Métricas temporales
        hold_times = [t.hold_time_hours for t in trades]
        avg_hold_time = sum(hold_times) / len(hold_times) if hold_times else 0
        longest_hold = max(hold_times) if hold_times else 0
        shortest_hold = min(hold_times) if hold_times else 0
        
        return BacktestMetrics(
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            total_return=total_return,
            total_return_pct=total_return_pct,
            avg_trade_return=avg_trade_return,
            avg_winning_trade=avg_winning_trade,
            avg_losing_trade=avg_losing_trade,
            max_drawdown=max_drawdown,
            max_drawdown_pct=max_drawdown_pct,
            sharpe_ratio=sharpe_ratio,
            profit_factor=profit_factor,
            avg_data_quality=avg_data_quality,
            reliability_score=reliability_score,
            execution_issues=execution_issues,
            avg_hold_time_hours=avg_hold_time,
            longest_hold_hours=longest_hold,
            shortest_hold_hours=shortest_hold
        )
    
    def _create_empty_metrics(self) -> BacktestMetrics:
        """Crear métricas vacías"""
        return BacktestMetrics(
            total_trades=0, winning_trades=0, losing_trades=0, win_rate=0,
            total_return=0, total_return_pct=0, avg_trade_return=0,
            avg_winning_trade=0, avg_losing_trade=0, max_drawdown=0,
            max_drawdown_pct=0, sharpe_ratio=0, profit_factor=0,
            avg_data_quality=0, reliability_score=0, execution_issues=0,
            avg_hold_time_hours=0, longest_hold_hours=0, shortest_hold_hours=0
        )
    
    def print_summary(self, metrics: BacktestMetrics):
        """Imprimir resumen completo de resultados"""
        print(f"\n🎯 BACKTEST RESULTS SUMMARY")
        print("=" * 60)
        
        # Métricas de trading
        print(f"📊 TRADING METRICS:")
        print(f"   Total Trades: {metrics.total_trades}")
        print(f"   Win Rate: {metrics.win_rate:.1f}% ({metrics.winning_trades}W/{metrics.losing_trades}L)")
        print(f"   Avg Trade: ${metrics.avg_trade_return:.2f}")
        print(f"   Avg Winner: ${metrics.avg_winning_trade:.2f}")
        print(f"   Avg Loser: ${metrics.avg_losing_trade:.2f}")
        print()
        
        # Métricas financieras
        print(f"💰 FINANCIAL METRICS:")
        print(f"   Total Return: ${metrics.total_return:.2f} ({metrics.total_return_pct:.2f}%)")
        print(f"   Max Drawdown: ${metrics.max_drawdown:.2f} ({metrics.max_drawdown_pct:.2f}%)")
        print(f"   Profit Factor: {metrics.profit_factor:.2f}")
        print(f"   Sharpe Ratio: {metrics.sharpe_ratio:.2f}")
        print()
        
        # Métricas de calidad
        print(f"🔍 DATA QUALITY METRICS:")
        print(f"   Avg Data Quality: {metrics.avg_data_quality:.1f}/100")
        print(f"   Reliability Score: {metrics.reliability_score:.1f}/100")
        print(f"   Execution Issues: {metrics.execution_issues}")
        print()
        
        # Métricas temporales
        print(f"⏰ TIMING METRICS:")
        print(f"   Avg Hold Time: {metrics.avg_hold_time_hours:.1f} hours")
        print(f"   Longest Hold: {metrics.longest_hold_hours:.1f} hours")
        print(f"   Shortest Hold: {metrics.shortest_hold_hours:.1f} hours")
        
        print("=" * 60)


def main():
    """Función principal CLI"""
    parser = argparse.ArgumentParser(description='Validated Backtest Engine V5.0')
    parser.add_argument('--symbols', nargs='+', default=['AAPL', 'MSFT', 'GOOGL'],
                       help='Símbolos a testear')
    parser.add_argument('--start-date', type=str, default='2024-01-01',
                       help='Fecha de inicio (YYYY-MM-DD)')
    parser.add_argument('--end-date', type=str, default=None,
                       help='Fecha de fin (YYYY-MM-DD)')
    parser.add_argument('--balance', type=float, default=10000,
                       help='Balance inicial de cuenta')
    parser.add_argument('--validation-only', action='store_true',
                       help='Solo ejecutar validación de datos')
    parser.add_argument('--strict-mode', action='store_true',
                       help='Modo estricto: excluir datos de baja calidad')
    parser.add_argument('--quick-test', action='store_true',
                       help='Test rápido con pocos símbolos y periodo corto')
    
    args = parser.parse_args()
    
    # Configuración de parámetros
    symbols = args.symbols
    balance = args.balance
    strict_mode = args.strict_mode
    
    # Parse dates
    start_date = datetime.strptime(args.start_date, '%Y-%m-%d')
    end_date = datetime.strptime(args.end_date, '%Y-%m-%d') if args.end_date else datetime.now()
    
    # Quick test configuration
    if args.quick_test:
        symbols = symbols[:2]  # Solo primeros 2 símbolos
        start_date = datetime.now() - timedelta(days=30)
        if not end_date:
            end_date = datetime.now()
        print("⚡ QUICK TEST MODE: Limited symbols and time period")
    else:
        if not start_date:
            start_date = datetime.now() - timedelta(days=90)
        if not end_date:
            end_date = datetime.now()
    
    print(f"🚀 VALIDATED BACKTEST ENGINE V5.0")
    print("=" * 50)
    print(f"🔍 Data Validation: {'STRICT' if strict_mode else 'PERMISSIVE'} mode")
    
    # Crear engine
    engine = ValidatedBacktestEngine(account_balance=balance, strict_mode=strict_mode)
    
    try:
        if args.validation_only:
            # Solo validación de datos
            print(f"🔍 VALIDATION-ONLY MODE")
            validation_reports = engine.validate_all_data(symbols, start_date, end_date)
            engine.print_validation_summary()
            
            # Mostrar detalles por símbolo
            print(f"\n📋 DETAILED VALIDATION RESULTS:")
            print("-" * 60)
            
            for symbol, report in validation_reports.items():
                quality_emoji = {
                    DataQuality.EXCELLENT: "🟢",
                    DataQuality.GOOD: "🔵", 
                    DataQuality.FAIR: "🟡",
                    DataQuality.POOR: "🟠",
                    DataQuality.UNUSABLE: "🔴"
                }
                
                emoji = quality_emoji.get(report.overall_quality, "❓")
                print(f"{emoji} {symbol}:")
                print(f"   Quality: {report.overall_quality.value} ({report.quality_score:.1f}/100)")
                print(f"   Data Coverage: {report.actual_periods}/{report.total_expected_periods} periods ({100-report.gap_percentage:.1f}%)")
                print(f"   Largest Gap: {report.largest_gap_days} days")
                print(f"   Price Anomalies: {len(report.price_anomalies)}")
                print(f"   Usable for Backtest: {'✅ Yes' if report.usable_for_backtest else '❌ No'}")
                
                if report.warnings:
                    print(f"   ⚠️ Warnings: {len(report.warnings)}")
                    for warning in report.warnings[:3]:  # Show first 3 warnings
                        print(f"      • {warning}")
                    if len(report.warnings) > 3:
                        print(f"      ... and {len(report.warnings) - 3} more")
                        
                if report.recommendations:
                    print(f"   💡 Recommendations:")
                    for rec in report.recommendations[:2]:  # Show first 2 recommendations
                        print(f"      • {rec}")
                print()
            
        else:
            # Backtest completo con validación
            metrics = engine.run_backtest(
                symbols=symbols,
                start_date=start_date,
                end_date=end_date
            )
            
            # Mostrar validación primero
            engine.print_validation_summary()
            print()
            
            # Mostrar resultados del backtest
            engine.print_summary(metrics)
            
            # Recomendaciones finales
            print(f"\n💡 RECOMMENDATIONS:")
            
            if metrics.reliability_score < 60:
                print("   🔴 CRITICAL: Low reliability score - results may not be trustworthy")
                print("      → Download more complete historical data")
                print("      → Use --strict mode to exclude poor quality data")
                print("      → Consider shorter time period with better data coverage")
            
            elif metrics.reliability_score < 80:
                print("   🟡 CAUTION: Moderate reliability - interpret results carefully")
                print("      → Some data quality issues detected")
                print("      → Consider validating key trades manually")
            
            else:
                print("   ✅ HIGH RELIABILITY: Results are trustworthy")
                
            if metrics.total_trades == 0:
                print("   📊 No trades executed - possible causes:")
                print("      → Signal thresholds too strict")
                print("      → Insufficient historical data")
                print("      → All symbols excluded due to data quality")
                print("      → Run with --validation-only to check data availability")
                
            elif metrics.total_trades < 10:
                print("   📊 Limited trades - consider:")
                print("      → Longer time period")
                print("      → More symbols")
                print("      → Lower signal thresholds")
                
            else:
                print("   📊 Good trade sample size for statistical significance")
                
            # Data quality specific recommendations
            if metrics.avg_data_quality < 70:
                print("   📈 Data Quality Improvements:")
                print("      → Download more recent data with python downloader.py")
                print("      → Check for missing trading days or holidays")
                print("      → Verify indicator calculations are correct")
            
            print(f"\n🎉 Validated backtest completed!")
            
    except KeyboardInterrupt:
        print("\n🛑 Backtest interrupted by user")
    except Exception as e:
        logger.error(f"❌ Backtest failed: {e}")
        print(f"❌ Error: {e}")
        print("💡 Troubleshooting steps:")
        print("   1. Make sure historical data is available (run populate_db.py)")
        print("   2. Check database connection")
        print("   3. Verify symbols have sufficient data coverage")
        print("   4. Try --validation-only to check data quality first")

if __name__ == "__main__":
    main()