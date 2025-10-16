#!/usr/bin/env python3
"""
🔗 DATABASE CONNECTION V3.1 - EXTENDED HOURS + GAP TRACKING
==========================================================

FUNCIONALIDADES V3.1:
- Tabla gap_reports para tracking de gaps
- Tabla continuous_data para datos 24/5  
- Soporte completo OHLC en indicators_data
- Funciones de mantenimiento y cleanup
- Estadísticas avanzadas de gaps
"""

import sqlite3
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
import json
import os
from pathlib import Path

# Configurar logging
logger = logging.getLogger(__name__)

# Ruta del archivo de base de datos
DB_PATH = os.path.join(os.path.dirname(__file__), 'trading_data.db')

def get_connection():
    """
    Obtener conexión a la base de datos SQLite
    """
    try:
        conn = sqlite3.connect(DB_PATH, timeout=30.0)
        conn.row_factory = sqlite3.Row  # Para acceder por nombre de columna
        return conn
    except Exception as e:
        logger.error(f"❌ Error conectando a DB: {e}")
        return None

def initialize_database():
    """
    Inicializar base de datos con todas las tablas V3.1
    """
    try:
        conn = get_connection()
        if not conn:
            return False
        
        cursor = conn.cursor()
        
        # Tabla principal de indicadores (ya existente, verificar estructura)
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS indicators_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            symbol TEXT NOT NULL,
            open_price REAL DEFAULT 0,
            high_price REAL DEFAULT 0,
            low_price REAL DEFAULT 0,
            close_price REAL DEFAULT 0,
            volume INTEGER DEFAULT 0,
            rsi_value REAL,
            macd_line REAL,
            macd_signal REAL,
            macd_histogram REAL,
            vwap_value REAL,
            vwap_deviation_pct REAL,
            roc_value REAL,
            bb_upper REAL,
            bb_middle REAL,
            bb_lower REAL,
            bb_position REAL,
            volume_oscillator REAL,
            atr_value REAL,
            atr_percentage REAL,
            market_regime TEXT,
            volatility_level TEXT,
            UNIQUE(timestamp, symbol)
        )
        ''')
        
        # Tabla de señales (ya existente)
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS signals_sent (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            symbol TEXT NOT NULL,
            signal_type TEXT NOT NULL,
            signal_strength REAL NOT NULL,
            confidence_level TEXT,
            entry_quality TEXT,
            current_price REAL,
            market_context TEXT,
            macd_score REAL DEFAULT 0,
            rsi_score REAL DEFAULT 0,
            vwap_score REAL DEFAULT 0,
            roc_score REAL DEFAULT 0,
            bollinger_score REAL DEFAULT 0,
            volume_score REAL DEFAULT 0,
            strategy_type TEXT,
            max_risk_reward REAL,
            expected_hold_time TEXT,
            telegram_sent INTEGER DEFAULT 1
        )
        ''')
        
        # 🆕 NUEVA: Tabla para reportes de gaps
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS gap_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            analysis_time TIMESTAMP NOT NULL,
            analysis_period_start TIMESTAMP,
            analysis_period_end TIMESTAMP,
            total_data_points INTEGER,
            expected_data_points INTEGER,
            completeness_pct REAL,
            total_gaps INTEGER,
            quality_score REAL,
            is_suitable_for_backtesting BOOLEAN,
            gaps_by_type TEXT,  -- JSON string
            gaps_by_severity TEXT,  -- JSON string
            max_gap_duration_hours REAL,
            avg_gap_duration_minutes REAL,
            price_anomalies_count INTEGER,
            volume_anomalies_count INTEGER,
            recommended_actions TEXT,  -- JSON string
            extended_hours_used BOOLEAN DEFAULT FALSE,
            gaps_filled_count INTEGER DEFAULT 0
        )
        ''')
        
        # 🆕 NUEVA: Tabla para datos continuos 24/5
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS continuous_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP NOT NULL,
            symbol TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            open_price REAL NOT NULL,
            high_price REAL NOT NULL,
            low_price REAL NOT NULL,
            close_price REAL NOT NULL,
            volume INTEGER DEFAULT 0,
            session_type TEXT,  -- PRE_MARKET, REGULAR, POST_MARKET, OVERNIGHT
            is_extended_hours BOOLEAN DEFAULT FALSE,
            is_gap_filled BOOLEAN DEFAULT FALSE,
            data_source TEXT DEFAULT 'API',  -- API, INTERPOLATED, FORWARD_FILL
            collection_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(timestamp, symbol, timeframe)
        )
        ''')
        
        # 🆕 NUEVA: Tabla para estadísticas del collector
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS collector_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            session_type TEXT,
            symbol TEXT,
            collection_success BOOLEAN,
            data_points_collected INTEGER,
            gaps_detected INTEGER,
            gaps_filled INTEGER,
            collection_time_ms REAL,
            error_message TEXT
        )
        ''')
        
        # Crear índices para mejor performance
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_indicators_symbol_time ON indicators_data(symbol, timestamp)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_signals_symbol_time ON signals_sent(symbol, timestamp)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_gaps_symbol_time ON gap_reports(symbol, analysis_time)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_continuous_symbol_time ON continuous_data(symbol, timestamp)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_collector_time ON collector_stats(timestamp)')
        
        conn.commit()
        conn.close()
        
        logger.info("✅ Base de datos V3.1 inicializada correctamente")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error inicializando base de datos: {e}")
        if conn:
            conn.close()
        return False

def save_indicators_data(indicators: Dict[str, Any]) -> bool:
    """
    Guardar datos de indicadores en la base de datos
    
    Args:
        indicators: Dict con todos los indicadores calculados (desde indicators.py)
        
    Returns:
        True si se guardó exitosamente, False si hubo error
    """
    try:
        conn = get_connection()
        if not conn:
            return False
        
        cursor = conn.cursor()
        
        # Extraer datos básicos
        symbol = indicators.get('symbol', 'UNKNOWN')
        timestamp = indicators.get('timestamp', datetime.now()).isoformat()
        
        # Extraer TODOS los precios OHLC
        current_price = indicators.get('current_price', 0)
        open_price = indicators.get('open_price', current_price)
        high_price = indicators.get('high_price', current_price)
        low_price = indicators.get('low_price', current_price)
        close_price = current_price
        current_volume = indicators.get('current_volume', 0)
        
        # Extraer datos de indicadores
        macd_data = indicators.get('macd', {})
        rsi_data = indicators.get('rsi', {})
        vwap_data = indicators.get('vwap', {})
        roc_data = indicators.get('roc', {})
        bb_data = indicators.get('bollinger', {})
        vol_data = indicators.get('volume_osc', {})
        atr_data = indicators.get('atr', {})
        
        # Determinar market regime simple
        roc_value = roc_data.get('roc', 0)
        if abs(roc_value) > 2.0:
            market_regime = "TRENDING"
        elif abs(roc_value) < 0.5:
            market_regime = "RANGING"
        else:
            market_regime = "TRANSITIONING"
        
        cursor.execute('''
        INSERT OR REPLACE INTO indicators_data (
            timestamp, symbol, open_price, high_price, low_price, close_price, volume,
            rsi_value, macd_line, macd_signal, macd_histogram,
            vwap_value, vwap_deviation_pct, roc_value,
            bb_upper, bb_middle, bb_lower, bb_position,
            volume_oscillator, atr_value, atr_percentage,
            market_regime, volatility_level
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            timestamp, symbol, open_price, high_price, low_price, close_price, current_volume,
            rsi_data.get('rsi', 0),
            macd_data.get('macd', 0),
            macd_data.get('signal', 0),
            macd_data.get('histogram', 0),
            vwap_data.get('vwap', 0),
            vwap_data.get('deviation_pct', 0),
            roc_value,
            bb_data.get('upper_band', 0),
            bb_data.get('middle_band', 0),
            bb_data.get('lower_band', 0),
            bb_data.get('bb_position', 0.5),
            vol_data.get('volume_oscillator', 0),
            atr_data.get('atr', 0),
            atr_data.get('atr_percentage', 0),
            market_regime,
            atr_data.get('volatility_level', 'NORMAL')
        ))
        
        conn.commit()
        conn.close()
        
        logger.debug(f"📊 Indicadores guardados: {symbol} - {timestamp}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error guardando indicadores: {e}")
        if conn:
            conn.close()
        return False

