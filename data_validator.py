#!/usr/bin/env python3
"""
🔍 DATA VALIDATOR V3.1 - VALIDACIÓN PRE-BACKTESTING
==================================================

Validador robusto de calidad de datos antes de ejecutar backtesting.
Este es el último checkpoint que garantiza que los datos son confiables
para análisis histórico y simulaciones.

🎯 FUNCIONALIDADES:
- Validación exhaustiva de datos OHLCV
- Detección de gaps críticos para backtesting
- Verificación de continuidad 24/5
- Análisis de anomalías de precio/volumen
- Validación de extended hours data
- Scoring de calidad por símbolo
- Recomendaciones automáticas
- Reportes detallados HTML/JSON

🚦 CRITERIOS DE VALIDACIÓN:
- COMPLETENESS: >= 95% datos requeridos
- GAPS: < 5 gaps críticos por símbolo
- CONSISTENCIA OHLC: >= 98% barras válidas
- ANOMALÍAS: < 2% precios/volúmenes anómalos
- EXTENDED HOURS: Cobertura overnight verificada

🔧 USO:
- Standalone: python data_validator.py --symbol SPY
- Integrado: from data_validator import DataValidator
- Pre-backtest: validator.validate_for_backtesting(symbols)
"""

import pandas as pd
import numpy as np
import logging
from datetime import datetime, timedelta, time
from typing import Dict, List, Optional, Any, Tuple, Union
from dataclasses import dataclass, field
from enum import Enum
import json
from pathlib import Path
import sqlite3
import yfinance as yf

# Importaciones del sistema
try:
    import config
    from indicators import TechnicalIndicators
    from gap_detector import GapDetector, DataQualityReport
    from database.connection import get_connection, get_gap_reports
    
    SYSTEM_INTEGRATION = True
    logger = logging.getLogger(__name__)
    
except ImportError as e:
    # Modo standalone
    SYSTEM_INTEGRATION = False
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    logger.warning(f"Modo standalone - integración limitada: {e}")

class ValidationLevel(Enum):
    """Niveles de validación"""
    BASIC = "BASIC"           # Validación rápida esencial
    STANDARD = "STANDARD"     # Validación completa recomendada
    STRICT = "STRICT"         # Validación exhaustiva para backtesting crítico
    EXTENDED = "EXTENDED"     # Incluye validación de extended hours

class ValidationStatus(Enum):
    """Estados de validación"""
    PASSED = "PASSED"         # Apto para backtesting
    WARNING = "WARNING"       # Apto con advertencias
    FAILED = "FAILED"         # NO apto para backtesting
    CRITICAL = "CRITICAL"     # Datos corruptos o insuficientes

class ValidationType(Enum):
    """Tipos de validación específicos"""
    COMPLETENESS = "COMPLETENESS"
    GAPS_ANALYSIS = "GAPS_ANALYSIS" 
    OHLC_CONSISTENCY = "OHLC_CONSISTENCY"
    PRICE_ANOMALIES = "PRICE_ANOMALIES"
    VOLUME_VALIDATION = "VOLUME_VALIDATION"
    TEMPORAL_CONTINUITY = "TEMPORAL_CONTINUITY"
    EXTENDED_HOURS = "EXTENDED_HOURS"
    MARKET_SESSIONS = "MARKET_SESSIONS"

@dataclass
class ValidationResult:
    """Resultado de una validación específica"""
    validation_type: ValidationType
    status: ValidationStatus
    score: float  # 0-100
    details: Dict[str, Any]
    issues: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    execution_time_ms: float = 0

@dataclass
class SymbolValidationReport:
    """Reporte completo de validación por símbolo"""
    symbol: str
    validation_timestamp: datetime
    validation_level: ValidationLevel
    overall_status: ValidationStatus
    overall_score: float  # 0-100
    
    # Resultados por tipo de validación
    validation_results: Dict[ValidationType, ValidationResult] = field(default_factory=dict)
    
    # Métricas generales
    total_data_points: int = 0
    data_period: Tuple[datetime, datetime] = None
    extended_hours_coverage: float = 0  # % cobertura extended hours
    
    # Decisión final
    backtest_ready: bool = False
    critical_issues: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    
    # Metadatos
    data_source: str = "UNKNOWN"
    gaps_filled: int = 0
    validation_duration_ms: float = 0

