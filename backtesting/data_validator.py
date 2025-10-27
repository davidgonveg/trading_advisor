#!/usr/bin/env python3
"""
✅ DATA VALIDATOR - Validación de Datos Históricos para Backtesting
===================================================================

Valida la calidad de los datos históricos antes de ejecutar backtesting.
Garantiza que los datos sean completos, consistentes y aptos para backtesting.
"""

import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
import sys
from pathlib import Path

# Añadir path del proyecto
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from database.connection import get_connection

logger = logging.getLogger(__name__)


class ValidationSeverity(Enum):
    """Severidad de problemas encontrados"""
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


@dataclass
class ValidationIssue:
    """Problema encontrado en la validación"""
    severity: ValidationSeverity
    category: str  # 'GAPS', 'OHLC', 'INDICATORS', 'VOLUME', etc.
    description: str
    timestamp: Optional[datetime] = None
    value: Optional[Any] = None
    recommendation: Optional[str] = None


@dataclass
class ValidationReport:
    """Reporte completo de validación de datos"""
    symbol: str
    validation_time: datetime
    period_start: datetime
    period_end: datetime

    # Datos básicos
    total_rows: int = 0
    expected_rows: int = 0
    completeness_pct: float = 0.0

    # Problemas encontrados
    issues: List[ValidationIssue] = field(default_factory=list)

    # Scores por categoría (0-100)
    ohlc_score: float = 0.0
    indicators_score: float = 0.0
    volume_score: float = 0.0
    gaps_score: float = 0.0
    consistency_score: float = 0.0

    # Score general
    overall_score: float = 0.0

    # Aptitud para backtesting
    is_backtest_ready: bool = False
    backtest_readiness_reasons: List[str] = field(default_factory=list)

    # Estadísticas adicionales
    gaps_found: int = 0
    largest_gap_hours: float = 0.0
    missing_indicators_count: int = 0
    ohlc_violations: int = 0
    volume_anomalies: int = 0

    def add_issue(self, severity: ValidationSeverity, category: str,
                  description: str, timestamp: Optional[datetime] = None,
                  value: Optional[Any] = None, recommendation: Optional[str] = None):
        """Añadir un problema al reporte"""
        self.issues.append(ValidationIssue(
            severity=severity,
            category=category,
            description=description,
            timestamp=timestamp,
            value=value,
            recommendation=recommendation
        ))

    def get_critical_issues(self) -> List[ValidationIssue]:
        """Obtener solo problemas críticos"""
        return [i for i in self.issues if i.severity == ValidationSeverity.CRITICAL]

    def get_errors(self) -> List[ValidationIssue]:
        """Obtener errores"""
        return [i for i in self.issues if i.severity == ValidationSeverity.ERROR]

    def get_warnings(self) -> List[ValidationIssue]:
        """Obtener warnings"""
        return [i for i in self.issues if i.severity == ValidationSeverity.WARNING]

    def summary(self) -> str:
        """Generar resumen del reporte"""
        critical = len(self.get_critical_issues())
        errors = len(self.get_errors())
        warnings = len(self.get_warnings())

        status = "✅ READY" if self.is_backtest_ready else "❌ NOT READY"

        return f"""
╔═══════════════════════════════════════════════════════════════╗
║  VALIDATION REPORT - {self.symbol}
╠═══════════════════════════════════════════════════════════════╣
║  Status: {status}
║  Overall Score: {self.overall_score:.1f}/100
║
║  Period: {self.period_start.strftime('%Y-%m-%d')} to {self.period_end.strftime('%Y-%m-%d')}
║  Rows: {self.total_rows:,} / {self.expected_rows:,} ({self.completeness_pct:.1f}%)
║
║  📊 Scores:
║    • OHLC:        {self.ohlc_score:.1f}/100
║    • Indicators:  {self.indicators_score:.1f}/100
║    • Volume:      {self.volume_score:.1f}/100
║    • Gaps:        {self.gaps_score:.1f}/100
║    • Consistency: {self.consistency_score:.1f}/100
║
║  🔍 Issues Found:
║    • Critical: {critical}
║    • Errors:   {errors}
║    • Warnings: {warnings}
║
║  📋 Gaps: {self.gaps_found} (largest: {self.largest_gap_hours:.1f}h)
║  ⚠️  OHLC violations: {self.ohlc_violations}
║  📉 Volume anomalies: {self.volume_anomalies}
║  🔢 Missing indicators: {self.missing_indicators_count}
╚═══════════════════════════════════════════════════════════════╝
"""