def save_signal_data(signal) -> bool:
    """
    Guardar señal de trading en la base de datos
    
    Args:
        signal: TradingSignal object (desde scanner.py)
        
    Returns:
        True si se guardó exitosamente, False si hubo error
    """
    try:
        conn = get_connection()
        if not conn:
            return False
        
        cursor = conn.cursor()
        
        # Extraer datos básicos del signal
        timestamp = signal.timestamp.isoformat() if signal.timestamp else datetime.now().isoformat()
        
        # Extraer scores de indicadores
        indicator_scores = getattr(signal, 'indicator_scores', {})
        
        # Extraer datos del plan de posición si existe
        strategy_type = ""
        max_risk_reward = 0.0
        expected_hold_time = ""
        
        if hasattr(signal, 'position_plan') and signal.position_plan:
            strategy_type = getattr(signal.position_plan, 'strategy_type', '')
            max_risk_reward = getattr(signal.position_plan, 'max_risk_reward', 0.0)
            expected_hold_time = getattr(signal.position_plan, 'expected_hold_time', '')
        
        # Insertar en base de datos
        cursor.execute('''
        INSERT INTO signals_sent (
            timestamp, symbol, signal_type, signal_strength,
            confidence_level, entry_quality, current_price, market_context,
            macd_score, rsi_score, vwap_score, roc_score, bollinger_score, volume_score,
            strategy_type, max_risk_reward, expected_hold_time, telegram_sent
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            timestamp,
            signal.symbol,
            signal.signal_type,
            signal.signal_strength,
            signal.confidence_level,
            signal.entry_quality,
            signal.current_price,
            getattr(signal, 'market_context', ''),
            indicator_scores.get('MACD', 0),
            indicator_scores.get('RSI', 0),
            indicator_scores.get('VWAP', 0),
            indicator_scores.get('ROC', 0),
            indicator_scores.get('BOLLINGER', 0),
            indicator_scores.get('VOLUME', 0),
            strategy_type,
            max_risk_reward,
            expected_hold_time,
            1  # telegram_sent = True
        ))
        
        conn.commit()
        conn.close()
        
        logger.info(f"📤 Señal guardada: {signal.symbol} {signal.signal_type} ({signal.signal_strength} pts)")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error guardando señal: {e}")
        if conn:
            conn.close()
        return False

def save_gap_report(report_data: Dict[str, Any]) -> bool:
    """
    Guardar reporte de gaps en la base de datos
    
    Args:
        report_data: Diccionario con datos del reporte (desde gap_detector.py)
        
    Returns:
        True si se guardó exitosamente
    """
    try:
        conn = get_connection()
        if not conn:
            return False
        
        cursor = conn.cursor()
        
        # Extraer datos del reporte
        symbol = report_data.get('symbol', 'UNKNOWN')
        analysis_time = report_data.get('analysis_time', datetime.now())
        
        # Convertir analysis_period tuple a timestamps
        analysis_period = report_data.get('analysis_period', (datetime.now(), datetime.now()))
        period_start = analysis_period[0] if len(analysis_period) > 0 else datetime.now()
        period_end = analysis_period[1] if len(analysis_period) > 1 else datetime.now()
        
        # Convertir diccionarios a JSON strings
        gaps_by_type_json = json.dumps(report_data.get('gaps_by_type', {}))
        gaps_by_severity_json = json.dumps(report_data.get('gaps_by_severity', {}))
        recommendations_json = json.dumps(report_data.get('recommended_actions', []))
        
        cursor.execute('''
        INSERT INTO gap_reports (
            symbol, analysis_time, analysis_period_start, analysis_period_end,
            total_data_points, expected_data_points, completeness_pct,
            total_gaps, quality_score, is_suitable_for_backtesting,
            gaps_by_type, gaps_by_severity, max_gap_duration_hours,
            avg_gap_duration_minutes, price_anomalies_count, volume_anomalies_count,
            recommended_actions, extended_hours_used, gaps_filled_count
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            symbol,
            analysis_time.isoformat() if hasattr(analysis_time, 'isoformat') else str(analysis_time),
            period_start.isoformat() if hasattr(period_start, 'isoformat') else str(period_start),
            period_end.isoformat() if hasattr(period_end, 'isoformat') else str(period_end),
            report_data.get('total_data_points', 0),
            report_data.get('expected_data_points', 0),
            report_data.get('completeness_pct', 0),
            report_data.get('total_gaps', 0),
            report_data.get('overall_quality_score', 0),
            report_data.get('is_suitable_for_backtesting', False),
            gaps_by_type_json,
            gaps_by_severity_json,
            report_data.get('max_gap_duration_hours', 0),
            report_data.get('avg_gap_duration_minutes', 0),
            report_data.get('price_anomalies_count', 0),
            report_data.get('volume_anomalies_count', 0),
            recommendations_json,
            report_data.get('extended_hours_used', False),
            len([g for g in report_data.get('gaps_detected', []) if getattr(g, 'is_fillable', False)])
        ))
        
        conn.commit()
        conn.close()
        
        logger.info(f"📊 Reporte de gaps guardado: {symbol} - Score: {report_data.get('overall_quality_score', 0):.1f}/100")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error guardando reporte de gaps: {e}")
        if conn:
            conn.close()
        return False