class DataValidator:
    """
    Validador principal de calidad de datos para backtesting
    """
    
    def __init__(self, validation_level: ValidationLevel = ValidationLevel.STANDARD):
        """
        Inicializar validador
        
        Args:
            validation_level: Nivel de validación a aplicar
        """
        self.validation_level = validation_level
        self.validation_stats = {
            'total_validations': 0,
            'passed_validations': 0,
            'failed_validations': 0,
            'warnings_generated': 0
        }
        
        # Configuración de umbrales por nivel
        self.thresholds = self._get_thresholds_for_level(validation_level)
        
        # Componentes del sistema si están disponibles
        self.indicators = None
        self.gap_detector = None
        self.database_available = False
        
        if SYSTEM_INTEGRATION:
            try:
                self.indicators = TechnicalIndicators()
                self.gap_detector = GapDetector()
                
                # Verificar base de datos
                conn = get_connection()
                if conn:
                    conn.close()
                    self.database_available = True
                    
                logger.info("✅ Data Validator inicializado con integración completa")
            except Exception as e:
                logger.warning(f"⚠️ Integración parcial del sistema: {e}")
        
        logger.info(f"🔍 Data Validator V3.1 inicializado - Nivel: {validation_level.value}")
    
    def _get_thresholds_for_level(self, level: ValidationLevel) -> Dict[str, Any]:
        """Obtener umbrales de validación según el nivel"""
        thresholds = {
            ValidationLevel.BASIC: {
                'min_completeness_pct': 85.0,
                'max_critical_gaps': 10,
                'min_ohlc_consistency': 90.0,
                'max_price_anomalies_pct': 5.0,
                'max_volume_anomalies_pct': 10.0,
                'min_overall_score': 70.0
            },
            ValidationLevel.STANDARD: {
                'min_completeness_pct': 92.0,
                'max_critical_gaps': 5,
                'min_ohlc_consistency': 95.0,
                'max_price_anomalies_pct': 2.0,
                'max_volume_anomalies_pct': 5.0,
                'min_overall_score': 80.0
            },
            ValidationLevel.STRICT: {
                'min_completeness_pct': 98.0,
                'max_critical_gaps': 2,
                'min_ohlc_consistency': 98.0,
                'max_price_anomalies_pct': 1.0,
                'max_volume_anomalies_pct': 2.0,
                'min_overall_score': 90.0
            },
            ValidationLevel.EXTENDED: {
                'min_completeness_pct': 95.0,
                'max_critical_gaps': 3,
                'min_ohlc_consistency': 96.0,
                'max_price_anomalies_pct': 1.5,
                'max_volume_anomalies_pct': 3.0,
                'min_overall_score': 85.0,
                'min_extended_hours_coverage': 80.0,
                'max_overnight_gaps': 2
            }
        }
        
        return thresholds[level]
    
    def validate_symbol(self, symbol: str, 
                       data: Optional[pd.DataFrame] = None,
                       days_back: int = 30) -> SymbolValidationReport:
        """
        Validar datos de un símbolo específico
        
        Args:
            symbol: Símbolo a validar
            data: DataFrame con datos (opcional, se descarga si no se proporciona)
            days_back: Días de historial para validar
            
        Returns:
            Reporte completo de validación
        """
        start_time = datetime.now()
        
        try:
            logger.info(f"🔍 Iniciando validación de {symbol} - Nivel: {self.validation_level.value}")
            
            # Obtener datos si no se proporcionaron
            if data is None:
                data = self._get_symbol_data(symbol, days_back)
            
            if data is None or len(data) == 0:
                return self._create_failed_report(symbol, "No se pudieron obtener datos")
            
            # Crear reporte base
            report = SymbolValidationReport(
                symbol=symbol,
                validation_timestamp=start_time,
                validation_level=self.validation_level,
                overall_status=ValidationStatus.PASSED,
                overall_score=0.0,
                total_data_points=len(data),
                data_period=(data.index.min(), data.index.max()) if not data.empty else None,
                data_source="API" if self.indicators else "PROVIDED"
            )
            
            # Ejecutar validaciones según el nivel
            validation_results = {}
            
            # 1. Validación de completeness
            validation_results[ValidationType.COMPLETENESS] = self._validate_completeness(data, symbol)
            
            # 2. Análisis de gaps
            validation_results[ValidationType.GAPS_ANALYSIS] = self._validate_gaps(data, symbol)
            
            # 3. Consistencia OHLC
            validation_results[ValidationType.OHLC_CONSISTENCY] = self._validate_ohlc_consistency(data, symbol)
            
            # 4. Anomalías de precio
            validation_results[ValidationType.PRICE_ANOMALIES] = self._validate_price_anomalies(data, symbol)
            
            # 5. Validación de volumen
            validation_results[ValidationType.VOLUME_VALIDATION] = self._validate_volume(data, symbol)
            
            # 6. Continuidad temporal
            validation_results[ValidationType.TEMPORAL_CONTINUITY] = self._validate_temporal_continuity(data, symbol)
            
            # 7. Extended Hours (solo si el nivel lo requiere)
            if self.validation_level == ValidationLevel.EXTENDED:
                validation_results[ValidationType.EXTENDED_HOURS] = self._validate_extended_hours(data, symbol)
                validation_results[ValidationType.MARKET_SESSIONS] = self._validate_market_sessions(data, symbol)
            
            # Guardar resultados
            report.validation_results = validation_results
            
            # Calcular score general y status final
            overall_score, overall_status = self._calculate_overall_assessment(validation_results)
            report.overall_score = overall_score
            report.overall_status = overall_status
            
            # Determinar si es apto para backtesting
            report.backtest_ready = self._is_backtest_ready(report)
            
            # Consolidar issues, warnings y recomendaciones
            report.critical_issues, report.warnings, report.recommendations = self._consolidate_feedback(validation_results)
            
            # Estadísticas adicionales
            if self.gap_detector and 'market_data' in dir(self.indicators):
                try:
                    # Contar gaps que fueron rellenados
                    gaps = self.gap_detector.detect_gaps_in_dataframe(data, symbol)
                    report.gaps_filled = len([g for g in gaps if getattr(g, 'is_fillable', False)])
                except Exception:
                    pass
            
            # Tiempo de ejecución
            execution_time = (datetime.now() - start_time).total_seconds() * 1000
            report.validation_duration_ms = execution_time
            
            # Actualizar estadísticas
            self.validation_stats['total_validations'] += 1
            if overall_status == ValidationStatus.PASSED:
                self.validation_stats['passed_validations'] += 1
            elif overall_status == ValidationStatus.FAILED:
                self.validation_stats['failed_validations'] += 1
            
            if report.warnings:
                self.validation_stats['warnings_generated'] += len(report.warnings)
            
            logger.info(f"✅ {symbol}: Validación completada - Score: {overall_score:.1f}/100, Status: {overall_status.value}")
            
            return report
            
        except Exception as e:
            logger.error(f"❌ Error validando {symbol}: {e}")
            return self._create_failed_report(symbol, f"Error durante validación: {str(e)}")
    
    def _get_symbol_data(self, symbol: str, days_back: int) -> Optional[pd.DataFrame]:
        """Obtener datos del símbolo para validación"""
        try:
            if self.indicators:
                # Usar sistema integrado
                indicators_data = self.indicators.get_all_indicators(symbol)
                if 'market_data' in indicators_data:
                    return indicators_data['market_data']
            
            # Fallback: usar yfinance directamente
            logger.info(f"📊 Descargando datos para {symbol} via yfinance fallback")
            ticker = yf.Ticker(symbol)
            
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days_back)
            
            data = ticker.history(
                start=start_date,
                end=end_date,
                interval="15m",
                auto_adjust=True,
                prepost=True  # Incluir extended hours
            )
            
            if data.empty:
                return None
            
            # Normalizar nombres de columnas
            data.columns = ['Open', 'High', 'Low', 'Close', 'Volume']
            return data
            
        except Exception as e:
            logger.error(f"❌ Error obteniendo datos para {symbol}: {e}")
            return None
    
    def _validate_completeness(self, data: pd.DataFrame, symbol: str) -> ValidationResult:
        """Validar completeness de los datos"""
        start_time = datetime.now()
        
        try:
            # Calcular completeness esperado vs actual
            data_period = (data.index.max() - data.index.min()).total_seconds() / 60  # minutos
            expected_points = int(data_period / 15)  # Asumiendo 15min intervals
            actual_points = len(data)
            
            completeness_pct = min(100.0, (actual_points / max(1, expected_points)) * 100)
            
            # Evaluar según umbrales
            threshold = self.thresholds['min_completeness_pct']
            
            if completeness_pct >= threshold:
                status = ValidationStatus.PASSED
                issues = []
            elif completeness_pct >= threshold * 0.9:  # 90% del threshold
                status = ValidationStatus.WARNING
                issues = [f"Completeness {completeness_pct:.1f}% ligeramente bajo"]
            else:
                status = ValidationStatus.FAILED
                issues = [f"Completeness {completeness_pct:.1f}% insuficiente (req: {threshold}%)"]
            
            # Score (0-100)
            score = min(100.0, completeness_pct)
            
            # Recomendaciones
            recommendations = []
            if completeness_pct < 95:
                recommendations.append("Considerar re-descarga de datos")
            if completeness_pct < 85:
                recommendations.append("Verificar fuente de datos y configuración extended hours")
            
            return ValidationResult(
                validation_type=ValidationType.COMPLETENESS,
                status=status,
                score=score,
                details={
                    'expected_points': expected_points,
                    'actual_points': actual_points,
                    'completeness_pct': completeness_pct,
                    'data_period_hours': data_period / 60
                },
                issues=issues,
                recommendations=recommendations,
                execution_time_ms=(datetime.now() - start_time).total_seconds() * 1000
            )
            
        except Exception as e:
            return ValidationResult(
                validation_type=ValidationType.COMPLETENESS,
                status=ValidationStatus.CRITICAL,
                score=0.0,
                details={'error': str(e)},
                issues=[f"Error en validación de completeness: {e}"],
                execution_time_ms=(datetime.now() - start_time).total_seconds() * 1000
            )
    
    def _validate_gaps(self, data: pd.DataFrame, symbol: str) -> ValidationResult:
        """Validar gaps en los datos"""
        start_time = datetime.now()
        
        try:
            gaps_detected = []
            critical_gaps = 0
            
            if self.gap_detector:
                # Usar gap detector del sistema
                gaps = self.gap_detector.detect_gaps_in_dataframe(data, symbol, 15)
                gaps_detected = gaps
                
                # Contar gaps críticos (que pueden afectar backtesting)
                critical_gaps = len([g for g in gaps if g.severity.value in ['HIGH', 'CRITICAL']])
            else:
                # Detección básica de gaps
                time_diffs = data.index.to_series().diff()
                large_gaps = time_diffs[time_diffs > timedelta(hours=4)]  # Gaps > 4 horas
                critical_gaps = len(large_gaps)
            
            # Evaluar según umbrales
            max_critical_gaps = self.thresholds['max_critical_gaps']
            
            if critical_gaps == 0:
                status = ValidationStatus.PASSED
                score = 100.0
                issues = []
            elif critical_gaps <= max_critical_gaps:
                status = ValidationStatus.WARNING
                score = max(70.0, 100.0 - (critical_gaps * 10))
                issues = [f"{critical_gaps} gaps críticos detectados"]
            else:
                status = ValidationStatus.FAILED
                score = max(0.0, 50.0 - (critical_gaps * 5))
                issues = [f"{critical_gaps} gaps críticos exceden límite ({max_critical_gaps})"]
            
            # Recomendaciones
            recommendations = []
            if critical_gaps > 0:
                recommendations.append("Revisar y rellenar gaps críticos antes de backtesting")
            if critical_gaps > 5:
                recommendations.append("Considerar usar datos de mayor calidad o períodos alternativos")
            
            return ValidationResult(
                validation_type=ValidationType.GAPS_ANALYSIS,
                status=status,
                score=score,
                details={
                    'total_gaps': len(gaps_detected),
                    'critical_gaps': critical_gaps,
                    'max_allowed_critical': max_critical_gaps,
                    'gaps_list': [str(g) for g in gaps_detected[:5]]  # Primeros 5
                },
                issues=issues,
                recommendations=recommendations,
                execution_time_ms=(datetime.now() - start_time).total_seconds() * 1000
            )
            
        except Exception as e:
            return ValidationResult(
                validation_type=ValidationType.GAPS_ANALYSIS,
                status=ValidationStatus.CRITICAL,
                score=0.0,
                details={'error': str(e)},
                issues=[f"Error en análisis de gaps: {e}"],
                execution_time_ms=(datetime.now() - start_time).total_seconds() * 1000
            )
    
    def _validate_ohlc_consistency(self, data: pd.DataFrame, symbol: str) -> ValidationResult:
        """Validar consistencia de datos OHLC"""
        start_time = datetime.now()
        
        try:
            total_bars = len(data)
            inconsistent_bars = 0
            issues = []
            
            # Verificar que High >= Low, Open, Close
            high_low_issues = (data['High'] < data['Low']).sum()
            high_open_issues = (data['High'] < data['Open']).sum()
            high_close_issues = (data['High'] < data['Close']).sum()
            
            # Verificar que Low <= High, Open, Close
            low_open_issues = (data['Low'] > data['Open']).sum()
            low_close_issues = (data['Low'] > data['Close']).sum()
            
            # Verificar precios no negativos
            negative_prices = (
                (data['Open'] <= 0).sum() +
                (data['High'] <= 0).sum() +
                (data['Low'] <= 0).sum() +
                (data['Close'] <= 0).sum()
            )
            
            inconsistent_bars = high_low_issues + high_open_issues + high_close_issues + low_open_issues + low_close_issues + negative_prices
            
            # Calcular consistencia
            consistency_pct = max(0.0, ((total_bars - inconsistent_bars) / max(1, total_bars)) * 100)
            
            # Evaluar según umbrales
            threshold = self.thresholds['min_ohlc_consistency']
            
            if consistency_pct >= threshold:
                status = ValidationStatus.PASSED
                score = consistency_pct
            elif consistency_pct >= threshold * 0.95:  # 95% del threshold
                status = ValidationStatus.WARNING
                score = consistency_pct * 0.9
                issues.append(f"Consistencia OHLC {consistency_pct:.1f}% ligeramente baja")
            else:
                status = ValidationStatus.FAILED
                score = consistency_pct * 0.5
                issues.append(f"Consistencia OHLC {consistency_pct:.1f}% insuficiente (req: {threshold}%)")
            
            # Issues específicos
            if high_low_issues > 0:
                issues.append(f"{high_low_issues} barras con High < Low")
            if negative_prices > 0:
                issues.append(f"{negative_prices} precios negativos o cero")
            
            # Recomendaciones
            recommendations = []
            if inconsistent_bars > 0:
                recommendations.append("Limpiar inconsistencias OHLC antes de backtesting")
            if inconsistent_bars > total_bars * 0.05:  # > 5%
                recommendations.append("Verificar fuente de datos - alta tasa de inconsistencias")
            
            return ValidationResult(
                validation_type=ValidationType.OHLC_CONSISTENCY,
                status=status,
                score=score,
                details={
                    'total_bars': total_bars,
                    'inconsistent_bars': inconsistent_bars,
                    'consistency_pct': consistency_pct,
                    'high_low_issues': high_low_issues,
                    'negative_prices': negative_prices
                },
                issues=issues,
                recommendations=recommendations,
                execution_time_ms=(datetime.now() - start_time).total_seconds() * 1000
            )
            
        except Exception as e:
            return ValidationResult(
                validation_type=ValidationType.OHLC_CONSISTENCY,
                status=ValidationStatus.CRITICAL,
                score=0.0,
                details={'error': str(e)},
                issues=[f"Error en validación OHLC: {e}"],
                execution_time_ms=(datetime.now() - start_time).total_seconds() * 1000
            )
    
    def _validate_price_anomalies(self, data: pd.DataFrame, symbol: str) -> ValidationResult:
        """Validar anomalías en precios"""
        start_time = datetime.now()
        
        try:
            total_bars = len(data)
            anomalies = 0
            issues = []
            
            # Calcular cambios porcentuales extremos
            price_changes = data['Close'].pct_change().abs()
            
            # Detectar cambios extremos (>20% en un período)
            extreme_changes = (price_changes > 0.20).sum()
            
            # Detectar spikes de volatilidad
            volatility = data['High'] / data['Low'] - 1
            extreme_volatility = (volatility > 0.15).sum()  # >15% range intrabar
            
            # Detectar precios idénticos consecutivos (posible data freeze)
            identical_closes = (data['Close'].diff() == 0).sum()
            identical_pct = (identical_closes / max(1, total_bars)) * 100
            
            anomalies = extreme_changes + extreme_volatility
            anomalies_pct = (anomalies / max(1, total_bars)) * 100
            
            # Evaluar según umbrales
            threshold = self.thresholds['max_price_anomalies_pct']
            
            if anomalies_pct <= threshold:
                status = ValidationStatus.PASSED
                score = max(80.0, 100.0 - anomalies_pct * 5)
            elif anomalies_pct <= threshold * 2:  # Doble del threshold
                status = ValidationStatus.WARNING
                score = max(60.0, 80.0 - anomalies_pct * 3)
                issues.append(f"Anomalías de precio {anomalies_pct:.1f}% elevadas")
            else:
                status = ValidationStatus.FAILED
                score = max(0.0, 40.0 - anomalies_pct * 2)
                issues.append(f"Anomalías de precio {anomalies_pct:.1f}% excesivas (max: {threshold}%)")
            
            # Issues específicos
            if extreme_changes > 0:
                issues.append(f"{extreme_changes} cambios de precio extremos (>20%)")
            if extreme_volatility > 0:
                issues.append(f"{extreme_volatility} spikes de volatilidad intrabar")
            if identical_pct > 10:
                issues.append(f"{identical_pct:.1f}% precios idénticos consecutivos")
            
            # Recomendaciones
            recommendations = []
            if anomalies_pct > 5:
                recommendations.append("Investigar anomalías antes de backtesting")
            if identical_pct > 15:
                recommendations.append("Verificar data freezes - posible problema de feed")
            
            return ValidationResult(
                validation_type=ValidationType.PRICE_ANOMALIES,
                status=status,
                score=score,
                details={
                    'total_bars': total_bars,
                    'anomalies_count': anomalies,
                    'anomalies_pct': anomalies_pct,
                    'extreme_changes': extreme_changes,
                    'extreme_volatility': extreme_volatility,
                    'identical_closes_pct': identical_pct
                },
                issues=issues,
                recommendations=recommendations,
                execution_time_ms=(datetime.now() - start_time).total_seconds() * 1000
            )
            
        except Exception as e:
            return ValidationResult(
                validation_type=ValidationType.PRICE_ANOMALIES,
                status=ValidationStatus.CRITICAL,
                score=0.0,
                details={'error': str(e)},
                issues=[f"Error en validación de anomalías: {e}"],
                execution_time_ms=(datetime.now() - start_time).total_seconds() * 1000
            )
    
    def _validate_volume(self, data: pd.DataFrame, symbol: str) -> ValidationResult:
        """Validar calidad de datos de volumen"""
        start_time = datetime.now()
        
        try:
            total_bars = len(data)
            volume_issues = 0
            issues = []
            
            # Verificar volúmenes válidos
            zero_volume = (data['Volume'] == 0).sum()
            negative_volume = (data['Volume'] < 0).sum()
            
            # Detectar spikes de volumen extremos
            volume_median = data['Volume'].median()
            if volume_median > 0:
                extreme_volume = (data['Volume'] > volume_median * 20).sum()  # >20x mediana
            else:
                extreme_volume = 0
            
            volume_issues = zero_volume + negative_volume + extreme_volume
            volume_issues_pct = (volume_issues / max(1, total_bars)) * 100
            
            # Evaluar según umbrales
            threshold = self.thresholds['max_volume_anomalies_pct']
            
            if volume_issues_pct <= threshold:
                status = ValidationStatus.PASSED
                score = max(80.0, 100.0 - volume_issues_pct * 2)
            elif volume_issues_pct <= threshold * 2:
                status = ValidationStatus.WARNING
                score = max(60.0, 80.0 - volume_issues_pct)
                issues.append(f"Issues de volumen {volume_issues_pct:.1f}% moderados")
            else:
                status = ValidationStatus.FAILED
                score = max(0.0, 40.0 - volume_issues_pct)
                issues.append(f"Issues de volumen {volume_issues_pct:.1f}% excesivos (max: {threshold}%)")
            
            # Issues específicos
            if zero_volume > 0:
                issues.append(f"{zero_volume} barras con volumen cero")
            if negative_volume > 0:
                issues.append(f"{negative_volume} volúmenes negativos")
            if extreme_volume > 0:
                issues.append(f"{extreme_volume} spikes de volumen extremos")
            
            # Recomendaciones
            recommendations = []
            if zero_volume > total_bars * 0.1:  # >10% zero volume
                recommendations.append("Alto % de volumen cero - verificar extended hours data")
            if negative_volume > 0:
                recommendations.append("Corregir volúmenes negativos antes de backtesting")
            
            return ValidationResult(
                validation_type=ValidationType.VOLUME_VALIDATION,
                status=status,
                score=score,
                details={
                    'total_bars': total_bars,
                    'volume_issues': volume_issues,
                    'volume_issues_pct': volume_issues_pct,
                    'zero_volume': zero_volume,
                    'negative_volume': negative_volume,
                    'extreme_volume': extreme_volume,
                    'volume_median': volume_median
                },
                issues=issues,
                recommendations=recommendations,
                execution_time_ms=(datetime.now() - start_time).total_seconds() * 1000
            )
            
        except Exception as e:
            return ValidationResult(
                validation_type=ValidationType.VOLUME_VALIDATION,
                status=ValidationStatus.CRITICAL,
                score=0.0,
                details={'error': str(e)},
                issues=[f"Error en validación de volumen: {e}"],
                execution_time_ms=(datetime.now() - start_time).total_seconds() * 1000
            )
    
    def _validate_temporal_continuity(self, data: pd.DataFrame, symbol: str) -> ValidationResult:
        """Validar continuidad temporal de los datos"""
        start_time = datetime.now()
        
        try:
            issues = []
            
            # Verificar ordenamiento temporal
            is_sorted = data.index.is_monotonic_increasing
            
            # Detectar duplicados de timestamp
            duplicates = data.index.duplicated().sum()
            
            # Verificar intervalos esperados (15 min)
            time_diffs = data.index.to_series().diff()[1:]
            expected_interval = timedelta(minutes=15)
            
            # Contar intervalos normales vs anómalos
            normal_intervals = ((time_diffs >= expected_interval * 0.8) & 
                              (time_diffs <= expected_interval * 1.2)).sum()
            total_intervals = len(time_diffs)
            
            continuity_pct = (normal_intervals / max(1, total_intervals)) * 100
            
            # Evaluar continuidad
            if continuity_pct >= 90 and is_sorted and duplicates == 0:
                status = ValidationStatus.PASSED
                score = min(100.0, continuity_pct + 5)
            elif continuity_pct >= 80 and is_sorted:
                status = ValidationStatus.WARNING
                score = continuity_pct
                issues.append(f"Continuidad temporal {continuity_pct:.1f}% aceptable")
            else:
                status = ValidationStatus.FAILED
                score = max(0.0, continuity_pct - 20)
                issues.append(f"Continuidad temporal {continuity_pct:.1f}% insuficiente")
            
            # Issues específicos
            if not is_sorted:
                issues.append("Datos no están ordenados cronológicamente")
            if duplicates > 0:
                issues.append(f"{duplicates} timestamps duplicados")
            
            # Recomendaciones
            recommendations = []
            if not is_sorted:
                recommendations.append("Ordenar datos por timestamp antes de backtesting")
            if duplicates > 0:
                recommendations.append("Eliminar timestamps duplicados")
            if continuity_pct < 85:
                recommendations.append("Re-descargar datos para mejorar continuidad")
            
            return ValidationResult(
                validation_type=ValidationType.TEMPORAL_CONTINUITY,
                status=status,
                score=score,
                details={
                    'is_sorted': is_sorted,
                    'duplicates': duplicates,
                    'continuity_pct': continuity_pct,
                    'normal_intervals': normal_intervals,
                    'total_intervals': total_intervals
                },
                issues=issues,
                recommendations=recommendations,
                execution_time_ms=(datetime.now() - start_time).total_seconds() * 1000
            )
            
        except Exception as e:
            return ValidationResult(
                validation_type=ValidationType.TEMPORAL_CONTINUITY,
                status=ValidationStatus.CRITICAL,
                score=0.0,
                details={'error': str(e)},
                issues=[f"Error en validación temporal: {e}"],
                execution_time_ms=(datetime.now() - start_time).total_seconds() * 1000
            )
    
    def _validate_extended_hours(self, data: pd.DataFrame, symbol: str) -> ValidationResult:
        """Validar cobertura de extended hours (solo para nivel EXTENDED)"""
        start_time = datetime.now()
        
        try:
            issues = []
            
            # Convertir index a timezone-aware si no lo está
            if data.index.tz is None:
                data_tz = data.index.tz_localize('UTC').tz_convert('US/Eastern')
            else:
                data_tz = data.index.tz_convert('US/Eastern')
            
            # Clasificar datos por sesión
            regular_hours = []
            pre_market = []
            post_market = []
            overnight = []
            
            for timestamp in data_tz:
                hour = timestamp.hour
                
                if 9 <= hour < 16:  # 9:30 AM - 4:00 PM aproximado
                    regular_hours.append(timestamp)
                elif 4 <= hour < 9:  # 4:00 AM - 9:30 AM
                    pre_market.append(timestamp)
                elif 16 <= hour < 20:  # 4:00 PM - 8:00 PM
                    post_market.append(timestamp)
                else:  # 8:00 PM - 4:00 AM
                    overnight.append(timestamp)
            
            # Calcular cobertura
            total_points = len(data)
            regular_pct = (len(regular_hours) / max(1, total_points)) * 100
            pre_market_pct = (len(pre_market) / max(1, total_points)) * 100
            post_market_pct = (len(post_market) / max(1, total_points)) * 100
            overnight_pct = (len(overnight) / max(1, total_points)) * 100
            
            extended_hours_coverage = pre_market_pct + post_market_pct + overnight_pct
            
            # Evaluar según umbrales
            min_coverage = self.thresholds.get('min_extended_hours_coverage', 80.0)
            
            if extended_hours_coverage >= min_coverage:
                status = ValidationStatus.PASSED
                score = min(100.0, extended_hours_coverage)
            elif extended_hours_coverage >= min_coverage * 0.8:
                status = ValidationStatus.WARNING
                score = extended_hours_coverage * 0.9
                issues.append(f"Cobertura extended hours {extended_hours_coverage:.1f}% limitada")
            else:
                status = ValidationStatus.FAILED
                score = extended_hours_coverage * 0.5
                issues.append(f"Cobertura extended hours {extended_hours_coverage:.1f}% insuficiente")
            
            # Issues específicos
            if pre_market_pct < 5:
                issues.append("Datos pre-market insuficientes")
            if post_market_pct < 5:
                issues.append("Datos post-market insuficientes")
            if overnight_pct < 2:
                issues.append("Datos overnight ausentes")
            
            # Recomendaciones
            recommendations = []
            if extended_hours_coverage < 70:
                recommendations.append("Habilitar extended hours en descarga de datos")
            if overnight_pct == 0:
                recommendations.append("Configurar recolección de datos overnight")
            
            return ValidationResult(
                validation_type=ValidationType.EXTENDED_HOURS,
                status=status,
                score=score,
                details={
                    'extended_hours_coverage': extended_hours_coverage,
                    'regular_hours_pct': regular_pct,
                    'pre_market_pct': pre_market_pct,
                    'post_market_pct': post_market_pct,
                    'overnight_pct': overnight_pct,
                    'min_required_coverage': min_coverage
                },
                issues=issues,
                recommendations=recommendations,
                execution_time_ms=(datetime.now() - start_time).total_seconds() * 1000
            )
            
        except Exception as e:
            return ValidationResult(
                validation_type=ValidationType.EXTENDED_HOURS,
                status=ValidationStatus.CRITICAL,
                score=0.0,
                details={'error': str(e)},
                issues=[f"Error en validación extended hours: {e}"],
                execution_time_ms=(datetime.now() - start_time).total_seconds() * 1000
            )
    
    def _validate_market_sessions(self, data: pd.DataFrame, symbol: str) -> ValidationResult:
        """Validar representación adecuada de sesiones de mercado"""
        start_time = datetime.now()
        
        try:
            issues = []
            
            # Agrupar datos por día de la semana
            if data.index.tz is None:
                data_tz = data.index.tz_localize('UTC').tz_convert('US/Eastern')
            else:
                data_tz = data.index.tz_convert('US/Eastern')
            
            weekdays = data_tz.weekday  # 0=Monday, 6=Sunday
            
            # Contar datos por día de semana
            weekday_counts = {}
            for day in range(7):
                count = (weekdays == day).sum()
                weekday_counts[day] = count
            
            # Verificar distribución razonable (lunes-viernes)
            trading_days = sum(weekday_counts[day] for day in range(5))  # Mon-Fri
            weekend_days = weekday_counts[5] + weekday_counts[6]  # Sat-Sun
            
            if trading_days == 0:
                status = ValidationStatus.FAILED
                score = 0.0
                issues.append("No hay datos de días de trading")
            else:
                # Evaluar distribución
                weekend_ratio = weekend_days / max(1, trading_days + weekend_days)
                
                if weekend_ratio < 0.1:  # <10% weekend data es normal
                    status = ValidationStatus.PASSED
                    score = 90.0
                elif weekend_ratio < 0.3:
                    status = ValidationStatus.WARNING
                    score = 75.0
                    issues.append(f"Datos de fin de semana {weekend_ratio*100:.1f}% elevados")
                else:
                    status = ValidationStatus.WARNING
                    score = 60.0
                    issues.append(f"Datos de fin de semana {weekend_ratio*100:.1f}% muy altos")
            
            # Verificar presencia de días trading principales
            missing_weekdays = [day for day in range(5) if weekday_counts[day] == 0]
            if missing_weekdays:
                day_names = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie']
                missing_names = [day_names[day] for day in missing_weekdays]
                issues.append(f"Faltan datos de: {', '.join(missing_names)}")
                score = max(score * 0.8, 40.0)
            
            # Recomendaciones
            recommendations = []
            if missing_weekdays:
                recommendations.append("Asegurar cobertura de todos los días de trading")
            if weekend_ratio > 0.2:
                recommendations.append("Revisar filtros de días de trading")
            
            return ValidationResult(
                validation_type=ValidationType.MARKET_SESSIONS,
                status=status,
                score=score,
                details={
                    'weekday_counts': weekday_counts,
                    'trading_days_data': trading_days,
                    'weekend_data': weekend_days,
                    'weekend_ratio': weekend_ratio,
                    'missing_weekdays': missing_weekdays
                },
                issues=issues,
                recommendations=recommendations,
                execution_time_ms=(datetime.now() - start_time).total_seconds() * 1000
            )
            
        except Exception as e:
            return ValidationResult(
                validation_type=ValidationType.MARKET_SESSIONS,
                status=ValidationStatus.CRITICAL,
                score=0.0,
                details={'error': str(e)},
                issues=[f"Error en validación de sesiones: {e}"],
                execution_time_ms=(datetime.now() - start_time).total_seconds() * 1000
            )
    
    def _calculate_overall_assessment(self, validation_results: Dict[ValidationType, ValidationResult]) -> Tuple[float, ValidationStatus]:
        """Calcular evaluación general y status final"""
        if not validation_results:
            return 0.0, ValidationStatus.CRITICAL
        
        # Pesos por tipo de validación
        weights = {
            ValidationType.COMPLETENESS: 0.25,
            ValidationType.GAPS_ANALYSIS: 0.20,
            ValidationType.OHLC_CONSISTENCY: 0.20,
            ValidationType.PRICE_ANOMALIES: 0.15,
            ValidationType.VOLUME_VALIDATION: 0.10,
            ValidationType.TEMPORAL_CONTINUITY: 0.10,
            ValidationType.EXTENDED_HOURS: 0.05,  # Solo para nivel EXTENDED
            ValidationType.MARKET_SESSIONS: 0.05   # Solo para nivel EXTENDED
        }
        
        # Calcular score ponderado
        total_score = 0.0
        total_weight = 0.0
        critical_count = 0
        failed_count = 0
        
        for validation_type, result in validation_results.items():
            weight = weights.get(validation_type, 0.1)
            total_score += result.score * weight
            total_weight += weight
            
            if result.status == ValidationStatus.CRITICAL:
                critical_count += 1
            elif result.status == ValidationStatus.FAILED:
                failed_count += 1
        
        # Normalizar score
        overall_score = total_score / max(total_weight, 1.0)
        
        # Determinar status final
        if critical_count > 0:
            overall_status = ValidationStatus.CRITICAL
        elif failed_count > 0:
            overall_status = ValidationStatus.FAILED
        elif overall_score >= self.thresholds['min_overall_score']:
            overall_status = ValidationStatus.PASSED
        else:
            overall_status = ValidationStatus.WARNING
        
        return overall_score, overall_status
    
    def _is_backtest_ready(self, report: SymbolValidationReport) -> bool:
        """Determinar si el símbolo está listo para backtesting"""
        # Criterios básicos
        if report.overall_status == ValidationStatus.CRITICAL:
            return False
        
        if report.overall_status == ValidationStatus.FAILED:
            return False
        
        if report.overall_score < self.thresholds['min_overall_score']:
            return False
        
        # Verificar validaciones críticas específicas
        critical_validations = [
            ValidationType.COMPLETENESS,
            ValidationType.OHLC_CONSISTENCY,
            ValidationType.TEMPORAL_CONTINUITY
        ]
        
        for validation_type in critical_validations:
            if validation_type in report.validation_results:
                result = report.validation_results[validation_type]
                if result.status in [ValidationStatus.CRITICAL, ValidationStatus.FAILED]:
                    return False
        
        return True
    
    def _consolidate_feedback(self, validation_results: Dict[ValidationType, ValidationResult]) -> Tuple[List[str], List[str], List[str]]:
        """Consolidar issues, warnings y recomendaciones"""
        critical_issues = []
        warnings = []
        recommendations = []
        
        for validation_type, result in validation_results.items():
            if result.status == ValidationStatus.CRITICAL:
                critical_issues.extend(result.issues)
            elif result.status == ValidationStatus.FAILED:
                critical_issues.extend(result.issues)
            elif result.status == ValidationStatus.WARNING:
                warnings.extend(result.issues)
            
            recommendations.extend(result.recommendations)
        
        # Eliminar duplicados manteniendo orden
        critical_issues = list(dict.fromkeys(critical_issues))
        warnings = list(dict.fromkeys(warnings))
        recommendations = list(dict.fromkeys(recommendations))
        
        return critical_issues, warnings, recommendations
    
    def _create_failed_report(self, symbol: str, error_message: str) -> SymbolValidationReport:
        """Crear reporte fallido"""
        return SymbolValidationReport(
            symbol=symbol,
            validation_timestamp=datetime.now(),
            validation_level=self.validation_level,
            overall_status=ValidationStatus.CRITICAL,
            overall_score=0.0,
            backtest_ready=False,
            critical_issues=[error_message],
            data_source="ERROR"
        )
    
    def validate_multiple_symbols(self, symbols: List[str], 
                                 days_back: int = 30) -> Dict[str, SymbolValidationReport]:
        """
        Validar múltiples símbolos
        
        Args:
            symbols: Lista de símbolos a validar
            days_back: Días de historial
            
        Returns:
            Diccionario {symbol: report}
        """
        logger.info(f"🔍 Iniciando validación masiva de {len(symbols)} símbolos")
        
        reports = {}
        
        for i, symbol in enumerate(symbols, 1):
            try:
                logger.info(f"📊 Validando {symbol} ({i}/{len(symbols)})")
                report = self.validate_symbol(symbol, days_back=days_back)
                reports[symbol] = report
                
                # Log resultado
                status_emoji = {
                    ValidationStatus.PASSED: "✅",
                    ValidationStatus.WARNING: "⚠️",
                    ValidationStatus.FAILED: "❌",
                    ValidationStatus.CRITICAL: "🚨"
                }
                emoji = status_emoji.get(report.overall_status, "❓")
                logger.info(f"{emoji} {symbol}: {report.overall_score:.1f}/100 - {report.overall_status.value}")
                
            except Exception as e:
                logger.error(f"❌ Error validando {symbol}: {e}")
                reports[symbol] = self._create_failed_report(symbol, str(e))
        
        # Estadísticas finales
        passed = len([r for r in reports.values() if r.overall_status == ValidationStatus.PASSED])
        failed = len([r for r in reports.values() if r.overall_status in [ValidationStatus.FAILED, ValidationStatus.CRITICAL]])
        
        logger.info(f"📊 Validación completada: {passed} aprobados, {failed} fallidos de {len(symbols)} total")
        
        return reports
    
    def validate_for_backtesting(self, symbols: List[str], 
                                days_back: int = 30,
                                auto_filter: bool = True) -> Dict[str, Any]:
        """
        Validación específica para backtesting con recomendaciones automáticas
        
        Args:
            symbols: Símbolos a validar
            days_back: Días de historial
            auto_filter: Si True, filtra automáticamente símbolos no aptos
            
        Returns:
            Diccionario con resultados y recomendaciones
        """
        logger.info(f"🧪 Validación pre-backtesting de {len(symbols)} símbolos")
        
        # Validar todos los símbolos
        reports = self.validate_multiple_symbols(symbols, days_back)
        
        # Clasificar resultados
        backtest_ready = []
        warnings_symbols = []
        failed_symbols = []
        critical_symbols = []
        
        for symbol, report in reports.items():
            if report.backtest_ready:
                backtest_ready.append(symbol)
            elif report.overall_status == ValidationStatus.WARNING:
                warnings_symbols.append(symbol)
            elif report.overall_status == ValidationStatus.FAILED:
                failed_symbols.append(symbol)
            else:
                critical_symbols.append(symbol)
        
        # Recomendaciones generales
        general_recommendations = []
        
        if len(backtest_ready) < len(symbols) * 0.7:  # <70% aprobados
            general_recommendations.append("Considerar re-descarga de datos con extended hours")
        
        if critical_symbols:
            general_recommendations.append(f"Excluir símbolos críticos: {', '.join(critical_symbols)}")
        
        if failed_symbols and not auto_filter:
            general_recommendations.append(f"Revisar símbolos fallidos: {', '.join(failed_symbols)}")
        
        # Lista final de símbolos según filtros
        if auto_filter:
            final_symbols = backtest_ready + warnings_symbols
            excluded_symbols = failed_symbols + critical_symbols
        else:
            final_symbols = symbols
            excluded_symbols = critical_symbols
        
        # Crear resultado final
        result = {
            'validation_summary': {
                'total_symbols': len(symbols),
                'backtest_ready': len(backtest_ready),
                'warnings': len(warnings_symbols),
                'failed': len(failed_symbols),
                'critical': len(critical_symbols),
                'success_rate': (len(backtest_ready) / max(1, len(symbols))) * 100
            },
            'symbol_classification': {
                'backtest_ready': backtest_ready,
                'warnings': warnings_symbols,
                'failed': failed_symbols,
                'critical': critical_symbols
            },
            'final_recommendation': {
                'recommended_symbols': final_symbols,
                'excluded_symbols': excluded_symbols,
                'auto_filter_applied': auto_filter
            },
            'general_recommendations': general_recommendations,
            'detailed_reports': reports,
            'validation_level': self.validation_level.value,
            'validation_timestamp': datetime.now().isoformat()
        }
        
        logger.info(f"✅ Pre-backtesting completado: {len(final_symbols)} símbolos recomendados")
        
        return result
    
    def generate_html_report(self, reports: Dict[str, SymbolValidationReport], 
                           output_file: str = "validation_report.html") -> bool:
        """Generar reporte HTML detallado"""
        try:
            html_content = self._create_html_report_content(reports)
            
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            logger.info(f"📄 Reporte HTML generado: {output_file}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error generando reporte HTML: {e}")
            return False
    
    def _create_html_report_content(self, reports: Dict[str, SymbolValidationReport]) -> str:
        """Crear contenido HTML del reporte"""
        # Calcular estadísticas generales
        total_symbols = len(reports)
        passed = len([r for r in reports.values() if r.overall_status == ValidationStatus.PASSED])
        warnings = len([r for r in reports.values() if r.overall_status == ValidationStatus.WARNING])
        failed = len([r for r in reports.values() if r.overall_status == ValidationStatus.FAILED])
        critical = len([r for r in reports.values() if r.overall_status == ValidationStatus.CRITICAL])
        
        avg_score = np.mean([r.overall_score for r in reports.values()]) if reports else 0
        
        html = f"""
        <!DOCTYPE html>
        <html lang="es">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Data Validation Report</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }}
                .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 20px; border-radius: 10px; }}
                .header {{ text-align: center; margin-bottom: 30px; }}
                .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 30px; }}
                .stat-card {{ background: #f8f9fa; padding: 20px; border-radius: 8px; text-align: center; }}
                .stat-number {{ font-size: 2em; font-weight: bold; color: #333; }}
                .stat-label {{ color: #666; }}
                .status-passed {{ color: #28a745; }}
                .status-warning {{ color: #ffc107; }}
                .status-failed {{ color: #dc3545; }}
                .status-critical {{ color: #721c24; }}
                .symbol-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 20px; }}
                .symbol-card {{ border: 1px solid #ddd; border-radius: 8px; padding: 15px; }}
                .symbol-header {{ display: flex; justify-content: between; align-items: center; margin-bottom: 10px; }}
                .symbol-name {{ font-size: 1.2em; font-weight: bold; }}
                .score-badge {{ padding: 4px 8px; border-radius: 4px; color: white; font-weight: bold; }}
                .validation-details {{ margin-top: 10px; }}
                .validation-item {{ margin: 5px 0; padding: 5px; background: #f8f9fa; border-radius: 4px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🔍 Data Validation Report</h1>
                    <p>Generado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                    <p>Nivel de validación: {self.validation_level.value}</p>
                </div>
                
                <div class="summary">
                    <div class="stat-card">
                        <div class="stat-number">{total_symbols}</div>
                        <div class="stat-label">Total Símbolos</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number status-passed">{passed}</div>
                        <div class="stat-label">Aprobados</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number status-warning">{warnings}</div>
                        <div class="stat-label">Con Advertencias</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number status-failed">{failed + critical}</div>
                        <div class="stat-label">Fallidos</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number">{avg_score:.1f}/100</div>
                        <div class="stat-label">Score Promedio</div>
                    </div>
                </div>
                
                <h2>Detalles por Símbolo</h2>
                <div class="symbol-grid">
        """
        
        # Añadir tarjetas de símbolos
        for symbol, report in sorted(reports.items()):
            status_class = f"status-{report.overall_status.value.lower()}"
            
            # Determinar color del badge de score
            if report.overall_score >= 90:
                badge_color = "#28a745"  # Verde
            elif report.overall_score >= 80:
                badge_color = "#ffc107"  # Amarillo
            elif report.overall_score >= 60:
                badge_color = "#fd7e14"  # Naranja
            else:
                badge_color = "#dc3545"  # Rojo
            
            html += f"""
                <div class="symbol-card">
                    <div class="symbol-header">
                        <div class="symbol-name {status_class}">{symbol}</div>
                        <div class="score-badge" style="background-color: {badge_color}">
                            {report.overall_score:.1f}/100
                        </div>
                    </div>
                    <div><strong>Status:</strong> {report.overall_status.value}</div>
                    <div><strong>Backtest Ready:</strong> {'✅ Sí' if report.backtest_ready else '❌ No'}</div>
                    <div><strong>Datos:</strong> {report.total_data_points:,} puntos</div>
                    
                    <div class="validation-details">
                        <strong>Validaciones:</strong>
            """
            
            # Añadir resultados de validaciones
            for validation_type, result in report.validation_results.items():
                result_class = f"status-{result.status.value.lower()}"
                html += f"""
                    <div class="validation-item">
                        <span class="{result_class}">
                            {validation_type.value}: {result.score:.1f}/100
                        </span>
                    </div>
                """
            
            # Añadir issues críticos si existen
            if report.critical_issues:
                html += "<div><strong>Issues Críticos:</strong><ul>"
                for issue in report.critical_issues[:3]:  # Máximo 3
                    html += f"<li>{issue}</li>"
                html += "</ul></div>"
            
            html += """
                    </div>
                </div>
            """
        
        html += """
                </div>
            </div>
        </body>
        </html>
        """
        
        return html
    
    def export_results_json(self, reports: Dict[str, SymbolValidationReport], 
                           output_file: str = "validation_results.json") -> bool:
        """Exportar resultados a JSON"""
        try:
            # Convertir reports a formato serializable
            json_data = {
                'validation_summary': {
                    'timestamp': datetime.now().isoformat(),
                    'validation_level': self.validation_level.value,
                    'total_symbols': len(reports),
                    'validation_stats': self.validation_stats
                },
                'symbol_reports': {}
            }
            
            for symbol, report in reports.items():
                json_data['symbol_reports'][symbol] = {
                    'symbol': report.symbol,
                    'validation_timestamp': report.validation_timestamp.isoformat(),
                    'overall_status': report.overall_status.value,
                    'overall_score': report.overall_score,
                    'backtest_ready': report.backtest_ready,
                    'total_data_points': report.total_data_points,
                    'validation_duration_ms': report.validation_duration_ms,
                    'critical_issues': report.critical_issues,
                    'warnings': report.warnings,
                    'recommendations': report.recommendations,
                    'validation_results': {
                        validation_type.value: {
                            'status': result.status.value,
                            'score': result.score,
                            'execution_time_ms': result.execution_time_ms,
                            'issues': result.issues,
                            'recommendations': result.recommendations,
                            'details': result.details
                        } for validation_type, result in report.validation_results.items()
                    }
                }
            
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(json_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"📄 Resultados exportados a JSON: {output_file}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error exportando a JSON: {e}")
            return False
    
    def get_validation_statistics(self) -> Dict[str, Any]:
        """Obtener estadísticas del validador"""
        return {
            'validation_level': self.validation_level.value,
            'statistics': self.validation_stats.copy(),
            'thresholds': self.thresholds.copy(),
            'system_integration': {
                'indicators_available': self.indicators is not None,
                'gap_detector_available': self.gap_detector is not None,
                'database_available': self.database_available
            }
        }

