#!/usr/bin/env python3
"""
🔍 GAP DETECTOR V3.1 - SISTEMA DE DETECCIÓN Y ANÁLISIS DE GAPS
============================================================

Módulo independiente para detectar, analizar y reportar gaps en datos
de trading. Funciona tanto con datos históricos como en tiempo real.

🎯 FUNCIONALIDADES:
- Detección automática de gaps en datos OHLCV
- Clasificación de gaps (overnight, weekend, holiday, etc.)
- Análisis de calidad de datos
- Generación de reportes detallados
- Sugerencias de estrategias de filling
- Validación de continuidad de datos

🔧 USO:
- Como módulo independiente para auditoría de datos
- Integrado con indicators.py para filling automático
- Para validación antes de backtesting
- Análisis de calidad de datos históricos
"""

import pandas as pd
import numpy as np
import logging
from datetime import datetime, timedelta, time
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
from enum import Enum
import pytz
import sqlite3
from pathlib import Path

# Importar configuración si está disponible
try:
    import config
    GAP_CONFIG = getattr(config, 'GAP_DETECTION_CONFIG', {})
    MARKET_TZ = pytz.timezone(getattr(config, 'MARKET_TIMEZONE', 'US/Eastern'))
    logger = logging.getLogger(__name__)
except ImportError:
    # Configuración básica si no hay config.py
    GAP_CONFIG = {
        'MIN_GAP_MINUTES': 60,
        'OVERNIGHT_GAP_HOURS': [20, 4],
        'WEEKEND_GAP_HOURS': 48,
        'HOLIDAY_GAP_HOURS': 24,
        'FILL_STRATEGIES': {
            'SMALL_GAP': 'INTERPOLATE',
            'OVERNIGHT_GAP': 'FORWARD_FILL',
            'WEEKEND_GAP': 'FORWARD_FILL',
            'HOLIDAY_GAP': 'FORWARD_FILL'
        }
    }
    MARKET_TZ = pytz.timezone('US/Eastern')
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

class GapType(Enum):
    """Tipos de gaps detectados"""
    SMALL_GAP = "SMALL_GAP"           # < 4 horas
    OVERNIGHT_GAP = "OVERNIGHT_GAP"   # 8PM - 4AM
    WEEKEND_GAP = "WEEKEND_GAP"       # > 48 horas
    HOLIDAY_GAP = "HOLIDAY_GAP"       # Día laborable > 24h
    UNKNOWN_GAP = "UNKNOWN_GAP"       # No clasificado
    API_FAILURE = "API_FAILURE"       # Posible fallo de API

class GapSeverity(Enum):
    """Severidad del gap para priorización"""
    LOW = "LOW"           # Gap normal, fácil de rellenar
    MEDIUM = "MEDIUM"     # Gap significativo
    HIGH = "HIGH"         # Gap crítico para análisis
    CRITICAL = "CRITICAL" # Gap que puede romper backtesting

@dataclass
class Gap:
    """Representa un gap detectado en los datos"""
    symbol: str
    start_time: datetime
    end_time: datetime
    duration_minutes: float
    gap_type: GapType
    severity: GapSeverity
    
    # Contexto del gap
    before_price: float
    after_price: float
    price_change_pct: float
    
    # Metadatos
    detection_time: datetime
    suggested_strategy: str
    is_fillable: bool
    confidence: float  # 0-1, confianza en la clasificación
    
    # Información adicional
    market_session_before: Optional[str] = None
    market_session_after: Optional[str] = None
    volume_before: Optional[float] = None
    volume_after: Optional[float] = None

@dataclass
class DataQualityReport:
    """Reporte completo de calidad de datos"""
    symbol: str
    analysis_period: Tuple[datetime, datetime]
    total_data_points: int
    expected_data_points: int
    completeness_pct: float
    
    # Gaps detectados
    gaps_detected: List[Gap]
    total_gaps: int
    gaps_by_type: Dict[str, int]
    gaps_by_severity: Dict[str, int]
    
    # Métricas de calidad
    max_gap_duration_hours: float
    avg_gap_duration_minutes: float
    price_anomalies_count: int
    volume_anomalies_count: int
    
    # Recomendaciones
    overall_quality_score: float  # 0-100
    is_suitable_for_backtesting: bool
    recommended_actions: List[str]
    
    # Timestamps
    analysis_time: datetime