def save_continuous_data(symbol: str, timeframe: str, data_points: List[Dict], 
                        session_type: str = "REGULAR") -> bool:
    """
    Guardar datos continuos 24/5 en la base de datos
    
    Args:
        symbol: Símbolo del activo
        timeframe: Timeframe (15m, 1h, etc.)
        data_points: Lista de diccionarios con datos OHLCV
        session_type: Tipo de sesión (PRE_MARKET, REGULAR, POST_MARKET, OVERNIGHT)
        
    Returns:
        True si se guardó exitosamente
    """
    try:
        conn = get_connection()
        if not conn:
            return False
        
        cursor = conn.cursor()
        
        saved_count = 0
        for point in data_points:
            try:
                cursor.execute('''
                INSERT OR REPLACE INTO continuous_data (
                    timestamp, symbol, timeframe, open_price, high_price, 
                    low_price, close_price, volume, session_type, 
                    is_extended_hours, is_gap_filled, data_source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    point.get('timestamp'),
                    symbol,
                    timeframe,
                    point.get('open', 0),
                    point.get('high', 0),
                    point.get('low', 0),
                    point.get('close', 0),
                    point.get('volume', 0),
                    session_type,
                    session_type in ['PRE_MARKET', 'POST_MARKET', 'OVERNIGHT'],
                    point.get('is_gap_filled', False),
                    point.get('data_source', 'API')
                ))
                saved_count += 1
                
            except Exception as point_error:
                logger.warning(f"⚠️ Error guardando punto de {symbol}: {point_error}")
                continue
        
        conn.commit()
        conn.close()
        
        logger.info(f"📊 Datos continuos guardados: {symbol} - {saved_count}/{len(data_points)} puntos")
        return saved_count > 0
        
    except Exception as e:
        logger.error(f"❌ Error guardando datos continuos: {e}")
        if conn:
            conn.close()
        return False

def save_collector_stats(stats_data: Dict[str, Any]) -> bool:
    """
    Guardar estadísticas del continuous collector
    
    Args:
        stats_data: Diccionario con estadísticas de recolección
        
    Returns:
        True si se guardó exitosamente
    """
    try:
        conn = get_connection()
        if not conn:
            return False
        
        cursor = conn.cursor()
        
        cursor.execute('''
        INSERT INTO collector_stats (
            session_type, symbol, collection_success, data_points_collected,
            gaps_detected, gaps_filled, collection_time_ms, error_message
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            stats_data.get('session_type', 'UNKNOWN'),
            stats_data.get('symbol', 'UNKNOWN'),
            stats_data.get('success', False),
            stats_data.get('data_points', 0),
            stats_data.get('gaps_detected', 0),
            stats_data.get('gaps_filled', 0),
            stats_data.get('collection_time_ms', 0),
            stats_data.get('error_message', None)
        ))
        
        conn.commit()
        conn.close()
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Error guardando stats del collector: {e}")
        if conn:
            conn.close()
        return False