# =============================================================================
# FUNCIONES DE UTILIDAD Y HELPERS
# =============================================================================

def validate_symbol_quick(symbol: str, validation_level: ValidationLevel = ValidationLevel.STANDARD) -> bool:
    """
    Validación rápida de un símbolo - retorna solo True/False
    
    Args:
        symbol: Símbolo a validar
        validation_level: Nivel de validación
        
    Returns:
        True si el símbolo está listo para backtesting
    """
    try:
        validator = DataValidator(validation_level)
        report = validator.validate_symbol(symbol)
        return report.backtest_ready
        
    except Exception as e:
        logger.error(f"Error en validación rápida de {symbol}: {e}")
        return False

def get_backtest_ready_symbols(symbols: List[str], 
                              validation_level: ValidationLevel = ValidationLevel.STANDARD) -> List[str]:
    """
    Obtener lista de símbolos listos para backtesting
    
    Args:
        symbols: Lista de símbolos a validar
        validation_level: Nivel de validación
        
    Returns:
        Lista de símbolos aprobados
    """
    try:
        validator = DataValidator(validation_level)
        results = validator.validate_for_backtesting(symbols, auto_filter=True)
        return results['final_recommendation']['recommended_symbols']
        
    except Exception as e:
        logger.error(f"Error obteniendo símbolos aprobados: {e}")
        return []