class GapDetector:
    """
    Detector principal de gaps con análisis avanzado
    """
    
    def __init__(self):
        """Inicializar detector con configuración"""
        self.gap_config = GAP_CONFIG
        self.market_tz = MARKET_TZ
        self.detection_stats = {
            'total_symbols_analyzed': 0,
            'total_gaps_detected': 0,
            'gaps_by_type': {},
            'analysis_sessions': 0
        }
        
        logger.info("🔍 Gap Detector V3.1 inicializado")
        logger.info(f"⚙️ Configuración: Gap mínimo {self.gap_config.get('MIN_GAP_MINUTES', 60)} min")
    
    def detect_gaps_in_dataframe(self, data: pd.DataFrame, symbol: str, 
                                expected_interval_minutes: int = 15) -> List[Gap]:
        """
        Detectar gaps en un DataFrame de datos OHLCV
        
        Args:
            data: DataFrame con índice datetime y columnas OHLCV
            symbol: Símbolo analizado
            expected_interval_minutes: Intervalo esperado entre datos
            
        Returns:
            Lista de gaps detectados
        """
        try:
            if len(data) < 2:
                logger.warning(f"📊 {symbol}: Datos insuficientes para detectar gaps")
                return []
            
            # Asegurar que el índice es datetime
            if not isinstance(data.index, pd.DatetimeIndex):
                data.index = pd.to_datetime(data.index)
            
            # Ordenar por tiempo
            data_sorted = data.sort_index()
            
            gaps = []
            min_gap_minutes = self.gap_config.get('MIN_GAP_MINUTES', 60)
            
            # Calcular diferencias temporales
            time_diffs = data_sorted.index.to_series().diff()
            
            logger.debug(f"🔍 {symbol}: Analizando {len(data_sorted)} puntos de datos")
            
            for i, diff in enumerate(time_diffs[1:], 1):
                if pd.notna(diff):
                    gap_minutes = diff.total_seconds() / 60
                    
                    # Solo considerar gaps significativos
                    if gap_minutes > min_gap_minutes:
                        gap_start = data_sorted.index[i-1]
                        gap_end = data_sorted.index[i]
                        
                        # Crear objeto Gap
                        gap = self._create_gap_object(
                            symbol=symbol,
                            start_time=gap_start,
                            end_time=gap_end,
                            duration_minutes=gap_minutes,
                            before_data=data_sorted.iloc[i-1],
                            after_data=data_sorted.iloc[i],
                            expected_interval=expected_interval_minutes
                        )
                        
                        gaps.append(gap)
                        
                        logger.debug(f"🔍 {symbol}: Gap detectado {gap.gap_type.value} "
                                   f"({gap.duration_minutes:.1f} min) "
                                   f"{gap_start} -> {gap_end}")
            
            # Actualizar estadísticas
            self.detection_stats['total_gaps_detected'] += len(gaps)
            for gap in gaps:
                gap_type = gap.gap_type.value
                self.detection_stats['gaps_by_type'][gap_type] = \
                    self.detection_stats['gaps_by_type'].get(gap_type, 0) + 1
            
            logger.info(f"✅ {symbol}: {len(gaps)} gaps detectados")
            return gaps
            
        except Exception as e:
            logger.error(f"❌ Error detectando gaps en {symbol}: {e}")
            return []
    
    def _create_gap_object(self, symbol: str, start_time: datetime, end_time: datetime,
                          duration_minutes: float, before_data: pd.Series, 
                          after_data: pd.Series, expected_interval: int) -> Gap:
        """Crear objeto Gap con análisis completo"""
        try:
            # Clasificar tipo de gap
            gap_type = self._classify_gap_type(start_time, end_time, duration_minutes)
            
            # Determinar severidad
            severity = self._determine_gap_severity(gap_type, duration_minutes, expected_interval)
            
            # Calcular cambio de precio
            before_price = float(before_data.get('Close', before_data.get('close', 0)))
            after_price = float(after_data.get('Open', after_data.get('open', 0)))
            
            if before_price > 0:
                price_change_pct = ((after_price - before_price) / before_price) * 100
            else:
                price_change_pct = 0
            
            # Estrategia sugerida
            suggested_strategy = self.gap_config.get('FILL_STRATEGIES', {}).get(
                gap_type.value, 'FORWARD_FILL'
            )
            
            # Es rellenable?
            is_fillable = self._is_gap_fillable(gap_type, duration_minutes)
            
            # Confianza en clasificación
            confidence = self._calculate_classification_confidence(
                gap_type, duration_minutes, start_time, end_time
            )
            
            # Información de volumen si está disponible
            volume_before = before_data.get('Volume', before_data.get('volume'))
            volume_after = after_data.get('Volume', after_data.get('volume'))
            
            gap = Gap(
                symbol=symbol,
                start_time=start_time,
                end_time=end_time,
                duration_minutes=duration_minutes,
                gap_type=gap_type,
                severity=severity,
                before_price=before_price,
                after_price=after_price,
                price_change_pct=price_change_pct,
                detection_time=datetime.now(),
                suggested_strategy=suggested_strategy,
                is_fillable=is_fillable,
                confidence=confidence,
                volume_before=float(volume_before) if pd.notna(volume_before) else None,
                volume_after=float(volume_after) if pd.notna(volume_after) else None
            )
            
            return gap
            
        except Exception as e:
            logger.error(f"❌ Error creando objeto Gap: {e}")
            # Crear gap básico en caso de error
            return Gap(
                symbol=symbol,
                start_time=start_time,
                end_time=end_time,
                duration_minutes=duration_minutes,
                gap_type=GapType.UNKNOWN_GAP,
                severity=GapSeverity.MEDIUM,
                before_price=0,
                after_price=0,
                price_change_pct=0,
                detection_time=datetime.now(),
                suggested_strategy='FORWARD_FILL',
                is_fillable=True,
                confidence=0.5
            )
    
    def _classify_gap_type(self, start_time: datetime, end_time: datetime, 
                          duration_minutes: float) -> GapType:
        """Clasificar el tipo de gap basado en duración y horario"""
        try:
            # Gap de fin de semana
            if duration_minutes > self.gap_config.get('WEEKEND_GAP_HOURS', 48) * 60:
                return GapType.WEEKEND_GAP
            
            # Gap overnight (verificar horarios)
            overnight_hours = self.gap_config.get('OVERNIGHT_GAP_HOURS', [20, 4])
            start_hour = start_time.hour
            end_hour = end_time.hour
            
            # Verificar si está en horario overnight
            if ((start_hour >= overnight_hours[0] or start_hour <= overnight_hours[1]) and
                (end_hour >= overnight_hours[0] or end_hour <= overnight_hours[1]) and
                duration_minutes <= 12 * 60):  # Max 12 horas para overnight
                return GapType.OVERNIGHT_GAP
            
            # Gap pequeño
            if duration_minutes < 4 * 60:  # < 4 horas
                return GapType.SMALL_GAP
            
            # Gap en día laborable (posible festivo)
            if (duration_minutes > self.gap_config.get('HOLIDAY_GAP_HOURS', 24) * 60 and
                start_time.weekday() < 5):  # Lunes a Viernes
                return GapType.HOLIDAY_GAP
            
            # Posible fallo de API si es muy raro
            if duration_minutes > 48 * 60:  # > 48 horas pero no weekend
                return GapType.API_FAILURE
            
            return GapType.UNKNOWN_GAP
            
        except Exception as e:
            logger.error(f"❌ Error clasificando gap: {e}")
            return GapType.UNKNOWN_GAP
    
    def _determine_gap_severity(self, gap_type: GapType, duration_minutes: float,
                               expected_interval: int) -> GapSeverity:
        """Determinar la severidad del gap"""
        try:
            # Severidad basada en tipo
            if gap_type == GapType.API_FAILURE:
                return GapSeverity.CRITICAL
            
            if gap_type == GapType.WEEKEND_GAP:
                return GapSeverity.LOW  # Normal
            
            if gap_type == GapType.OVERNIGHT_GAP:
                return GapSeverity.LOW if duration_minutes < 10 * 60 else GapSeverity.MEDIUM
            
            # Severidad basada en duración vs intervalo esperado
            gap_intervals = duration_minutes / expected_interval
            
            if gap_intervals <= 4:  # <= 4 intervalos perdidos
                return GapSeverity.LOW
            elif gap_intervals <= 12:  # <= 12 intervalos
                return GapSeverity.MEDIUM
            elif gap_intervals <= 24:  # <= 24 intervalos
                return GapSeverity.HIGH
            else:
                return GapSeverity.CRITICAL
                
        except Exception:
            return GapSeverity.MEDIUM
    
    def _is_gap_fillable(self, gap_type: GapType, duration_minutes: float) -> bool:
        """Determinar si el gap se puede rellenar de forma confiable"""
        try:
            # Gaps muy largos son difíciles de rellenar
            if duration_minutes > 72 * 60:  # > 72 horas
                return False
            
            # API failures son problemáticos
            if gap_type == GapType.API_FAILURE:
                return False
            
            # El resto se puede rellenar
            return True
            
        except Exception:
            return True
    
    def _calculate_classification_confidence(self, gap_type: GapType, duration_minutes: float,
                                           start_time: datetime, end_time: datetime) -> float:
        """Calcular confianza en la clasificación del gap"""
        try:
            confidence = 0.5  # Base
            
            # Confianza basada en tipo
            if gap_type == GapType.WEEKEND_GAP:
                # Verificar si realmente es fin de semana
                if start_time.weekday() >= 5 or end_time.weekday() >= 5:
                    confidence += 0.4
                
            elif gap_type == GapType.OVERNIGHT_GAP:
                # Verificar horarios overnight
                overnight_hours = self.gap_config.get('OVERNIGHT_GAP_HOURS', [20, 4])
                if (start_time.hour >= overnight_hours[0] or 
                    start_time.hour <= overnight_hours[1]):
                    confidence += 0.3
                    
            elif gap_type == GapType.SMALL_GAP:
                # Gaps pequeños son más confiables
                if duration_minutes < 2 * 60:  # < 2 horas
                    confidence += 0.3
            
            # Bonus por duración consistente
            if gap_type == GapType.OVERNIGHT_GAP and 8 * 60 <= duration_minutes <= 12 * 60:
                confidence += 0.2
            
            return min(1.0, confidence)
            
        except Exception:
            return 0.5
    
    def analyze_data_quality(self, data: pd.DataFrame, symbol: str,
                           expected_interval_minutes: int = 15) -> DataQualityReport:
        """
        Análisis completo de calidad de datos
        
        Args:
            data: DataFrame con datos OHLCV
            symbol: Símbolo analizado
            expected_interval_minutes: Intervalo esperado entre datos
            
        Returns:
            Reporte completo de calidad
        """
        try:
            logger.info(f"📊 Analizando calidad de datos para {symbol}")
            
            # Período de análisis
            if len(data) == 0:
                raise ValueError(f"Sin datos para analizar en {symbol}")
            
            analysis_start = data.index.min()
            analysis_end = data.index.max()
            analysis_period = (analysis_start, analysis_end)
            
            # Detectar gaps
            gaps = self.detect_gaps_in_dataframe(data, symbol, expected_interval_minutes)
            
            # Calcular completeness
            total_duration = (analysis_end - analysis_start).total_seconds() / 60
            expected_points = int(total_duration / expected_interval_minutes)
            actual_points = len(data)
            completeness_pct = min(100.0, (actual_points / max(1, expected_points)) * 100)
            
            # Estadísticas de gaps
            gaps_by_type = {}
            gaps_by_severity = {}
            
            for gap in gaps:
                gap_type = gap.gap_type.value
                severity = gap.severity.value
                gaps_by_type[gap_type] = gaps_by_type.get(gap_type, 0) + 1
                gaps_by_severity[severity] = gaps_by_severity.get(severity, 0) + 1
            
            # Métricas adicionales
            max_gap_duration = max([g.duration_minutes for g in gaps], default=0) / 60  # horas
            avg_gap_duration = np.mean([g.duration_minutes for g in gaps]) if gaps else 0
            
            # Detectar anomalías de precio y volumen
            price_anomalies = self._detect_price_anomalies(data)
            volume_anomalies = self._detect_volume_anomalies(data)
            
            # Calcular score de calidad general
            quality_score = self._calculate_overall_quality_score(
                completeness_pct, len(gaps), max_gap_duration, 
                price_anomalies, volume_anomalies
            )
            
            # Determinar si es adecuado para backtesting
            is_suitable = (
                completeness_pct >= 90 and
                len([g for g in gaps if g.severity == GapSeverity.CRITICAL]) == 0 and
                price_anomalies < len(data) * 0.05  # < 5% anomalías
            )
            
            # Generar recomendaciones
            recommendations = self._generate_recommendations(
                gaps, completeness_pct, price_anomalies, volume_anomalies
            )
            
            # Crear reporte
            report = DataQualityReport(
                symbol=symbol,
                analysis_period=analysis_period,
                total_data_points=actual_points,
                expected_data_points=expected_points,
                completeness_pct=completeness_pct,
                gaps_detected=gaps,
                total_gaps=len(gaps),
                gaps_by_type=gaps_by_type,
                gaps_by_severity=gaps_by_severity,
                max_gap_duration_hours=max_gap_duration,
                avg_gap_duration_minutes=avg_gap_duration,
                price_anomalies_count=price_anomalies,
                volume_anomalies_count=volume_anomalies,
                overall_quality_score=quality_score,
                is_suitable_for_backtesting=is_suitable,
                recommended_actions=recommendations,
                analysis_time=datetime.now()
            )
            
            # Actualizar estadísticas del detector
            self.detection_stats['total_symbols_analyzed'] += 1
            self.detection_stats['analysis_sessions'] += 1
            
            logger.info(f"✅ {symbol}: Análisis completado - Score: {quality_score:.1f}/100")
            return report
            
        except Exception as e:
            logger.error(f"❌ Error analizando calidad de {symbol}: {e}")
            raise
    
    def _detect_price_anomalies(self, data: pd.DataFrame) -> int:
        """Detectar anomalías en precios (cambios extremos, inconsistencias OHLC)"""
        try:
            anomalies = 0
            
            # Verificar consistencia OHLC
            if all(col in data.columns for col in ['Open', 'High', 'Low', 'Close']):
                # High debe ser >= Low, Open, Close
                high_issues = (
                    (data['High'] < data['Low']) |
                    (data['High'] < data['Open']) |
                    (data['High'] < data['Close'])
                ).sum()
                
                # Low debe ser <= High, Open, Close
                low_issues = (
                    (data['Low'] > data['High']) |
                    (data['Low'] > data['Open']) |
                    (data['Low'] > data['Close'])
                ).sum()
                
                anomalies += high_issues + low_issues
            
            # Detectar cambios extremos (>20% en un período)
            if 'Close' in data.columns:
                price_changes = data['Close'].pct_change().abs()
                extreme_changes = (price_changes > 0.2).sum()  # >20%
                anomalies += extreme_changes
            
            return int(anomalies)
            
        except Exception as e:
            logger.error(f"❌ Error detectando anomalías de precio: {e}")
            return 0
    
    def _detect_volume_anomalies(self, data: pd.DataFrame) -> int:
        """Detectar anomalías en volumen"""
        try:
            anomalies = 0
            
            if 'Volume' in data.columns:
                # Volúmenes negativos o cero
                negative_volume = (data['Volume'] < 0).sum()
                zero_volume = (data['Volume'] == 0).sum()
                
                # Volúmenes extremos (>10x la mediana)
                median_volume = data['Volume'].median()
                if median_volume > 0:
                    extreme_volume = (data['Volume'] > median_volume * 10).sum()
                    anomalies = negative_volume + extreme_volume
                else:
                    anomalies = negative_volume + zero_volume
            
            return int(anomalies)
            
        except Exception as e:
            logger.error(f"❌ Error detectando anomalías de volumen: {e}")
            return 0
    
    def _calculate_overall_quality_score(self, completeness_pct: float, total_gaps: int,
                                       max_gap_hours: float, price_anomalies: int,
                                       volume_anomalies: int) -> float:
        """Calcular score general de calidad (0-100)"""
        try:
            score = 0
            
            # Completeness (40% del score)
            score += completeness_pct * 0.4
            
            # Gaps (30% del score)
            if total_gaps == 0:
                gap_score = 30
            elif total_gaps <= 5:
                gap_score = 25
            elif total_gaps <= 10:
                gap_score = 20
            elif total_gaps <= 20:
                gap_score = 15
            else:
                gap_score = 5
            
            # Penalizar gaps muy largos
            if max_gap_hours > 72:  # > 3 días
                gap_score *= 0.5
            elif max_gap_hours > 24:  # > 1 día
                gap_score *= 0.8
            
            score += gap_score
            
            # Anomalías de precio (20% del score)
            if price_anomalies == 0:
                price_score = 20
            elif price_anomalies <= 2:
                price_score = 15
            elif price_anomalies <= 5:
                price_score = 10
            else:
                price_score = 0
            
            score += price_score
            
            # Anomalías de volumen (10% del score)
            if volume_anomalies == 0:
                volume_score = 10
            elif volume_anomalies <= 2:
                volume_score = 7
            elif volume_anomalies <= 5:
                volume_score = 5
            else:
                volume_score = 0
            
            score += volume_score
            
            return min(100.0, max(0.0, score))
            
        except Exception:
            return 50.0  # Score neutral si hay error
    
    def _generate_recommendations(self, gaps: List[Gap], completeness_pct: float,
                                price_anomalies: int, volume_anomalies: int) -> List[str]:
        """Generar recomendaciones basadas en el análisis"""
        recommendations = []
        
        try:
            # Recomendaciones por completeness
            if completeness_pct < 80:
                recommendations.append("⚠️ Completeness < 80% - Descargar más datos históricos")
            elif completeness_pct < 95:
                recommendations.append("📊 Completeness moderado - Verificar gaps antes de backtesting")
            
            # Recomendaciones por gaps
            critical_gaps = [g for g in gaps if g.severity == GapSeverity.CRITICAL]
            if critical_gaps:
                recommendations.append(f"🚨 {len(critical_gaps)} gaps críticos - Filling manual requerido")
            
            fillable_gaps = [g for g in gaps if g.is_fillable]
            if fillable_gaps:
                recommendations.append(f"🔧 {len(fillable_gaps)} gaps auto-rellenables disponibles")
            
            overnight_gaps = [g for g in gaps if g.gap_type == GapType.OVERNIGHT_GAP]
            if len(overnight_gaps) > 10:
                recommendations.append("🌙 Muchos gaps overnight - Considerar extended hours data")
            
            # Recomendaciones por anomalías
            if price_anomalies > 5:
                recommendations.append(f"💰 {price_anomalies} anomalías de precio - Revisar datos OHLC")
            
            if volume_anomalies > 3:
                recommendations.append(f"📊 {volume_anomalies} anomalías de volumen - Validar fuente de datos")
            
            # Recomendaciones generales
            if not recommendations:
                recommendations.append("✅ Calidad de datos excelente - Listo para backtesting")
            
            # Limitar a máximo 5 recomendaciones
            return recommendations[:5]
            
        except Exception as e:
            logger.error(f"❌ Error generando recomendaciones: {e}")
            return ["⚠️ Error generando recomendaciones"]
    