def get_recent_signals(days: int = 7, symbol: str = None) -> List[Dict]:
    """
    Obtener señales recientes de la base de datos
    
    Args:
        days: Número de días hacia atrás
        symbol: Símbolo específico (opcional)
        
    Returns:
        Lista de diccionarios con las señales
    """
    try:
        conn = get_connection()
        if not conn:
            return []
        
        cursor = conn.cursor()
        
        # Construir query
        query = '''
        SELECT * FROM signals_sent 
        WHERE datetime(timestamp) >= datetime('now', '-{} days')
        '''.format(days)
        
        params = []
        if symbol:
            query += ' AND symbol = ?'
            params.append(symbol)
        
        query += ' ORDER BY timestamp DESC'
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        # Convertir a lista de diccionarios
        signals = []
        for row in rows:
            signals.append(dict(row))
        
        conn.close()
        
        logger.debug(f"📊 Recuperadas {len(signals)} señales de últimos {days} días")
        return signals
        
    except Exception as e:
        logger.error(f"❌ Error obteniendo señales: {e}")
        return []

def get_gap_reports(symbol: str = None, days_back: int = 30) -> List[Dict]:
    """
    Obtener reportes de gaps de la base de datos
    
    Args:
        symbol: Símbolo específico (opcional)
        days_back: Días hacia atrás para buscar
        
    Returns:
        Lista de reportes de gaps
    """
    try:
        conn = get_connection()
        if not conn:
            return []
        
        cursor = conn.cursor()
        
        query = '''
        SELECT * FROM gap_reports 
        WHERE datetime(analysis_time) >= datetime('now', '-{} days')
        '''.format(days_back)
        
        params = []
        if symbol:
            query += ' AND symbol = ?'
            params.append(symbol)
        
        query += ' ORDER BY analysis_time DESC'
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        reports = []
        for row in rows:
            report = dict(row)
            # Parsear JSON fields
            try:
                report['gaps_by_type'] = json.loads(report['gaps_by_type'])
                report['gaps_by_severity'] = json.loads(report['gaps_by_severity'])
                report['recommended_actions'] = json.loads(report['recommended_actions'])
            except (json.JSONDecodeError, TypeError):
                pass
            
            reports.append(report)
        
        conn.close()
        
        logger.debug(f"📊 Recuperados {len(reports)} reportes de gaps")
        return reports
        
    except Exception as e:
        logger.error(f"❌ Error obteniendo reportes de gaps: {e}")
        return []