def create_validation_report_summary(reports: Dict[str, SymbolValidationReport]) -> Dict[str, Any]:
    """Crear resumen ejecutivo de validación"""
    if not reports:
        return {}
    
    # Clasificar por status
    status_counts = {}
    for status in ValidationStatus:
        status_counts[status.value] = len([r for r in reports.values() if r.overall_status == status])
    
    # Calcular métricas
    scores = [r.overall_score for r in reports.values()]
    backtest_ready_count = len([r for r in reports.values() if r.backtest_ready])
    
    # Issues más comunes
    all_issues = []
    for report in reports.values():
        all_issues.extend(report.critical_issues)
        all_issues.extend(report.warnings)
    
    # Contar frecuencia de issues
    issue_frequency = {}
    for issue in all_issues:
        issue_frequency[issue] = issue_frequency.get(issue, 0) + 1
    
    top_issues = sorted(issue_frequency.items(), key=lambda x: x[1], reverse=True)[:5]
    
    return {
        'total_symbols': len(reports),
        'status_distribution': status_counts,
        'backtest_ready_count': backtest_ready_count,
        'backtest_ready_percentage': (backtest_ready_count / len(reports)) * 100,
        'score_statistics': {
            'average': np.mean(scores),
            'median': np.median(scores),
            'min': min(scores),
            'max': max(scores),
            'std_dev': np.std(scores)
        },
        'top_issues': top_issues,
        'validation_timestamp': datetime.now().isoformat()
    }