# 🔧 FIX PARA gap_detector.py - Líneas 380-450 aproximadamente

    def save_gap_report_to_database(self, report: DataQualityReport) -> bool:
        """Guardar reporte de gaps en base de datos - FIXED para SQLite"""
        try:
            # Intentar usar base de datos del sistema si está disponible
            try:
                from database.connection import save_gap_report
                
                # 🔧 FIXED: Convertir el objeto DataQualityReport a diccionario con timestamps correctos
                report_data = {
                    'symbol': report.symbol,
                    'analysis_time': report.analysis_time.isoformat() if hasattr(report.analysis_time, 'isoformat') else str(report.analysis_time),
                    'analysis_period': (
                        report.analysis_period[0].isoformat() if hasattr(report.analysis_period[0], 'isoformat') else str(report.analysis_period[0]),
                        report.analysis_period[1].isoformat() if hasattr(report.analysis_period[1], 'isoformat') else str(report.analysis_period[1])
                    ),
                    'total_data_points': report.total_data_points,
                    'expected_data_points': report.expected_data_points,
                    'completeness_pct': report.completeness_pct,
                    'total_gaps': report.total_gaps,
                    'overall_quality_score': report.overall_quality_score,
                    'is_suitable_for_backtesting': report.is_suitable_for_backtesting,
                    'gaps_by_type': report.gaps_by_type,
                    'gaps_by_severity': report.gaps_by_severity,
                    'max_gap_duration_hours': report.max_gap_duration_hours,
                    'avg_gap_duration_minutes': report.avg_gap_duration_minutes,
                    'price_anomalies_count': report.price_anomalies_count,
                    'volume_anomalies_count': report.volume_anomalies_count,
                    'recommended_actions': report.recommended_actions,
                    'extended_hours_used': getattr(report, 'extended_hours_used', False),
                    'gaps_detected': report.gaps_detected  # Lista de objetos Gap
                }
                
                # Usar la función del sistema de database
                success = save_gap_report(report_data)
                
                if success:
                    logger.info(f"💾 {report.symbol}: Reporte de gaps guardado en base de datos del sistema")
                    return True
                else:
                    logger.warning(f"⚠️ {report.symbol}: Error guardando con función del sistema, intentando fallback")
                    
            except ImportError:
                logger.debug("Sistema de database no disponible, usando fallback")
            except Exception as system_error:
                logger.warning(f"⚠️ Error con sistema de database: {system_error}, usando fallback")
            
            # 🔧 FALLBACK: Crear conexión local si no hay base de datos del sistema
            db_path = Path("gap_analysis.db")
            conn = sqlite3.connect(db_path)
            
            # Crear tabla si no existe
            conn.execute('''
            CREATE TABLE IF NOT EXISTS gap_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                analysis_time TIMESTAMP NOT NULL,
                completeness_pct REAL,
                total_gaps INTEGER,
                quality_score REAL,
                is_suitable_for_backtesting BOOLEAN,
                gaps_by_type TEXT,
                recommended_actions TEXT,
                analysis_period_start TIMESTAMP,
                analysis_period_end TIMESTAMP
            )
            ''')
            
            cursor = conn.cursor()
            
            # 🔧 FIXED: Convertir TODOS los timestamps a strings antes de insertar
            analysis_time_str = report.analysis_time.isoformat() if hasattr(report.analysis_time, 'isoformat') else str(report.analysis_time)
            period_start_str = report.analysis_period[0].isoformat() if hasattr(report.analysis_period[0], 'isoformat') else str(report.analysis_period[0])
            period_end_str = report.analysis_period[1].isoformat() if hasattr(report.analysis_period[1], 'isoformat') else str(report.analysis_period[1])
            
            # Preparar datos para insertar
            gaps_by_type_json = json.dumps(report.gaps_by_type) if isinstance(report.gaps_by_type, dict) else str(report.gaps_by_type)
            recommendations_text = "; ".join(report.recommended_actions) if isinstance(report.recommended_actions, list) else str(report.recommended_actions)
            
            # Insertar reporte con timestamps convertidos
            cursor.execute('''
            INSERT INTO gap_reports (
                symbol, analysis_time, completeness_pct, total_gaps, 
                quality_score, is_suitable_for_backtesting, gaps_by_type,
                recommended_actions, analysis_period_start, analysis_period_end
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                report.symbol,
                analysis_time_str,  # 🔧 FIXED: String en lugar de timestamp
                report.completeness_pct,
                report.total_gaps,
                report.overall_quality_score,
                report.is_suitable_for_backtesting,
                gaps_by_type_json,
                recommendations_text,
                period_start_str,   # 🔧 FIXED: String en lugar de timestamp
                period_end_str      # 🔧 FIXED: String en lugar de timestamp
            ))
            
            conn.commit()
            conn.close()
            
            logger.info(f"💾 {report.symbol}: Reporte de gaps guardado en base de datos local")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error guardando reporte en BD: {e}")
            return False
    
    def get_detector_statistics(self) -> Dict[str, Any]:
        """Obtener estadísticas del detector"""
        return {
            'total_symbols_analyzed': self.detection_stats['total_symbols_analyzed'],
            'total_gaps_detected': self.detection_stats['total_gaps_detected'],
            'gaps_by_type': self.detection_stats['gaps_by_type'].copy(),
            'analysis_sessions': self.detection_stats['analysis_sessions'],
            'avg_gaps_per_symbol': (
                self.detection_stats['total_gaps_detected'] / 
                max(1, self.detection_stats['total_symbols_analyzed'])
            )
        }
    
    def print_gap_report(self, report: DataQualityReport) -> None:
        """Imprimir reporte de calidad en formato legible"""
        try:
            print(f"\n📊 REPORTE DE CALIDAD DE DATOS - {report.symbol}")
            print("=" * 60)
            
            # Información general
            print(f"📅 Período: {report.analysis_period[0].strftime('%Y-%m-%d %H:%M')} → {report.analysis_period[1].strftime('%Y-%m-%d %H:%M')}")
            print(f"📊 Datos: {report.total_data_points:,} puntos ({report.expected_data_points:,} esperados)")
            print(f"✅ Completeness: {report.completeness_pct:.1f}%")
            print(f"🎯 Score de calidad: {report.overall_quality_score:.1f}/100")
            print(f"🧪 Apto para backtesting: {'✅ SÍ' if report.is_suitable_for_backtesting else '❌ NO'}")
            
            # Gaps detectados
            print(f"\n🔍 GAPS DETECTADOS:")
            print(f"   Total: {report.total_gaps}")
            
            if report.gaps_by_type:
                print("   Por tipo:")
                for gap_type, count in report.gaps_by_type.items():
                    print(f"     • {gap_type}: {count}")
            
            if report.gaps_by_severity:
                print("   Por severidad:")
                for severity, count in report.gaps_by_severity.items():
                    print(f"     • {severity}: {count}")
            
            if report.total_gaps > 0:
                print(f"   Gap máximo: {report.max_gap_duration_hours:.1f} horas")
                print(f"   Gap promedio: {report.avg_gap_duration_minutes:.1f} minutos")
            
            # Anomalías
            print(f"\n⚠️ ANOMALÍAS:")
            print(f"   Precios: {report.price_anomalies_count}")
            print(f"   Volumen: {report.volume_anomalies_count}")
            
            # Recomendaciones
            if report.recommended_actions:
                print(f"\n💡 RECOMENDACIONES:")
                for i, action in enumerate(report.recommended_actions, 1):
                    print(f"   {i}. {action}")
            
            print("=" * 60)
            
        except Exception as e:
            logger.error(f"❌ Error imprimiendo reporte: {e}")

# =============================================================================
# FUNCIONES DE UTILIDAD
# =============================================================================

def analyze_symbol_data_quality(symbol: str, data: pd.DataFrame, 
                               expected_interval: int = 15) -> DataQualityReport:
    """
    Función de conveniencia para analizar calidad de un símbolo
    
    Args:
        symbol: Símbolo a analizar
        data: DataFrame con datos OHLCV
        expected_interval: Intervalo esperado en minutos
        
    Returns:
        Reporte de calidad completo
    """
    detector = GapDetector()
    return detector.analyze_data_quality(data, symbol, expected_interval)

def detect_gaps_in_database(symbols: List[str] = None, days_back: int = 30) -> Dict[str, List[Gap]]:
    """
    Detectar gaps en datos almacenados en base de datos
    
    Args:
        symbols: Lista de símbolos a analizar (None = todos)
        days_back: Días hacia atrás para analizar
        
    Returns:
        Diccionario {symbol: [gaps]}
    """
    try:
        from database.connection import get_connection
        
        conn = get_connection()
        if not conn:
            logger.error("❌ No se puede conectar a la base de datos")
            return {}
        
        # Determinar símbolos a analizar
        if symbols is None:
            # Obtener todos los símbolos de la BD
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT symbol FROM indicators_data")
            symbols = [row[0] for row in cursor.fetchall()]
        
        detector = GapDetector()
        results = {}
        
        for symbol in symbols:
            try:
                # Obtener datos de la BD
                end_date = datetime.now()
                start_date = end_date - timedelta(days=days_back)
                
                query = '''
                SELECT timestamp, open_price, high_price, low_price, close_price, volume
                FROM indicators_data 
                WHERE symbol = ? AND timestamp BETWEEN ? AND ?
                ORDER BY timestamp
                '''
                
                df = pd.read_sql_query(
                    query, conn, 
                    params=[symbol, start_date.isoformat(), end_date.isoformat()],
                    index_col='timestamp', parse_dates=['timestamp']
                )
                
                if not df.empty:
                    # Renombrar columnas para compatibilidad
                    df.rename(columns={
                        'open_price': 'Open', 'high_price': 'High', 
                        'low_price': 'Low', 'close_price': 'Close',
                        'volume': 'Volume'
                    }, inplace=True)
                    
                    # Detectar gaps
                    gaps = detector.detect_gaps_in_dataframe(df, symbol)
                    results[symbol] = gaps
                    
                    logger.info(f"✅ {symbol}: {len(gaps)} gaps detectados")
                else:
                    logger.warning(f"⚠️ {symbol}: Sin datos en BD")
                    results[symbol] = []
                    
            except Exception as e:
                logger.error(f"❌ Error analizando {symbol}: {e}")
                results[symbol] = []
        
        conn.close()
        return results
        
    except ImportError:
        logger.error("❌ Base de datos no disponible")
        return {}
    except Exception as e:
        logger.error(f"❌ Error general detectando gaps en BD: {e}")
        return {}

def generate_gap_summary_report(gap_results: Dict[str, List[Gap]]) -> None:
    """
    Generar reporte resumen de gaps para múltiples símbolos
    
    Args:
        gap_results: Diccionario {symbol: [gaps]} de resultados
    """
    try:
        print("\n📊 REPORTE RESUMEN DE GAPS")
        print("=" * 60)
        
        total_symbols = len(gap_results)
        total_gaps = sum(len(gaps) for gaps in gap_results.values())
        
        print(f"📈 Símbolos analizados: {total_symbols}")
        print(f"🔍 Total gaps detectados: {total_gaps}")
        
        if total_gaps == 0:
            print("✅ No se detectaron gaps en ningún símbolo")
            return
        
        # Estadísticas por tipo
        gap_types = {}
        gap_severities = {}
        
        for symbol, gaps in gap_results.items():
            for gap in gaps:
                gap_type = gap.gap_type.value
                severity = gap.severity.value
                gap_types[gap_type] = gap_types.get(gap_type, 0) + 1
                gap_severities[severity] = gap_severities.get(severity, 0) + 1
        
        print(f"\n📊 Gaps por tipo:")
        for gap_type, count in sorted(gap_types.items()):
            print(f"   • {gap_type}: {count}")
        
        print(f"\n⚠️ Gaps por severidad:")
        for severity, count in sorted(gap_severities.items()):
            print(f"   • {severity}: {count}")
        
        # Top símbolos con más gaps
        symbols_by_gaps = sorted(
            [(symbol, len(gaps)) for symbol, gaps in gap_results.items()],
            key=lambda x: x[1], reverse=True
        )
        
        print(f"\n🎯 Top símbolos con más gaps:")
        for symbol, gap_count in symbols_by_gaps[:5]:
            if gap_count > 0:
                print(f"   • {symbol}: {gap_count} gaps")
        
        # Símbolos críticos
        critical_symbols = []
        for symbol, gaps in gap_results.items():
            critical_gaps = [g for g in gaps if g.severity == GapSeverity.CRITICAL]
            if critical_gaps:
                critical_symbols.append((symbol, len(critical_gaps)))
        
        if critical_symbols:
            print(f"\n🚨 Símbolos con gaps críticos:")
            for symbol, critical_count in critical_symbols:
                print(f"   • {symbol}: {critical_count} gaps críticos")
        
        print("=" * 60)
        
    except Exception as e:
        logger.error(f"❌ Error generando reporte resumen: {e}")

# =============================================================================
# FUNCIONES DE TESTING Y DEMO
# =============================================================================

def test_gap_detector_basic():
    """Test básico del gap detector"""
    print("🧪 TESTING GAP DETECTOR BÁSICO")
    print("=" * 50)
    
    try:
        # Crear datos de prueba con gaps artificiales
        dates = pd.date_range('2024-01-01 09:30', '2024-01-01 16:00', freq='15T')
        data = pd.DataFrame({
            'Open': np.random.uniform(100, 105, len(dates)),
            'High': np.random.uniform(104, 110, len(dates)),
            'Low': np.random.uniform(95, 101, len(dates)),
            'Close': np.random.uniform(100, 105, len(dates)),
            'Volume': np.random.randint(1000000, 5000000, len(dates))
        }, index=dates)
        
        # Crear gap artificial (eliminar datos de 12:00 a 13:30)
        gap_start = pd.Timestamp('2024-01-01 12:00')
        gap_end = pd.Timestamp('2024-01-01 13:30')
        data = data[~((data.index >= gap_start) & (data.index <= gap_end))]
        
        print(f"📊 Datos de prueba creados: {len(data)} puntos")
        print(f"🔍 Gap artificial: {gap_start} → {gap_end} (90 min)")
        
        # Detectar gaps
        detector = GapDetector()
        gaps = detector.detect_gaps_in_dataframe(data, "TEST", 15)
        
        print(f"\n✅ Gaps detectados: {len(gaps)}")
        
        for i, gap in enumerate(gaps, 1):
            print(f"   {i}. {gap.gap_type.value} - {gap.duration_minutes:.0f} min")
            print(f"      {gap.start_time} → {gap.end_time}")
            print(f"      Severidad: {gap.severity.value}")
            print(f"      Confianza: {gap.confidence:.2f}")
        
        # Análisis de calidad
        report = detector.analyze_data_quality(data, "TEST", 15)
        detector.print_gap_report(report)
        
        print("✅ Test básico completado")
        return True
        
    except Exception as e:
        print(f"❌ Error en test básico: {e}")
        return False

def demo_gap_detector_with_real_data():
    """Demo con datos reales del sistema"""
    print("🧪 DEMO GAP DETECTOR CON DATOS REALES")
    print("=" * 50)
    
    try:
        # Intentar usar indicators para obtener datos reales
        try:
            from indicators import TechnicalIndicators
            
            indicators = TechnicalIndicators()
            symbol = "SPY"
            
            print(f"📊 Obteniendo datos reales para {symbol}...")
            result = indicators.get_all_indicators(symbol)
            
            if 'market_data' in result and not result['market_data'].empty:
                data = result['market_data']
                
                print(f"✅ Datos obtenidos: {len(data)} barras")
                
                # Analizar calidad
                detector = GapDetector()
                report = detector.analyze_data_quality(data, symbol, 15)
                
                # Mostrar reporte
                detector.print_gap_report(report)
                
                # Mostrar gaps individuales si hay pocos
                if len(report.gaps_detected) <= 10:
                    print(f"\n🔍 DETALLE DE GAPS:")
                    for i, gap in enumerate(report.gaps_detected, 1):
                        print(f"   {i}. {gap.gap_type.value}")
                        print(f"      📅 {gap.start_time} → {gap.end_time}")
                        print(f"      ⏱️ Duración: {gap.duration_minutes:.0f} min")
                        print(f"      💰 Cambio precio: {gap.price_change_pct:+.2f}%")
                        print(f"      🎯 Estrategia: {gap.suggested_strategy}")
                        print(f"      ✅ Rellenable: {'Sí' if gap.is_fillable else 'No'}")
                        print()
                
                print("✅ Demo con datos reales completado")
                return True
            else:
                print("⚠️ No se pudieron obtener datos del indicador")
                return False
                
        except ImportError:
            print("⚠️ Módulo indicators no disponible, usando test básico")
            return test_gap_detector_basic()
            
    except Exception as e:
        print(f"❌ Error en demo: {e}")
        return False

if __name__ == "__main__":
    """Ejecutar tests si se ejecuta directamente"""
    print("🔍 GAP DETECTOR V3.1 - SISTEMA DE DETECCIÓN DE GAPS")
    print("=" * 70)
    
    # Test básico
    print("1️⃣ Ejecutando test básico...")
    basic_success = test_gap_detector_basic()
    
    if basic_success:
        print("\n2️⃣ Ejecutando demo con datos reales...")
        demo_success = demo_gap_detector_with_real_data()
        
        if demo_success:
            print("\n3️⃣ Ejecutando análisis de base de datos...")
            try:
                # Test de análisis de BD (solo si está disponible)
                gap_results = detect_gaps_in_database(["SPY", "AAPL"], days_back=7)
                if gap_results:
                    generate_gap_summary_report(gap_results)
                else:
                    print("⚠️ No se pudo acceder a la base de datos o sin datos")
            except Exception as e:
                print(f"⚠️ Test de BD omitido: {e}")
    
    print(f"\n🏁 Tests Gap Detector V3.1 completados")
    print("📍 Ubicación: Guardar como gap_detector.py en el directorio principal")