def get_database_stats() -> Dict[str, Any]:
    """
    Obtener estadísticas completas de la base de datos V3.1
    
    Returns:
        Diccionario con estadísticas
    """
    try:
        conn = get_connection()
        if not conn:
            return {}
        
        cursor = conn.cursor()
        
        # Estadísticas básicas
        cursor.execute("SELECT COUNT(*) FROM indicators_data")
        indicators_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM signals_sent")
        signals_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM gap_reports")
        gap_reports_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM continuous_data")
        continuous_data_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM collector_stats")
        collector_stats_count = cursor.fetchone()[0]
        
        # Símbolos únicos
        cursor.execute("SELECT COUNT(DISTINCT symbol) FROM indicators_data")
        unique_symbols = cursor.fetchone()[0]
        
        # Estadísticas de gaps
        cursor.execute('''
        SELECT 
            AVG(quality_score) as avg_quality,
            COUNT(CASE WHEN is_suitable_for_backtesting = 1 THEN 1 END) as backtest_ready,
            SUM(total_gaps) as total_gaps_detected,
            SUM(gaps_filled_count) as total_gaps_filled
        FROM gap_reports
        WHERE datetime(analysis_time) >= datetime('now', '-30 days')
        ''')
        gap_stats = cursor.fetchone()
        
        # Estadísticas del collector
        cursor.execute('''
        SELECT 
            COUNT(CASE WHEN collection_success = 1 THEN 1 END) as successful_collections,
            COUNT(*) as total_collections,
            SUM(gaps_detected) as collector_gaps_detected,
            SUM(gaps_filled) as collector_gaps_filled,
            AVG(collection_time_ms) as avg_collection_time
        FROM collector_stats
        WHERE datetime(timestamp) >= datetime('now', '-7 days')
        ''')
        collector_stats = cursor.fetchone()
        
        # Rango de fechas
        cursor.execute("SELECT MIN(timestamp), MAX(timestamp) FROM signals_sent")
        date_range = cursor.fetchone()
        
        # Últimas señales por tipo (7 días)
        cursor.execute('''
        SELECT signal_type, COUNT(*) 
        FROM signals_sent 
        WHERE datetime(timestamp) >= datetime('now', '-7 days')
        GROUP BY signal_type
        ''')
        recent_signals = dict(cursor.fetchall())
        
        # Calidad promedio por símbolo
        cursor.execute('''
        SELECT symbol, AVG(quality_score) as avg_quality, COUNT(*) as reports_count
        FROM gap_reports
        WHERE datetime(analysis_time) >= datetime('now', '-30 days')
        GROUP BY symbol
        ORDER BY avg_quality DESC
        ''')
        quality_by_symbol = {row[0]: {'avg_quality': row[1], 'reports': row[2]} 
                           for row in cursor.fetchall()}
        
        conn.close()
        
        # Calcular success rate del collector
        collector_success_rate = 0
        if collector_stats and collector_stats[1] > 0:
            collector_success_rate = (collector_stats[0] / collector_stats[1]) * 100
        
        stats = {
            'tables': {
                'indicators_data': indicators_count,
                'signals_sent': signals_count,
                'gap_reports': gap_reports_count,
                'continuous_data': continuous_data_count,
                'collector_stats': collector_stats_count
            },
            'unique_symbols': unique_symbols,
            'date_range': {
                'first_signal': date_range[0] if date_range[0] else None,
                'last_signal': date_range[1] if date_range[1] else None
            },
            'recent_signals_by_type': recent_signals,
            'gap_analysis': {
                'avg_quality_score': float(gap_stats[0]) if gap_stats[0] else 0,
                'backtest_ready_symbols': gap_stats[1] if gap_stats[1] else 0,
                'total_gaps_detected': gap_stats[2] if gap_stats[2] else 0,
                'total_gaps_filled': gap_stats[3] if gap_stats[3] else 0
            },
            'collector_performance': {
                'success_rate_7d': collector_success_rate,
                'total_collections_7d': collector_stats[1] if collector_stats else 0,
                'gaps_detected_7d': collector_stats[2] if collector_stats else 0,
                'gaps_filled_7d': collector_stats[3] if collector_stats else 0,
                'avg_collection_time_ms': float(collector_stats[4]) if collector_stats and collector_stats[4] else 0
            },
            'quality_by_symbol': quality_by_symbol,
            'database_path': DB_PATH,
            'database_size_mb': round(os.path.getsize(DB_PATH) / (1024*1024), 2) if os.path.exists(DB_PATH) else 0
        }
        
        return stats
        
    except Exception as e:
        logger.error(f"❌ Error obteniendo estadísticas: {e}")
        return {}

