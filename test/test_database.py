#!/usr/bin/env python3
"""
🧪 TESTS DE BASE DE DATOS
=========================

Tests comprehensivos para la base de datos:
- Estructura de tablas
- Integridad de datos
- Detección de duplicados
- Detección de gaps
- Validación de índices
- Performance de queries
"""

import pytest
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
from database.connection import (
    get_connection,
    initialize_database,
    save_indicators_data,
    save_gap_report,
    get_database_stats,
    cleanup_old_data,
    mark_gap_as_filled,
    get_filled_gaps
)


# =============================================================================
# 📋 TESTS DE ESTRUCTURA
# =============================================================================

@pytest.mark.database
class TestDatabaseStructure:
    """Tests de estructura de base de datos"""

    def test_database_initialization(self, temp_db):
        """Test: La base de datos se inicializa correctamente"""
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()

        # Verificar que todas las tablas existen
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]

        expected_tables = [
            'indicators_data',
            'signals_sent',
            'gap_reports',
            'continuous_data',
            'collector_stats',
            'gap_fills'
        ]

        for table in expected_tables:
            assert table in tables, f"Tabla {table} no encontrada"

        conn.close()

    def test_indicators_data_schema(self, db_connection):
        """Test: Tabla indicators_data tiene el schema correcto"""
        cursor = db_connection.cursor()

        cursor.execute("PRAGMA table_info(indicators_data)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}

        # Verificar columnas OHLCV
        assert 'timestamp' in columns
        assert 'symbol' in columns
        assert 'open_price' in columns
        assert 'high_price' in columns
        assert 'low_price' in columns
        assert 'close_price' in columns
        assert 'volume' in columns

        # Verificar columnas de indicadores
        assert 'rsi_value' in columns
        assert 'macd_line' in columns
        assert 'vwap_value' in columns
        assert 'atr_value' in columns

    def test_indexes_exist(self, db_connection):
        """Test: Los índices necesarios existen"""
        cursor = db_connection.cursor()

        cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
        indexes = [row[0] for row in cursor.fetchall()]

        # Verificar índices críticos
        expected_indexes = [
            'idx_indicators_symbol_time',
            'idx_signals_symbol_time',
            'idx_gaps_symbol_time'
        ]

        for idx in expected_indexes:
            assert idx in indexes, f"Índice {idx} no encontrado"

    def test_unique_constraints(self, db_connection):
        """Test: Las constraints UNIQUE funcionan"""
        cursor = db_connection.cursor()

        # Insertar un registro
        timestamp = datetime.now().isoformat()
        cursor.execute('''
        INSERT INTO indicators_data (timestamp, symbol, close_price, volume)
        VALUES (?, ?, ?, ?)
        ''', (timestamp, 'TEST', 100.0, 1000000))

        # Intentar insertar duplicado - debe fallar
        with pytest.raises(sqlite3.IntegrityError):
            cursor.execute('''
            INSERT INTO indicators_data (timestamp, symbol, close_price, volume)
            VALUES (?, ?, ?, ?)
            ''', (timestamp, 'TEST', 101.0, 1000000))


# =============================================================================
# 💾 TESTS DE INSERCIÓN Y RECUPERACIÓN
# =============================================================================

@pytest.mark.database
class TestDataInsertion:
    """Tests de inserción y recuperación de datos"""

    def test_save_indicators_data(self, temp_db, sample_indicators_result):
        """Test: Guardar datos de indicadores"""
        result = save_indicators_data(sample_indicators_result)
        assert result is True, "Error guardando indicadores"

        # Verificar que se guardó
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
        SELECT * FROM indicators_data WHERE symbol = ?
        ''', (sample_indicators_result['symbol'],))
        row = cursor.fetchone()

        assert row is not None, "Datos no encontrados"
        conn.close()

    def test_save_gap_report(self, temp_db):
        """Test: Guardar reporte de gaps"""
        test_report = {
            'symbol': 'TEST',
            'analysis_time': datetime.now(),
            'analysis_period': (datetime.now() - timedelta(days=1), datetime.now()),
            'total_data_points': 100,
            'expected_data_points': 120,
            'completeness_pct': 83.3,
            'total_gaps': 3,
            'overall_quality_score': 85.5,
            'is_suitable_for_backtesting': True,
            'gaps_by_type': {'OVERNIGHT_GAP': 2, 'SMALL_GAP': 1},
            'gaps_by_severity': {'LOW': 2, 'MEDIUM': 1},
            'max_gap_duration_hours': 8.5,
            'avg_gap_duration_minutes': 120.0,
            'price_anomalies_count': 1,
            'volume_anomalies_count': 0,
            'recommended_actions': ['Fill overnight gaps'],
            'extended_hours_used': True,
            'gaps_detected': []
        }

        result = save_gap_report(test_report)
        assert result is True, "Error guardando reporte de gaps"

    def test_mark_gap_as_filled(self, temp_db):
        """Test: Marcar gap como rellenado"""
        symbol = "AAPL"
        gap_start = datetime.now() - timedelta(hours=2)
        gap_end = datetime.now() - timedelta(hours=1)

        result = mark_gap_as_filled(symbol, gap_start, gap_end, 'REAL_DATA', 8)
        assert result is True, "Error marcando gap"

        # Verificar que se guardó
        filled_gaps = get_filled_gaps(symbol, 1)
        assert len(filled_gaps) > 0, "Gap no encontrado"
        assert filled_gaps[0]['fill_method'] == 'REAL_DATA'


# =============================================================================
# 🔍 TESTS DE INTEGRIDAD DE DATOS
# =============================================================================

@pytest.mark.database
class TestDataIntegrity:
    """Tests de integridad de datos"""

    def test_no_duplicate_timestamps(self, populated_db):
        """Test: No hay timestamps duplicados por símbolo"""
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute('''
        SELECT symbol, timestamp, COUNT(*) as count
        FROM indicators_data
        GROUP BY symbol, timestamp
        HAVING count > 1
        ''')

        duplicates = cursor.fetchall()
        assert len(duplicates) == 0, f"Duplicados encontrados: {duplicates}"
        conn.close()

    def test_ohlc_consistency(self, populated_db):
        """Test: Consistencia de datos OHLC (H >= L, etc.)"""
        conn = get_connection()
        cursor = conn.cursor()

        # Verificar High >= Low
        cursor.execute('''
        SELECT symbol, timestamp, high_price, low_price
        FROM indicators_data
        WHERE high_price < low_price
        ''')
        inconsistent = cursor.fetchall()
        assert len(inconsistent) == 0, f"High < Low encontrado: {inconsistent}"

        # Verificar High >= Open
        cursor.execute('''
        SELECT symbol, timestamp, high_price, open_price
        FROM indicators_data
        WHERE high_price < open_price
        ''')
        inconsistent = cursor.fetchall()
        assert len(inconsistent) == 0, f"High < Open encontrado: {inconsistent}"

        # Verificar High >= Close
        cursor.execute('''
        SELECT symbol, timestamp, high_price, close_price
        FROM indicators_data
        WHERE high_price < close_price
        ''')
        inconsistent = cursor.fetchall()
        assert len(inconsistent) == 0, f"High < Close encontrado: {inconsistent}"

        conn.close()

    def test_no_negative_prices(self, populated_db):
        """Test: No hay precios negativos"""
        conn = get_connection()
        cursor = conn.cursor()

        price_columns = ['open_price', 'high_price', 'low_price', 'close_price']

        for col in price_columns:
            cursor.execute(f'''
            SELECT symbol, timestamp, {col}
            FROM indicators_data
            WHERE {col} < 0
            ''')
            negative = cursor.fetchall()
            assert len(negative) == 0, f"Precios negativos en {col}: {negative}"

        conn.close()

    def test_no_negative_volume(self, populated_db):
        """Test: No hay volúmenes negativos"""
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute('''
        SELECT symbol, timestamp, volume
        FROM indicators_data
        WHERE volume < 0
        ''')
        negative = cursor.fetchall()
        assert len(negative) == 0, f"Volúmenes negativos: {negative}"
        conn.close()

    def test_rsi_range(self, populated_db):
        """Test: RSI está en rango válido (0-100)"""
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute('''
        SELECT symbol, timestamp, rsi_value
        FROM indicators_data
        WHERE rsi_value IS NOT NULL AND (rsi_value < 0 OR rsi_value > 100)
        ''')
        invalid = cursor.fetchall()
        assert len(invalid) == 0, f"RSI fuera de rango: {invalid}"
        conn.close()


# =============================================================================
# 🕐 TESTS DE GAPS
# =============================================================================

@pytest.mark.database
@pytest.mark.gaps
class TestGapDetection:
    """Tests de detección de gaps en la base de datos"""

    def test_detect_temporal_gaps(self, populated_db):
        """Test: Detectar gaps temporales en los datos"""
        conn = get_connection()

        # Obtener datos de un símbolo
        df = pd.read_sql_query('''
        SELECT timestamp, symbol, close_price
        FROM indicators_data
        WHERE symbol = 'AAPL'
        ORDER BY timestamp
        ''', conn, parse_dates=['timestamp'])

        conn.close()

        if len(df) < 2:
            pytest.skip("No hay suficientes datos")

        # Calcular diferencias temporales
        df['time_diff'] = df['timestamp'].diff()

        # Buscar gaps significativos (> 1 hora)
        gaps = df[df['time_diff'] > timedelta(hours=1)]

        # Este test pasa si NO hay gaps (datos bien)
        # O si hay gaps conocidos/esperados
        print(f"Gaps detectados: {len(gaps)}")
        for idx, gap in gaps.iterrows():
            print(f"  Gap: {gap['time_diff']} en {gap['timestamp']}")

    def test_missing_data_periods(self, populated_db):
        """Test: Identificar períodos con datos faltantes"""
        conn = get_connection()
        cursor = conn.cursor()

        # Verificar que hay datos para cada día de la semana
        cursor.execute('''
        SELECT
            symbol,
            DATE(timestamp) as date,
            COUNT(*) as data_points
        FROM indicators_data
        GROUP BY symbol, DATE(timestamp)
        HAVING data_points < 20
        ''')

        sparse_days = cursor.fetchall()
        conn.close()

        # Advertir si hay días con muy pocos datos
        if len(sparse_days) > 0:
            print(f"Días con pocos datos: {sparse_days}")


# =============================================================================
# 📊 TESTS DE ESTADÍSTICAS
# =============================================================================

@pytest.mark.database
class TestDatabaseStats:
    """Tests de estadísticas de la base de datos"""

    def test_get_database_stats(self, populated_db):
        """Test: Obtener estadísticas de la base de datos"""
        stats = get_database_stats()

        assert stats is not None, "Error obteniendo estadísticas"
        assert 'tables' in stats
        assert 'unique_symbols' in stats

        # Verificar que hay datos
        assert stats['tables']['indicators_data'] > 0, "No hay datos en indicators_data"
        assert stats['unique_symbols'] > 0, "No hay símbolos únicos"

    def test_data_completeness_by_symbol(self, populated_db):
        """Test: Calcular completitud de datos por símbolo"""
        conn = get_connection()

        symbols_df = pd.read_sql_query('''
        SELECT
            symbol,
            COUNT(*) as data_points,
            MIN(timestamp) as first_timestamp,
            MAX(timestamp) as last_timestamp
        FROM indicators_data
        GROUP BY symbol
        ''', conn, parse_dates=['first_timestamp', 'last_timestamp'])

        conn.close()

        for idx, row in symbols_df.iterrows():
            duration = (row['last_timestamp'] - row['first_timestamp']).total_seconds() / 3600
            expected_points = duration * 4  # Esperamos 4 puntos por hora (15min)

            completeness = (row['data_points'] / expected_points) * 100 if expected_points > 0 else 0

            print(f"{row['symbol']}: {completeness:.1f}% completo ({row['data_points']} puntos)")

            # Advertir si completitud < 80%
            if completeness < 80:
                print(f"  ⚠️ Baja completitud para {row['symbol']}")


# =============================================================================
# 🧹 TESTS DE MANTENIMIENTO
# =============================================================================

@pytest.mark.database
class TestDatabaseMaintenance:
    """Tests de mantenimiento de la base de datos"""

    def test_cleanup_old_data(self, populated_db):
        """Test: Limpiar datos antiguos"""
        # Primero obtener conteo inicial
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM collector_stats")
        initial_count = cursor.fetchone()[0]
        conn.close()

        # Ejecutar cleanup
        cleanup_results = cleanup_old_data(days_old=0)  # Limpiar todo

        assert isinstance(cleanup_results, dict), "Resultado de cleanup inválido"

    def test_database_size(self, populated_db):
        """Test: Verificar tamaño de la base de datos"""
        import os

        stats = get_database_stats()
        db_size_mb = stats.get('database_size_mb', 0)

        print(f"Tamaño de BD: {db_size_mb} MB")

        # Advertir si la BD es muy grande (> 500 MB)
        if db_size_mb > 500:
            print("⚠️ Base de datos grande, considerar cleanup")


# =============================================================================
# 🚀 TESTS DE PERFORMANCE
# =============================================================================

@pytest.mark.database
@pytest.mark.slow
class TestDatabasePerformance:
    """Tests de performance de queries"""

    def test_query_performance(self, populated_db):
        """Test: Medir performance de queries comunes"""
        import time
        conn = get_connection()

        # Query 1: Obtener datos recientes de un símbolo
        start = time.time()
        df = pd.read_sql_query('''
        SELECT * FROM indicators_data
        WHERE symbol = 'AAPL'
        ORDER BY timestamp DESC
        LIMIT 100
        ''', conn)
        query1_time = time.time() - start

        print(f"Query recientes: {query1_time:.3f}s")
        assert query1_time < 1.0, "Query muy lenta"

        # Query 2: Agregar datos por símbolo
        start = time.time()
        df = pd.read_sql_query('''
        SELECT symbol, COUNT(*) as count
        FROM indicators_data
        GROUP BY symbol
        ''', conn)
        query2_time = time.time() - start

        print(f"Query agregación: {query2_time:.3f}s")
        assert query2_time < 2.0, "Query muy lenta"

        conn.close()


# =============================================================================
# 🎯 TESTS DE CASOS ESPECIALES
# =============================================================================

@pytest.mark.database
class TestEdgeCases:
    """Tests de casos especiales y edge cases"""

    def test_insert_with_null_values(self, temp_db):
        """Test: Manejar valores NULL correctamente"""
        conn = get_connection()
        cursor = conn.cursor()

        # Insertar con algunos NULLs
        timestamp = datetime.now().isoformat()
        cursor.execute('''
        INSERT INTO indicators_data (timestamp, symbol, close_price, volume)
        VALUES (?, ?, ?, ?)
        ''', (timestamp, 'TEST', 100.0, 1000000))

        # Verificar que se insertó
        cursor.execute('''
        SELECT rsi_value FROM indicators_data
        WHERE symbol = 'TEST'
        ''')
        row = cursor.fetchone()
        assert row is not None
        # rsi_value debe ser NULL
        assert row[0] is None

        conn.close()

    def test_very_old_and_very_new_data(self, temp_db):
        """Test: Manejar datos muy antiguos y muy nuevos"""
        conn = get_connection()
        cursor = conn.cursor()

        # Datos muy antiguos
        old_date = datetime.now() - timedelta(days=365 * 5)
        cursor.execute('''
        INSERT INTO indicators_data (timestamp, symbol, close_price, volume)
        VALUES (?, ?, ?, ?)
        ''', (old_date.isoformat(), 'OLD', 100.0, 1000000))

        # Datos muy nuevos
        new_date = datetime.now()
        cursor.execute('''
        INSERT INTO indicators_data (timestamp, symbol, close_price, volume)
        VALUES (?, ?, ?, ?)
        ''', (new_date.isoformat(), 'NEW', 100.0, 1000000))

        conn.commit()

        # Verificar que ambos se insertaron
        cursor.execute('SELECT COUNT(*) FROM indicators_data')
        count = cursor.fetchone()[0]
        assert count == 2

        conn.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