# =============================================================================
# FUNCIONES DE TESTING Y DEMO
# =============================================================================

def test_data_validator_basic():
    """Test básico del data validator"""
    print("🧪 TESTING DATA VALIDATOR BÁSICO")
    print("=" * 50)
    
    try:
        # Test 1: Inicialización
        print("1. 🔧 Inicializando validator...")
        validator = DataValidator(ValidationLevel.STANDARD)
        print(f"   Nivel: {validator.validation_level.value}")
        print(f"   Umbrales: {len(validator.thresholds)} configurados")
        
        # Test 2: Validación de un símbolo
        print("2. 📊 Validando símbolo de prueba...")
        test_symbol = "SPY"
        
        report = validator.validate_symbol(test_symbol)
        print(f"   {test_symbol}: Score {report.overall_score:.1f}/100")
        print(f"   Status: {report.overall_status.value}")
        print(f"   Backtest ready: {'✅' if report.backtest_ready else '❌'}")
        print(f"   Datos: {report.total_data_points:,} puntos")
        
        # Test 3: Mostrar validaciones individuales
        print("3. 🔍 Resultados por validación:")
        for validation_type, result in report.validation_results.items():
            status_emoji = {
                ValidationStatus.PASSED: "✅",
                ValidationStatus.WARNING: "⚠️", 
                ValidationStatus.FAILED: "❌",
                ValidationStatus.CRITICAL: "🚨"
            }
            emoji = status_emoji.get(result.status, "❓")
            print(f"   {emoji} {validation_type.value}: {result.score:.1f}/100")
        
        # Test 4: Issues y recomendaciones
        if report.critical_issues:
            print("4. 🚨 Issues críticos:")
            for issue in report.critical_issues[:3]:
                print(f"   • {issue}")
        
        if report.recommendations:
            print("5. 💡 Recomendaciones:")
            for rec in report.recommendations[:3]:
                print(f"   • {rec}")
        
        print("✅ Test básico completado")
        return validator, report
        
    except Exception as e:
        print(f"❌ Error en test básico: {e}")
        return None, None