def cleanup_old_data(days_old: int = 90) -> Dict[str, int]:
    """
    Limpiar datos antiguos de la base de datos
    
    Args:
        days_old: Días de antigüedad para considerar datos como "antiguos"
        
    Returns:
        Diccionario con conteo de registros eliminados por tabla
    """
    try:
        conn = get_connection()
        if not conn:
            return {}
        
        cursor = conn.cursor()
        cutoff_date = (datetime.now() - timedelta(days=days_old)).isoformat()
        
        cleanup_results = {}
        
        # Limpiar collector_stats (mantener solo 30 días)
        cursor.execute('''
        DELETE FROM collector_stats 
        WHERE datetime(timestamp) < datetime('now', '-30 days')
        ''')
        cleanup_results['collector_stats'] = cursor.rowcount
        
        # Limpiar gap_reports antiguos
        cursor.execute('''
        DELETE FROM gap_reports 
        WHERE datetime(analysis_time) < ?
        ''', (cutoff_date,))
        cleanup_results['gap_reports'] = cursor.rowcount
        
        # Limpiar continuous_data muy antiguos (mantener 60 días)
        cursor.execute('''
        DELETE FROM continuous_data 
        WHERE datetime(timestamp) < datetime('now', '-60 days')
        ''')
        cleanup_results['continuous_data'] = cursor.rowcount
        
        # No limpiar indicators_data ni signals_sent (son históricos importantes)
        
        conn.commit()
        conn.close()
        
        total_cleaned = sum(cleanup_results.values())
        logger.info(f"🧹 Limpieza completada: {total_cleaned} registros eliminados")
        
        return cleanup_results
        
    except Exception as e:
        logger.error(f"❌ Error en limpieza de datos: {e}")
        if conn:
            conn.close()
        return {}

def vacuum_database() -> bool:
    """
    Optimizar y compactar la base de datos (VACUUM)
    
    Returns:
        True si se ejecutó exitosamente
    """
    try:
        conn = get_connection()
        if not conn:
            return False
        
        # VACUUM requiere que no haya transacciones activas
        conn.execute('VACUUM')
        conn.close()
        
        logger.info("🔧 VACUUM ejecutado correctamente")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error ejecutando VACUUM: {e}")
        if conn:
            conn.close()
        return False

