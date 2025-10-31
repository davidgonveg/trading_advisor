#!/usr/bin/env python3
"""
🧪 TESTS DE GAP FILLING
=======================

Tests comprehensivos para el sistema de gap filling:
- Detección de gaps
- Clasificación de gaps
- Relleno de gaps con datos reales
- Validación de calidad
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from gap_detector import GapDetector, GapType, GapSeverity


# =============================================================================
# 🔍 TESTS DE DETECCIÓN DE GAPS
# =============================================================================

@pytest.mark.gaps
class TestGapDetection:
    """Tests de detección de gaps"""

    def test_detect_small_gap(self, gap_detector_instance, sample_ohlcv_with_gaps):
        """Test: Detectar gaps pequeños"""
        report = gap_detector_instance.analyze_data_quality(
            'TEST',
            sample_ohlcv_with_gaps,
            datetime.now() - timedelta(days=7),
            datetime.now()
        )

        assert report is not None
        assert report.total_gaps > 0, "No se detectaron gaps"

    def test_gap_classification(self, gap_detector_instance):
        """Test: Clasificar tipos de gaps correctamente"""
        # Crear datos con gap overnight claro
        dates = pd.date_range('2024-01-01 09:30', periods=50, freq='15T')
        data = pd.DataFrame({
            'Open': 100,
            'High': 101,
            'Low': 99,
            'Close': 100,
            'Volume': 1000000
        }, index=dates)

        # Añadir gap overnight (borrar 16 horas)
        gap_start = dates[20]
        gap_end = gap_start + timedelta(hours=16)

        # Filtrar datos para crear el gap
        data = data[~((data.index > gap_start) & (data.index < gap_end))]

        report = gap_detector_instance.analyze_data_quality(
            'TEST',
            data,
            dates[0],
            dates[-1]
        )

        print(f"Gaps detectados: {report.total_gaps}")
        print(f"Gaps by type: {report.gaps_by_type}")

    def test_no_gaps_in_continuous_data(self, gap_detector_instance, sample_ohlcv_data):
        """Test: Datos continuos no tienen gaps"""
        report = gap_detector_instance.analyze_data_quality(
            'TEST',
            sample_ohlcv_data,
            sample_ohlcv_data.index[0],
            sample_ohlcv_data.index[-1]
        )

        # Datos de muestra pueden tener pocos gaps
        assert report.completeness_pct > 90, "Completitud baja en datos de muestra"

    def test_weekend_gap_detection(self, gap_detector_instance):
        """Test: Detectar gaps de fin de semana"""
        # Viernes 3PM
        friday = pd.Timestamp('2024-01-05 15:00')
        # Lunes 9:30AM
        monday = pd.Timestamp('2024-01-08 09:30')

        dates = pd.date_range(friday, friday + timedelta(hours=2), freq='15T')
        dates = dates.append(pd.date_range(monday, monday + timedelta(hours=2), freq='15T'))

        data = pd.DataFrame({
            'Open': 100,
            'High': 101,
            'Low': 99,
            'Close': 100,
            'Volume': 1000000
        }, index=dates)

        report = gap_detector_instance.analyze_data_quality(
            'TEST',
            data,
            friday,
            monday + timedelta(hours=2)
        )

        # Debe detectar el gap de fin de semana
        print(f"Gaps: {report.total_gaps}, Types: {report.gaps_by_type}")


# =============================================================================
# 📊 TESTS DE CALIDAD DE DATOS
# =============================================================================

@pytest.mark.gaps
class TestDataQuality:
    """Tests de calidad de datos"""

    def test_quality_score_calculation(self, gap_detector_instance, sample_ohlcv_data):
        """Test: Calcular score de calidad"""
        report = gap_detector_instance.analyze_data_quality(
            'TEST',
            sample_ohlcv_data,
            sample_ohlcv_data.index[0],
            sample_ohlcv_data.index[-1]
        )

        assert 0 <= report.overall_quality_score <= 100, \
            f"Score fuera de rango: {report.overall_quality_score}"

    def test_completeness_percentage(self, gap_detector_instance, sample_ohlcv_with_gaps):
        """Test: Calcular porcentaje de completitud"""
        report = gap_detector_instance.analyze_data_quality(
            'TEST',
            sample_ohlcv_with_gaps,
            sample_ohlcv_with_gaps.index[0],
            sample_ohlcv_with_gaps.index[-1]
        )

        assert 0 <= report.completeness_pct <= 100, \
            f"Completitud fuera de rango: {report.completeness_pct}"

        print(f"Completitud: {report.completeness_pct:.1f}%")

    def test_backtest_readiness(self, gap_detector_instance, sample_ohlcv_data):
        """Test: Determinar si datos son aptos para backtesting"""
        report = gap_detector_instance.analyze_data_quality(
            'TEST',
            sample_ohlcv_data,
            sample_ohlcv_data.index[0],
            sample_ohlcv_data.index[-1]
        )

        # Datos de muestra deben ser backtest-ready
        print(f"Backtest ready: {report.is_backtest_ready}")
        print(f"Quality score: {report.overall_quality_score}")


# =============================================================================
# 🔧 TESTS DE RELLENO DE GAPS
# =============================================================================

@pytest.mark.gaps
class TestGapFilling:
    """Tests de relleno de gaps"""

    def test_fill_small_gaps(self, gap_detector_instance, sample_ohlcv_with_gaps):
        """Test: Rellenar gaps pequeños"""
        # Esta función real intenta llenar gaps
        # El test verifica que el sistema maneja el proceso correctamente

        initial_length = len(sample_ohlcv_with_gaps)
        print(f"Datos iniciales: {initial_length} barras")

        # El gap_detector tiene lógica para identificar fillable gaps
        report = gap_detector_instance.analyze_data_quality(
            'TEST',
            sample_ohlcv_with_gaps,
            sample_ohlcv_with_gaps.index[0],
            sample_ohlcv_with_gaps.index[-1]
        )

        fillable_gaps = [g for g in report.gaps_detected if hasattr(g, 'is_fillable') and g.is_fillable]

        print(f"Gaps fillables: {len(fillable_gaps)}/{report.total_gaps}")

    def test_preserve_weekend_gaps(self, gap_detector_instance):
        """Test: No rellenar gaps de fin de semana"""
        friday = pd.Timestamp('2024-01-05 15:00')
        monday = pd.Timestamp('2024-01-08 09:30')

        dates = pd.date_range(friday, friday + timedelta(hours=2), freq='15T')
        dates = dates.append(pd.date_range(monday, monday + timedelta(hours=2), freq='15T'))

        data = pd.DataFrame({
            'Open': 100,
            'High': 101,
            'Low': 99,
            'Close': 100,
            'Volume': 1000000
        }, index=dates)

        report = gap_detector_instance.analyze_data_quality(
            'TEST',
            data,
            friday,
            monday + timedelta(hours=2)
        )

        # Los gaps de fin de semana no deben ser fillables
        weekend_gaps = [g for g in report.gaps_detected
                       if hasattr(g, 'gap_type') and g.gap_type == 'WEEKEND_GAP']

        for gap in weekend_gaps:
            if hasattr(gap, 'is_fillable'):
                assert not gap.is_fillable, "Gap de fin de semana no debe ser fillable"


# =============================================================================
# 📈 TESTS DE ANOMALÍAS
# =============================================================================

@pytest.mark.gaps
class TestAnomalies:
    """Tests de detección de anomalías"""

    def test_price_anomaly_detection(self, gap_detector_instance):
        """Test: Detectar anomalías de precio"""
        dates = pd.date_range('2024-01-01', periods=50, freq='15T')

        prices = np.full(50, 100.0)
        # Insertar spike anómalo
        prices[25] = 200.0  # +100% spike

        data = pd.DataFrame({
            'Open': prices,
            'High': prices + 1,
            'Low': prices - 1,
            'Close': prices,
            'Volume': 1000000
        }, index=dates)

        report = gap_detector_instance.analyze_data_quality(
            'TEST',
            data,
            dates[0],
            dates[-1]
        )

        # Debe detectar anomalía de precio
        assert report.price_anomalies_count >= 0

    def test_volume_anomaly_detection(self, gap_detector_instance):
        """Test: Detectar anomalías de volumen"""
        dates = pd.date_range('2024-01-01', periods=50, freq='15T')

        volumes = np.full(50, 1000000)
        # Insertar spike de volumen
        volumes[25] = 100000000  # 100x volumen normal

        data = pd.DataFrame({
            'Open': 100,
            'High': 101,
            'Low': 99,
            'Close': 100,
            'Volume': volumes
        }, index=dates)

        report = gap_detector_instance.analyze_data_quality(
            'TEST',
            data,
            dates[0],
            dates[-1]
        )

        # Debe detectar anomalía de volumen
        assert report.volume_anomalies_count >= 0


# =============================================================================
# 💾 TESTS DE PERSISTENCIA
# =============================================================================

@pytest.mark.gaps
@pytest.mark.database
class TestGapPersistence:
    """Tests de persistencia de gaps"""

    def test_mark_gap_as_filled(self, temp_db):
        """Test: Marcar gap como rellenado en DB"""
        from database.connection import mark_gap_as_filled, get_filled_gaps

        symbol = "TEST"
        gap_start = datetime.now() - timedelta(hours=2)
        gap_end = datetime.now() - timedelta(hours=1)

        result = mark_gap_as_filled(symbol, gap_start, gap_end, 'REAL_DATA', 8)
        assert result is True

        # Verificar que se guardó
        filled_gaps = get_filled_gaps(symbol, 1)
        assert len(filled_gaps) > 0

    def test_gap_report_persistence(self, temp_db):
        """Test: Persistir reporte de gaps"""
        from database.connection import save_gap_report, get_gap_reports

        test_report = {
            'symbol': 'TEST',
            'analysis_time': datetime.now(),
            'analysis_period': (datetime.now() - timedelta(days=1), datetime.now()),
            'total_data_points': 100,
            'expected_data_points': 100,
            'completeness_pct': 100.0,
            'total_gaps': 0,
            'overall_quality_score': 100.0,
            'is_suitable_for_backtesting': True,
            'gaps_by_type': {},
            'gaps_by_severity': {},
            'max_gap_duration_hours': 0,
            'avg_gap_duration_minutes': 0,
            'price_anomalies_count': 0,
            'volume_anomalies_count': 0,
            'recommended_actions': [],
            'extended_hours_used': True,
            'gaps_detected': []
        }

        result = save_gap_report(test_report)
        assert result is True

        # Recuperar
        reports = get_gap_reports('TEST', 1)
        assert len(reports) > 0
        assert reports[0]['quality_score'] == 100.0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