def test_data_validator_multiple():
    """Test con múltiples símbolos"""
    print("\n🧪 TESTING VALIDACIÓN MÚLTIPLE")
    print("=" * 50)
    
    try:
        validator = DataValidator(ValidationLevel.STANDARD)
        test_symbols = ["SPY", "AAPL", "NVDA"]
        
        print(f"📊 Validando {len(test_symbols)} símbolos...")
        
        reports = validator.validate_multiple_symbols(test_symbols)
        
        print("\n📋 RESULTADOS:")
        for symbol, report in reports.items():
            status_emoji = {
                ValidationStatus.PASSED: "✅",
                ValidationStatus.WARNING: "⚠️",
                ValidationStatus.FAILED: "❌", 
                ValidationStatus.CRITICAL: "🚨"
            }
            emoji = status_emoji.get(report.overall_status, "❓")
            backtest_icon = "🧪" if report.backtest_ready else "🚫"
            
            print(f"   {emoji} {symbol}: {report.overall_score:.1f}/100 {backtest_icon}")
        
        # Estadísticas
        stats = validator.get_validation_statistics()
        print(f"\n📈 ESTADÍSTICAS:")
        print(f"   Total validaciones: {stats['statistics']['total_validations']}")
        print(f"   Aprobadas: {stats['statistics']['passed_validations']}")
        print(f"   Fallidas: {stats['statistics']['failed_validations']}")
        
        print("✅ Test múltiple completado")
        return reports
        
    except Exception as e:
        print(f"❌ Error en test múltiple: {e}")
        return None