def export_data_to_json(output_dir: str = "exports", 
                       days_back: int = 30,
                       tables: List[str] = None) -> Dict[str, str]:
    """
    Exportar datos de la base de datos a archivos JSON
    
    Args:
        output_dir: Directorio de salida
        days_back: Días hacia atrás para exportar
        tables: Lista de tablas a exportar (None = todas)
        
    Returns:
        Diccionario con rutas de archivos exportados
    """
    try:
        # Crear directorio de salida
        export_path = Path(output_dir)
        export_path.mkdir(exist_ok=True)
        
        conn = get_connection()
        if not conn:
            return {}
        
        cursor = conn.cursor()
        
        # Tablas disponibles para exportar
        available_tables = ['indicators_data', 'signals_sent', 'gap_reports', 
                          'continuous_data', 'collector_stats']
        
        if tables is None:
            tables = available_tables
        
        exported_files = {}
        cutoff_date = (datetime.now() - timedelta(days=days_back)).isoformat()
        
        for table in tables:
            if table not in available_tables:
                logger.warning(f"⚠️ Tabla desconocida: {table}")
                continue
                
            try:
                # Query con filtro de fecha
                if table == 'gap_reports':
                    date_column = 'analysis_time'
                elif table == 'collector_stats':
                    date_column = 'timestamp'
                else:
                    date_column = 'timestamp'
                
                query = f'''
                SELECT * FROM {table} 
                WHERE datetime({date_column}) >= ?
                ORDER BY {date_column} DESC
                '''
                
                cursor.execute(query, (cutoff_date,))
                rows = cursor.fetchall()
                
                # Convertir a lista de diccionarios
                data = [dict(row) for row in rows]
                
                # Exportar a JSON
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f"{table}_{timestamp}.json"
                filepath = export_path / filename
                
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, default=str, ensure_ascii=False)
                
                exported_files[table] = str(filepath)
                logger.info(f"📤 Exportado {table}: {len(data)} registros -> {filename}")
                
            except Exception as table_error:
                logger.error(f"❌ Error exportando {table}: {table_error}")
                continue
        
        conn.close()
        
        logger.info(f"✅ Exportación completada: {len(exported_files)} tablas")
        return exported_files
        
    except Exception as e:
        logger.error(f"❌ Error en exportación: {e}")
        return {}

def test_database_connection():
    """
    Test completo de la conexión y funcionalidad de la base de datos V3.1
    """
    print("🧪 TESTING DATABASE CONNECTION V3.1")
    print("=" * 50)
    
    try:
        # Test 1: Inicialización
        print("1. 🔧 Inicializando base de datos...")
        if initialize_database():
            print("   ✅ Base de datos inicializada")
        else:
            print("   ❌ Error en inicialización")
            return False
        
        # Test 2: Conexión básica
        print("2. 🔗 Probando conexión...")
        conn = get_connection()
        if conn:
            print("   ✅ Conexión SQLite exitosa")
            
            # Verificar tablas
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]
            print(f"   📊 Tablas encontradas: {len(tables)}")
            for table in sorted(tables):
                print(f"      • {table}")
            
            conn.close()
        else:
            print("   ❌ Error en conexión")
            return False
        
        # Test 3: Estadísticas
        print("3. 📊 Obteniendo estadísticas...")
        stats = get_database_stats()
        
        print(f"   📈 Registros por tabla:")
        for table, count in stats.get('tables', {}).items():
            print(f"      • {table}: {count:,}")
        
        print(f"   🎯 Símbolos únicos: {stats.get('unique_symbols', 0)}")
        print(f"   💾 Tamaño DB: {stats.get('database_size_mb', 0)} MB")
        
        # Test 4: Gap analysis
        gap_analysis = stats.get('gap_analysis', {})
        if gap_analysis.get('total_gaps_detected', 0) > 0:
            print(f"   🔧 Gaps detectados: {gap_analysis['total_gaps_detected']}")
            print(f"   🔧 Gaps rellenados: {gap_analysis['total_gaps_filled']}")
            print(f"   📊 Score promedio: {gap_analysis['avg_quality_score']:.1f}/100")
        
        # Test 5: Collector performance
        collector_perf = stats.get('collector_performance', {})
        if collector_perf.get('total_collections_7d', 0) > 0:
            print(f"   🤖 Éxito collector (7d): {collector_perf['success_rate_7d']:.1f}%")
            print(f"   ⏱️ Tiempo promedio: {collector_perf['avg_collection_time_ms']:.0f}ms")
        
        print("✅ Database V3.1 funcionando correctamente")
        return True
        
    except Exception as e:
        print(f"❌ Error en test: {e}")
        return False