class DataValidator:
    """Validador de datos históricos para backtesting"""

    def __init__(self, expected_interval_minutes: int = 15):
        """
        Inicializar validador

        Args:
            expected_interval_minutes: Intervalo esperado entre datos (15 min default)
        """
        self.expected_interval = timedelta(minutes=expected_interval_minutes)
        self.expected_interval_minutes = expected_interval_minutes

        # Umbrales de validación
        self.min_completeness = 90.0  # % mínimo de datos completos
        self.max_gap_hours = 24.0     # Gap máximo aceptable
        self.min_volume = 1000        # Volumen mínimo razonable

        logger.info(f"✅ DataValidator inicializado (interval={expected_interval_minutes}min)")

    def validate_symbol(self, symbol: str, start_date: Optional[datetime] = None,
                       end_date: Optional[datetime] = None) -> ValidationReport:
        """
        Validar datos históricos de un símbolo

        Args:
            symbol: Símbolo a validar
            start_date: Fecha inicio (None = usar todos los datos)
            end_date: Fecha fin (None = usar todos los datos)

        Returns:
            ValidationReport con resultados de la validación
        """
        logger.info(f"🔍 Validando datos de {symbol}...")

        # Crear reporte
        report = ValidationReport(
            symbol=symbol,
            validation_time=datetime.now(),
            period_start=start_date or datetime(2020, 1, 1),
            period_end=end_date or datetime.now()
        )

        try:
            # 1. Cargar datos desde la base de datos
            df = self._load_data_from_db(symbol, start_date, end_date)

            if df is None or df.empty:
                report.add_issue(
                    ValidationSeverity.CRITICAL,
                    "DATA",
                    f"No se encontraron datos para {symbol}",
                    recommendation="Ejecutar populate_db.py para cargar datos históricos"
                )
                report.overall_score = 0.0
                report.is_backtest_ready = False
                report.backtest_readiness_reasons.append("Sin datos disponibles")
                return report

            report.total_rows = len(df)
            report.period_start = df['timestamp'].min()
            report.period_end = df['timestamp'].max()

            # 2. Validar completitud (gaps)
            gaps_score, gaps_found, largest_gap = self._validate_gaps(df, report)
            report.gaps_score = gaps_score
            report.gaps_found = gaps_found
            report.largest_gap_hours = largest_gap

            # 3. Validar OHLC
            ohlc_score, violations = self._validate_ohlc(df, report)
            report.ohlc_score = ohlc_score
            report.ohlc_violations = violations

            # 4. Validar indicadores
            indicators_score, missing_count = self._validate_indicators(df, report)
            report.indicators_score = indicators_score
            report.missing_indicators_count = missing_count

            # 5. Validar volumen
            volume_score, anomalies = self._validate_volume(df, report)
            report.volume_score = volume_score
            report.volume_anomalies = anomalies

            # 6. Validar consistencia temporal
            consistency_score = self._validate_consistency(df, report)
            report.consistency_score = consistency_score

            # 7. Calcular expected rows
            report.expected_rows = self._calculate_expected_rows(
                report.period_start, report.period_end
            )
            report.completeness_pct = (report.total_rows / report.expected_rows * 100) if report.expected_rows > 0 else 0

            # 8. Calcular score general
            report.overall_score = self._calculate_overall_score(
                gaps_score, ohlc_score, indicators_score, volume_score, consistency_score
            )

            # 9. Determinar si está listo para backtesting
            report.is_backtest_ready, reasons = self._evaluate_backtest_readiness(report)
            report.backtest_readiness_reasons = reasons

            logger.info(f"✅ Validación completada: {symbol} - Score: {report.overall_score:.1f}/100")

            return report

        except Exception as e:
            logger.error(f"❌ Error validando {symbol}: {e}")
            report.add_issue(
                ValidationSeverity.CRITICAL,
                "ERROR",
                f"Error durante validación: {str(e)}"
            )
            report.overall_score = 0.0
            report.is_backtest_ready = False
            return report

    def _load_data_from_db(self, symbol: str, start_date: Optional[datetime],
                           end_date: Optional[datetime]) -> Optional[pd.DataFrame]:
        """Cargar datos desde la base de datos"""
        try:
            conn = get_connection()
            if not conn:
                return None

            # Query para obtener datos
            query = """
            SELECT
                timestamp, symbol,
                open_price, high_price, low_price, close_price, volume,
                rsi_value, macd_line, macd_signal, macd_histogram,
                vwap_value, vwap_deviation_pct, roc_value,
                bb_upper, bb_middle, bb_lower, bb_position,
                volume_oscillator, atr_value, atr_percentage,
                market_regime, volatility_level
            FROM indicators_data
            WHERE symbol = ?
            """

            params = [symbol]

            if start_date:
                query += " AND timestamp >= ?"
                params.append(start_date.isoformat())

            if end_date:
                query += " AND timestamp <= ?"
                params.append(end_date.isoformat())

            query += " ORDER BY timestamp ASC"

            df = pd.read_sql_query(query, conn, params=params)
            conn.close()

            if df.empty:
                return None

            # Convertir timestamp a datetime
            df['timestamp'] = pd.to_datetime(df['timestamp'])

            return df

        except Exception as e:
            logger.error(f"❌ Error cargando datos de {symbol}: {e}")
            return None

    def _validate_gaps(self, df: pd.DataFrame, report: ValidationReport) -> Tuple[float, int, float]:
        """Validar gaps en los datos"""
        try:
            gaps_found = 0
            largest_gap_hours = 0.0

            # Calcular diferencias entre timestamps consecutivos
            df = df.sort_values('timestamp')
            time_diffs = df['timestamp'].diff()

            # Identificar gaps (diferencias mayores al intervalo esperado)
            # Permitir cierta tolerancia (1.5x el intervalo esperado)
            tolerance = self.expected_interval * 1.5
            gaps = time_diffs[time_diffs > tolerance]

            gaps_found = len(gaps)

            if gaps_found > 0:
                largest_gap = gaps.max()
                largest_gap_hours = largest_gap.total_seconds() / 3600

                # Añadir issues según severidad
                if largest_gap_hours > 72:  # Más de 3 días
                    report.add_issue(
                        ValidationSeverity.CRITICAL,
                        "GAPS",
                        f"Gap crítico de {largest_gap_hours:.1f} horas detectado",
                        recommendation="Rellenar gaps usando historical_data/downloader.py"
                    )
                elif largest_gap_hours > 24:  # Más de 1 día
                    report.add_issue(
                        ValidationSeverity.ERROR,
                        "GAPS",
                        f"Gap significativo de {largest_gap_hours:.1f} horas",
                        recommendation="Verificar datos y considerar rellenar gaps"
                    )
                elif gaps_found > 10:
                    report.add_issue(
                        ValidationSeverity.WARNING,
                        "GAPS",
                        f"{gaps_found} gaps pequeños encontrados",
                        recommendation="Aceptable para backtesting, pero puede mejorar"
                    )

            # Calcular score (100 = sin gaps, 0 = muchos gaps)
            max_acceptable_gaps = len(df) * 0.05  # 5% de gaps es aceptable
            if gaps_found == 0:
                score = 100.0
            elif gaps_found <= max_acceptable_gaps:
                score = 100.0 - (gaps_found / max_acceptable_gaps * 20)
            else:
                score = max(0.0, 80.0 - (gaps_found / len(df) * 100))

            # Penalizar por tamaño del gap más grande
            if largest_gap_hours > 24:
                score *= 0.7
            elif largest_gap_hours > 8:
                score *= 0.9

            return score, gaps_found, largest_gap_hours

        except Exception as e:
            logger.error(f"❌ Error validando gaps: {e}")
            return 0.0, 0, 0.0

    def _validate_ohlc(self, df: pd.DataFrame, report: ValidationReport) -> Tuple[float, int]:
        """Validar consistencia de datos OHLC"""
        violations = 0

        try:
            # Reglas de validación OHLC:
            # 1. High >= Low
            # 2. High >= Open
            # 3. High >= Close
            # 4. Low <= Open
            # 5. Low <= Close
            # 6. Valores no negativos
            # 7. Valores no NaN

            invalid_high_low = df[df['high_price'] < df['low_price']]
            if len(invalid_high_low) > 0:
                violations += len(invalid_high_low)
                report.add_issue(
                    ValidationSeverity.ERROR,
                    "OHLC",
                    f"{len(invalid_high_low)} filas con High < Low",
                    recommendation="Datos corruptos, necesitan corrección"
                )

            invalid_high_open = df[df['high_price'] < df['open_price']]
            if len(invalid_high_open) > 0:
                violations += len(invalid_high_open)
                report.add_issue(
                    ValidationSeverity.ERROR,
                    "OHLC",
                    f"{len(invalid_high_open)} filas con High < Open"
                )

            invalid_high_close = df[df['high_price'] < df['close_price']]
            if len(invalid_high_close) > 0:
                violations += len(invalid_high_close)
                report.add_issue(
                    ValidationSeverity.ERROR,
                    "OHLC",
                    f"{len(invalid_high_close)} filas con High < Close"
                )

            invalid_low_open = df[df['low_price'] > df['open_price']]
            if len(invalid_low_open) > 0:
                violations += len(invalid_low_open)
                report.add_issue(
                    ValidationSeverity.ERROR,
                    "OHLC",
                    f"{len(invalid_low_open)} filas con Low > Open"
                )

            invalid_low_close = df[df['low_price'] > df['close_price']]
            if len(invalid_low_close) > 0:
                violations += len(invalid_low_close)
                report.add_issue(
                    ValidationSeverity.ERROR,
                    "OHLC",
                    f"{len(invalid_low_close)} filas con Low > Close"
                )

            # Validar valores negativos
            negative_prices = df[(df['open_price'] <= 0) | (df['high_price'] <= 0) |
                                (df['low_price'] <= 0) | (df['close_price'] <= 0)]
            if len(negative_prices) > 0:
                violations += len(negative_prices)
                report.add_issue(
                    ValidationSeverity.CRITICAL,
                    "OHLC",
                    f"{len(negative_prices)} filas con precios negativos o cero",
                    recommendation="Datos inválidos, deben ser corregidos"
                )

            # Validar NaN
            nan_prices = df[df[['open_price', 'high_price', 'low_price', 'close_price']].isna().any(axis=1)]
            if len(nan_prices) > 0:
                violations += len(nan_prices)
                report.add_issue(
                    ValidationSeverity.ERROR,
                    "OHLC",
                    f"{len(nan_prices)} filas con valores NaN en OHLC",
                    recommendation="Eliminar o rellenar valores faltantes"
                )

            # Calcular score
            if violations == 0:
                score = 100.0
            else:
                violation_rate = violations / len(df)
                if violation_rate > 0.1:  # Más del 10% inválido
                    score = 0.0
                elif violation_rate > 0.05:  # Más del 5% inválido
                    score = 50.0
                else:
                    score = 100.0 - (violation_rate * 1000)

            return max(0.0, score), violations

        except Exception as e:
            logger.error(f"❌ Error validando OHLC: {e}")
            return 0.0, 0

    def _validate_indicators(self, df: pd.DataFrame, report: ValidationReport) -> Tuple[float, int]:
        """Validar indicadores técnicos"""
        missing_count = 0

        try:
            # Indicadores requeridos
            required_indicators = [
                'rsi_value', 'macd_line', 'macd_signal', 'macd_histogram',
                'vwap_value', 'roc_value', 'bb_upper', 'bb_middle', 'bb_lower',
                'atr_value', 'volume_oscillator'
            ]

            for indicator in required_indicators:
                if indicator not in df.columns:
                    missing_count += 1
                    report.add_issue(
                        ValidationSeverity.CRITICAL,
                        "INDICATORS",
                        f"Indicador faltante: {indicator}",
                        recommendation="Ejecutar historical_indicators_calc.py"
                    )
                else:
                    # Contar NaN
                    nan_count = df[indicator].isna().sum()
                    if nan_count > 0:
                        nan_pct = (nan_count / len(df)) * 100
                        if nan_pct > 10:
                            missing_count += 1
                            report.add_issue(
                                ValidationSeverity.ERROR,
                                "INDICATORS",
                                f"{indicator}: {nan_pct:.1f}% valores faltantes",
                                recommendation="Recalcular indicadores"
                            )
                        elif nan_pct > 5:
                            report.add_issue(
                                ValidationSeverity.WARNING,
                                "INDICATORS",
                                f"{indicator}: {nan_pct:.1f}% valores faltantes"
                            )

            # Calcular score
            if missing_count == 0:
                score = 100.0
            else:
                score = max(0.0, 100.0 - (missing_count / len(required_indicators) * 100))

            return score, missing_count

        except Exception as e:
            logger.error(f"❌ Error validando indicadores: {e}")
            return 0.0, 0

    def _validate_volume(self, df: pd.DataFrame, report: ValidationReport) -> Tuple[float, int]:
        """Validar datos de volumen"""
        anomalies = 0

        try:
            # Validar volumen
            zero_volume = df[df['volume'] == 0]
            if len(zero_volume) > 0:
                zero_pct = (len(zero_volume) / len(df)) * 100
                if zero_pct > 5:
                    anomalies += len(zero_volume)
                    report.add_issue(
                        ValidationSeverity.WARNING,
                        "VOLUME",
                        f"{zero_pct:.1f}% de filas con volumen cero",
                        recommendation="Normal en índices, pero verificar en acciones"
                    )

            negative_volume = df[df['volume'] < 0]
            if len(negative_volume) > 0:
                anomalies += len(negative_volume)
                report.add_issue(
                    ValidationSeverity.ERROR,
                    "VOLUME",
                    f"{len(negative_volume)} filas con volumen negativo",
                    recommendation="Datos inválidos"
                )

            # Detectar volumen anormalmente alto (outliers)
            if len(df) > 100:
                volume_mean = df['volume'].mean()
                volume_std = df['volume'].std()
                outliers = df[df['volume'] > volume_mean + 10 * volume_std]
                if len(outliers) > 0:
                    report.add_issue(
                        ValidationSeverity.INFO,
                        "VOLUME",
                        f"{len(outliers)} filas con volumen anormalmente alto",
                        recommendation="Puede ser normal (noticias, earnings)"
                    )

            # Calcular score
            if anomalies == 0:
                score = 100.0
            else:
                anomaly_rate = anomalies / len(df)
                score = max(0.0, 100.0 - (anomaly_rate * 200))

            return score, anomalies

        except Exception as e:
            logger.error(f"❌ Error validando volumen: {e}")
            return 0.0, 0

    def _validate_consistency(self, df: pd.DataFrame, report: ValidationReport) -> float:
        """Validar consistencia temporal y orden"""
        try:
            # Verificar orden cronológico
            timestamps_sorted = df['timestamp'].is_monotonic_increasing
            if not timestamps_sorted:
                report.add_issue(
                    ValidationSeverity.WARNING,
                    "CONSISTENCY",
                    "Datos no están ordenados cronológicamente",
                    recommendation="Se reordenarán automáticamente en backtesting"
                )
                return 90.0

            # Verificar duplicados
            duplicates = df[df.duplicated(subset=['timestamp'], keep=False)]
            if len(duplicates) > 0:
                report.add_issue(
                    ValidationSeverity.ERROR,
                    "CONSISTENCY",
                    f"{len(duplicates)} timestamps duplicados encontrados",
                    recommendation="Eliminar duplicados"
                )
                return 70.0

            return 100.0

        except Exception as e:
            logger.error(f"❌ Error validando consistencia: {e}")
            return 50.0

    def _calculate_expected_rows(self, start: datetime, end: datetime) -> int:
        """Calcular número esperado de filas basado en el período"""
        try:
            # Calcular días laborables (simplificado)
            total_days = (end - start).days
            trading_days = total_days * (5/7)  # Aprox 5 días de 7

            # Sesiones por día (asumiendo 2 sesiones de trading)
            hours_per_day = 5.5  # Aprox 5.5 horas de mercado
            intervals_per_day = (hours_per_day * 60) / self.expected_interval_minutes

            expected = int(trading_days * intervals_per_day)
            return max(1, expected)

        except Exception as e:
            logger.error(f"❌ Error calculando expected rows: {e}")
            return 1

    def _calculate_overall_score(self, gaps_score: float, ohlc_score: float,
                                 indicators_score: float, volume_score: float,
                                 consistency_score: float) -> float:
        """Calcular score general ponderado"""
        # Ponderaciones
        weights = {
            'gaps': 0.25,
            'ohlc': 0.30,
            'indicators': 0.25,
            'volume': 0.10,
            'consistency': 0.10
        }

        overall = (
            gaps_score * weights['gaps'] +
            ohlc_score * weights['ohlc'] +
            indicators_score * weights['indicators'] +
            volume_score * weights['volume'] +
            consistency_score * weights['consistency']
        )

        return round(overall, 2)

    def _evaluate_backtest_readiness(self, report: ValidationReport) -> Tuple[bool, List[str]]:
        """Evaluar si los datos están listos para backtesting"""
        reasons = []

        # Criterios para estar listo
        is_ready = True

        # 1. Score general mínimo
        if report.overall_score < 70.0:
            is_ready = False
            reasons.append(f"Score general bajo ({report.overall_score:.1f}/100)")

        # 2. Sin problemas críticos
        critical_issues = report.get_critical_issues()
        if len(critical_issues) > 0:
            is_ready = False
            reasons.append(f"{len(critical_issues)} problemas críticos")

        # 3. Completitud mínima
        if report.completeness_pct < 85.0:
            is_ready = False
            reasons.append(f"Completitud baja ({report.completeness_pct:.1f}%)")

        # 4. Gaps no muy grandes
        if report.largest_gap_hours > 72:
            is_ready = False
            reasons.append(f"Gap muy grande ({report.largest_gap_hours:.1f}h)")

        # 5. Indicadores completos
        if report.missing_indicators_count > 2:
            is_ready = False
            reasons.append(f"{report.missing_indicators_count} indicadores faltantes")

        # 6. OHLC válido
        if report.ohlc_score < 90.0:
            is_ready = False
            reasons.append(f"Problemas en datos OHLC (score {report.ohlc_score:.1f})")

        # 7. Datos mínimos
        if report.total_rows < 100:
            is_ready = False
            reasons.append("Muy pocos datos disponibles (<100 filas)")

        if is_ready:
            reasons.append("✅ Todos los criterios cumplidos")

        return is_ready, reasons