def test_data_validator_backtesting():
    """Test específico para backtesting"""
    print("\n🧪 TESTING VALIDACIÓN PRE-BACKTESTING")
    print("=" * 50)
    
    try:
        validator = DataValidator(ValidationLevel.STRICT)
        test_symbols = ["SPY", "QQQ", "AAPL", "MSFT", "GOOGL"]
        
        print(f"🧪 Validación pre-backtesting de {len(test_symbols)} símbolos...")
        
        results = validator.validate_for_backtesting(test_symbols, auto_filter=True)
        
        summary = results['validation_summary']
        print(f"\n📊 RESUMEN:")
        print(f"   Total símbolos: {summary['total_symbols']}")
        print(f"   Listos para backtest: {summary['backtest_ready']}")
        print(f"   Con advertencias: {summary['warnings']}")
        print(f"   Fallidos: {summary['failed']}")
        print(f"   Tasa de éxito: {summary['success_rate']:.1f}%")
        
        recommendation = results['final_recommendation']
        print(f"\n💡 RECOMENDACIÓN FINAL:")
        print(f"   Símbolos recomendados: {', '.join(recommendation['recommended_symbols'])}")
        
        if recommendation['excluded_symbols']:
            print(f"   Símbolos excluidos: {', '.join(recommendation['excluded_symbols'])}")
        
        if results['general_recommendations']:
            print(f"\n🎯 RECOMENDACIONES GENERALES:")
            for rec in results['general_recommendations']:
                print(f"   • {rec}")
        
        print("✅ Test pre-backtesting completado")
        return results
        
    except Exception as e:
        print(f"❌ Error en test pre-backtesting: {e}")
        return None