def test_gap_report_save():
    """
    Test específico para guardar reportes de gaps
    """
    print("\n🧪 TESTING GAP REPORT SAVE")
    print("=" * 40)
    
    try:
        # Crear datos de prueba
        test_report = {
            'symbol': 'TEST_SYMBOL',
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
            'recommended_actions': ['Fill overnight gaps', 'Validate data source'],
            'extended_hours_used': True,
            'gaps_detected': [
                type('Gap', (), {'is_fillable': True})(),
                type('Gap', (), {'is_fillable': True})(),
                type('Gap', (), {'is_fillable': False})()
            ]
        }
        
        print("📝 Guardando reporte de prueba...")
        if save_gap_report(test_report):
            print("   ✅ Reporte guardado exitosamente")
            
            # Verificar que se guardó
            reports = get_gap_reports('TEST_SYMBOL', 1)
            if reports:
                report = reports[0]
                print(f"   📊 Reporte recuperado: Score {report['quality_score']}/100")
                print(f"   🔧 Gaps: {report['total_gaps']} detectados")
                print(f"   ✅ Backtest ready: {report['is_suitable_for_backtesting']}")
                
                return True
            else:
                print("   ❌ No se pudo recuperar el reporte")
                return False
        else:
            print("   ❌ Error guardando reporte")
            return False
            
    except Exception as e:
        print(f"❌ Error en test de gap report: {e}")
        return False

def maintenance_database() -> Dict[str, Any]:
    """
    Ejecutar mantenimiento completo de la base de datos
    
    Returns:
        Diccionario con resultados del mantenimiento
    """
    try:
        logger.info("🔧 Iniciando mantenimiento de base de datos...")
        
        maintenance_results = {
            'timestamp': datetime.now().isoformat(),
            'cleanup_results': {},
            'vacuum_success': False,
            'stats_before': {},
            'stats_after': {},
            'success': True
        }
        
        # Estadísticas antes del mantenimiento
        maintenance_results['stats_before'] = get_database_stats()
        
        # Limpiar datos antiguos
        logger.info("🧹 Limpiando datos antiguos...")
        cleanup_results = cleanup_old_data(90)  # 90 días
        maintenance_results['cleanup_results'] = cleanup_results
        
        # VACUUM para optimizar
        logger.info("🔧 Optimizando base de datos...")
        vacuum_success = vacuum_database()
        maintenance_results['vacuum_success'] = vacuum_success
        
        # Estadísticas después del mantenimiento
        maintenance_results['stats_after'] = get_database_stats()
        
        # Calcular espacio liberado
        size_before = maintenance_results['stats_before'].get('database_size_mb', 0)
        size_after = maintenance_results['stats_after'].get('database_size_mb', 0)
        space_saved = size_before - size_after
        
        logger.info(f"✅ Mantenimiento completado:")
        logger.info(f"   Registros limpiados: {sum(cleanup_results.values())}")
        logger.info(f"   Espacio liberado: {space_saved:.2f} MB")
        logger.info(f"   VACUUM: {'✅' if vacuum_success else '❌'}")
        
        return maintenance_results
        
    except Exception as e:
        logger.error(f"❌ Error en mantenimiento: {e}")
        return {
            'timestamp': datetime.now().isoformat(),
            'success': False,
            'error': str(e)
        }

if __name__ == "__main__":
    """Ejecutar tests si se ejecuta directamente"""
    print("🔗 DATABASE CONNECTION V3.1 - TESTING")
    print("=" * 60)
    
    # Test completo de conexión
    connection_success = test_database_connection()
    
    if connection_success:
        # Test específico de gap reports
        gap_test_success = test_gap_report_save()
        
        if gap_test_success:
            print("\n🔧 ¿Ejecutar mantenimiento de prueba? (y/n)")
            try:
                response = input().lower().strip()
                if response == 'y':
                    maintenance_result = maintenance_database()
                    if maintenance_result['success']:
                        print("✅ Mantenimiento de prueba exitoso")
                    else:
                        print("❌ Error en mantenimiento de prueba")
            except (EOFError, KeyboardInterrupt):
                print("\n⏸️ Test interrumpido por usuario")
    
    print(f"\n🏁 Tests completados: {'✅ ÉXITO' if connection_success else '❌ FALLOS'}")