def validate_all_symbols(symbols: List[str], start_date: Optional[datetime] = None,
                        end_date: Optional[datetime] = None) -> Dict[str, ValidationReport]:
    """
    Validar múltiples símbolos

    Args:
        symbols: Lista de símbolos a validar
        start_date: Fecha inicio
        end_date: Fecha fin

    Returns:
        Diccionario con reportes por símbolo
    """
    validator = DataValidator()
    reports = {}

    logger.info(f"🔍 Validando {len(symbols)} símbolos...")

    for i, symbol in enumerate(symbols, 1):
        logger.info(f"[{i}/{len(symbols)}] Validando {symbol}...")
        report = validator.validate_symbol(symbol, start_date, end_date)
        reports[symbol] = report

    # Resumen
    ready_count = sum(1 for r in reports.values() if r.is_backtest_ready)
    avg_score = np.mean([r.overall_score for r in reports.values()])

    logger.info(f"✅ Validación completada:")
    logger.info(f"   Símbolos ready: {ready_count}/{len(symbols)}")
    logger.info(f"   Score promedio: {avg_score:.1f}/100")

    return reports


if __name__ == "__main__":
    # Test del validador
    logging.basicConfig(level=logging.INFO)

    print("🔍 DATA VALIDATOR - TEST")
    print("=" * 70)

    # Validar un símbolo
    validator = DataValidator()
    report = validator.validate_symbol("AAPL")

    print(report.summary())

    # Mostrar issues críticos si los hay
    critical = report.get_critical_issues()
    if critical:
        print("\n🚨 CRITICAL ISSUES:")
        for issue in critical:
            print(f"   • {issue.description}")
            if issue.recommendation:
                print(f"     💡 {issue.recommendation}")