def demo_data_validator_complete():
    """Demo completo del data validator"""
    print("🎮 DEMO COMPLETO - DATA VALIDATOR V3.1")
    print("=" * 60)
    
    # Test 1: Básico
    validator, basic_report = test_data_validator_basic()
    
    if validator and basic_report:
        # Test 2: Múltiple
        multiple_reports = test_data_validator_multiple()
        
        if multiple_reports:
            # Test 3: Pre-backtesting
            backtest_results = test_data_validator_backtesting()
            
            if backtest_results:
                # Test 4: Generar reportes
                print("\n📄 GENERANDO REPORTES...")
                
                try:
                    # Reporte JSON
                    json_success = validator.export_results_json(
                        multiple_reports, 
                        "test_validation_results.json"
                    )
                    
                    # Reporte HTML
                    html_success = validator.generate_html_report(
                        multiple_reports,
                        "test_validation_report.html" 
                    )
                    
                    print(f"   JSON: {'✅' if json_success else '❌'}")
                    print(f"   HTML: {'✅' if html_success else '❌'}")
                    
                except Exception as e:
                    print(f"   ❌ Error generando reportes: {e}")
                
                # Test 5: Resumen ejecutivo
                print("\n📊 RESUMEN EJECUTIVO:")
                summary = create_validation_report_summary(multiple_reports)
                print(f"   Símbolos analizados: {summary['total_symbols']}")
                print(f"   Listos para backtest: {summary['backtest_ready_count']}")
                print(f"   Score promedio: {summary['score_statistics']['average']:.1f}")
                
                if summary['top_issues']:
                    print(f"   Issue más común: {summary['top_issues'][0][0]}")
    
    print("\n🏁 Demo completo finalizado!")

# =============================================================================
# PUNTO DE ENTRADA PRINCIPAL
# =============================================================================

if __name__ == "__main__":
    """Ejecutar según argumentos de línea de comandos"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Data Validator V3.1 - Validación pre-backtesting")
    parser.add_argument("--symbol", type=str, help="Validar un símbolo específico")
    parser.add_argument("--symbols", type=str, nargs='+', help="Validar múltiples símbolos")
    parser.add_argument("--level", choices=["BASIC", "STANDARD", "STRICT", "EXTENDED"], 
                       default="STANDARD", help="Nivel de validación")
    parser.add_argument("--days", type=int, default=30, help="Días de historial")
    parser.add_argument("--output", type=str, help="Archivo de salida para reporte")
    parser.add_argument("--format", choices=["json", "html"], default="json", 
                       help="Formato de reporte")
    parser.add_argument("--demo", action="store_true", help="Ejecutar demo completo")
    parser.add_argument("--test", action="store_true", help="Ejecutar tests")
    
    args = parser.parse_args()
    
    print("🔍 DATA VALIDATOR V3.1")
    print("=" * 40)
    
    try:
        if args.demo:
            demo_data_validator_complete()
            
        elif args.test:
            success = True
            validator, report = test_data_validator_basic()
            if not validator:
                success = False
            
            if success:
                multiple_reports = test_data_validator_multiple()
                if not multiple_reports:
                    success = False
            
            if success:
                backtest_results = test_data_validator_backtesting()
                if not backtest_results:
                    success = False
            
            print(f"\n🏁 Tests completados: {'✅ ÉXITO' if success else '❌ FALLOS'}")
            
        elif args.symbol:
            # Validar un símbolo
            validation_level = ValidationLevel[args.level]
            validator = DataValidator(validation_level)
            
            print(f"🔍 Validando {args.symbol} - Nivel: {args.level}")
            report = validator.validate_symbol(args.symbol, days_back=args.days)
            
            print(f"\n📊 RESULTADO:")
            print(f"   Score: {report.overall_score:.1f}/100")
            print(f"   Status: {report.overall_status.value}")
            print(f"   Backtest ready: {'✅ SÍ' if report.backtest_ready else '❌ NO'}")
            
            if args.output:
                if args.format == "json":
                    validator.export_results_json({args.symbol: report}, args.output)
                else:
                    validator.generate_html_report({args.symbol: report}, args.output)
                print(f"📄 Reporte guardado: {args.output}")
            
        elif args.symbols:
            # Validar múltiples símbolos
            validation_level = ValidationLevel[args.level]
            validator = DataValidator(validation_level)
            
            print(f"🔍 Validando {len(args.symbols)} símbolos - Nivel: {args.level}")
            results = validator.validate_for_backtesting(args.symbols, days_back=args.days)
            
            summary = results['validation_summary']
            print(f"\n📊 RESUMEN:")
            print(f"   Aprobados: {summary['backtest_ready']}/{summary['total_symbols']}")
            print(f"   Tasa éxito: {summary['success_rate']:.1f}%")
            
            recommended = results['final_recommendation']['recommended_symbols']
            print(f"   Recomendados: {', '.join(recommended) if recommended else 'Ninguno'}")
            
            if args.output:
                reports = results['detailed_reports']
                if args.format == "json":
                    validator.export_results_json(reports, args.output)
                else:
                    validator.generate_html_report(reports, args.output)
                print(f"📄 Reporte guardado: {args.output}")
        
        else:
            print("❓ No se especificó acción. Usa --help para ver opciones.")
            print("💡 Prueba: python data_validator.py --demo")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        exit(1)