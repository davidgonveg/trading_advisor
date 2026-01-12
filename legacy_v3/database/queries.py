#!/usr/bin/env python3
"""
📊 DATABASE QUERIES - Análisis de datos de trading
=================================================

Funciones útiles para analizar tus datos históricos de trading.
"""

import sqlite3
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
import os

logger = logging.getLogger(__name__)

# Ruta del archivo de base de datos
DB_PATH = os.path.join(os.path.dirname(__file__), 'trading_data.db')

def get_connection():
    """Obtener conexión a la base de datos SQLite"""
    try:
        conn = sqlite3.connect(DB_PATH, timeout=30.0)
        conn.row_factory = sqlite3.Row
        return conn
    except Exception as e:
        logger.error(f"❌ Error conectando a DB: {e}")
        return None

# =============================================================================
# 📈 ANÁLISIS DE SEÑALES
# =============================================================================

def get_signal_summary(days: int = 30) -> Dict[str, Any]:
    """
    Resumen básico de señales de los últimos N días
    """
    try:
        conn = get_connection()
        if not conn:
            return {}
        
        cursor = conn.cursor()
        
        # Señales totales por tipo
        cursor.execute('''
        SELECT 
            signal_type,
            COUNT(*) as total,
            AVG(signal_strength) as avg_strength,
            MIN(signal_strength) as min_strength,
            MAX(signal_strength) as max_strength
        FROM signals_sent 
        WHERE datetime(timestamp) >= datetime('now', '-{} days')
        GROUP BY signal_type
        '''.format(days))
        
        signals_by_type = {}
        for row in cursor.fetchall():
            signals_by_type[row['signal_type']] = {
                'total': row['total'],
                'avg_strength': round(row['avg_strength'], 1),
                'min_strength': row['min_strength'],
                'max_strength': row['max_strength']
            }
        
        # Señales por símbolo
        cursor.execute('''
        SELECT 
            symbol,
            COUNT(*) as total_signals,
            AVG(signal_strength) as avg_strength
        FROM signals_sent 
        WHERE datetime(timestamp) >= datetime('now', '-{} days')
        GROUP BY symbol
        ORDER BY total_signals DESC
        '''.format(days))
        
        signals_by_symbol = {}
        for row in cursor.fetchall():
            signals_by_symbol[row['symbol']] = {
                'total_signals': row['total_signals'],
                'avg_strength': round(row['avg_strength'], 1)
            }
        
        conn.close()
        
        return {
            'period_days': days,
            'by_type': signals_by_type,
            'by_symbol': signals_by_symbol,
            'generated_at': datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"❌ Error en signal summary: {e}")
        return {}

def get_best_signal_conditions() -> List[Dict]:
    """
    Condiciones que generan las señales más fuertes
    """
    try:
        conn = get_connection()
        if not conn:
            return []
        
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT 
            market_context,
            COUNT(*) as signal_count,
            AVG(signal_strength) as avg_strength,
            strategy_type,
            confidence_level
        FROM signals_sent 
        WHERE signal_strength >= 80
        GROUP BY market_context, strategy_type, confidence_level
        HAVING signal_count >= 2
        ORDER BY avg_strength DESC, signal_count DESC
        LIMIT 10
        ''')
        
        conditions = []
        for row in cursor.fetchall():
            conditions.append({
                'market_context': row['market_context'] or 'Unknown',
                'signal_count': row['signal_count'],
                'avg_strength': round(row['avg_strength'], 1),
                'strategy_type': row['strategy_type'] or 'Unknown',
                'confidence_level': row['confidence_level']
            })
        
        conn.close()
        return conditions
        
    except Exception as e:
        logger.error(f"❌ Error en best conditions: {e}")
        return []

def get_indicator_breakdown() -> Dict[str, Dict]:
    """
    Análisis de efectividad por indicador
    """
    try:
        conn = get_connection()
        if not conn:
            return {}
        
        cursor = conn.cursor()
        
        indicators = ['macd_score', 'rsi_score', 'vwap_score', 'roc_score', 'bollinger_score', 'volume_score']
        breakdown = {}
        
        for indicator in indicators:
            cursor.execute(f'''
            SELECT 
                AVG({indicator}) as avg_score,
                COUNT(CASE WHEN {indicator} >= 15 THEN 1 END) as high_scores,
                COUNT(*) as total_signals
            FROM signals_sent 
            WHERE {indicator} IS NOT NULL AND {indicator} > 0
            ''')
            
            row = cursor.fetchone()
            if row:
                breakdown[indicator.replace('_score', '').upper()] = {
                    'avg_score': round(row['avg_score'], 1),
                    'high_scores': row['high_scores'],
                    'total_signals': row['total_signals'],
                    'high_score_rate': round((row['high_scores'] / row['total_signals']) * 100, 1) if row['total_signals'] > 0 else 0
                }
        
        conn.close()
        return breakdown
        
    except Exception as e:
        logger.error(f"❌ Error en indicator breakdown: {e}")
        return {}

# =============================================================================
# 📊 ANÁLISIS DE INDICADORES TÉCNICOS
# =============================================================================

def get_market_regime_analysis(days: int = 30) -> Dict[str, Any]:
    """
    Análisis de regímenes de mercado y su frecuencia
    """
    try:
        conn = get_connection()
        if not conn:
            return {}
        
        cursor = conn.cursor()
        
        # Regímenes más frecuentes
        cursor.execute('''
        SELECT 
            market_regime,
            COUNT(*) as occurrences,
            AVG(rsi_value) as avg_rsi,
            AVG(roc_value) as avg_roc,
            AVG(atr_percentage) as avg_atr
        FROM indicators_data 
        WHERE datetime(timestamp) >= datetime('now', '-{} days')
        AND market_regime IS NOT NULL
        GROUP BY market_regime
        ORDER BY occurrences DESC
        '''.format(days))
        
        regimes = {}
        for row in cursor.fetchall():
            regimes[row['market_regime']] = {
                'occurrences': row['occurrences'],
                'avg_rsi': round(row['avg_rsi'], 1) if row['avg_rsi'] else None,
                'avg_roc': round(row['avg_roc'], 2) if row['avg_roc'] else None,
                'avg_atr': round(row['avg_atr'], 2) if row['avg_atr'] else None
            }
        
        # Volatilidad por símbolo
        cursor.execute('''
        SELECT 
            symbol,
            AVG(atr_percentage) as avg_volatility,
            volatility_level,
            COUNT(*) as readings
        FROM indicators_data 
        WHERE datetime(timestamp) >= datetime('now', '-{} days')
        GROUP BY symbol, volatility_level
        ORDER BY avg_volatility DESC
        '''.format(days))
        
        volatility_by_symbol = {}
        for row in cursor.fetchall():
            symbol = row['symbol']
            if symbol not in volatility_by_symbol:
                volatility_by_symbol[symbol] = []
            
            volatility_by_symbol[symbol].append({
                'level': row['volatility_level'],
                'avg_volatility': round(row['avg_volatility'], 2),
                'readings': row['readings']
            })
        
        conn.close()
        
        return {
            'period_days': days,
            'market_regimes': regimes,
            'volatility_by_symbol': volatility_by_symbol
        }
        
    except Exception as e:
        logger.error(f"❌ Error en market regime analysis: {e}")
        return {}

def get_symbol_performance(symbol: str, days: int = 30) -> Dict[str, Any]:
    """
    Análisis detallado de un símbolo específico
    """
    try:
        conn = get_connection()
        if not conn:
            return {}
        
        cursor = conn.cursor()
        
        # Estadísticas básicas
        cursor.execute('''
        SELECT 
            COUNT(*) as total_readings,
            AVG(rsi_value) as avg_rsi,
            AVG(roc_value) as avg_roc,
            AVG(atr_percentage) as avg_volatility,
            MIN(close_price) as min_price,
            MAX(close_price) as max_price,
            (MAX(close_price) - MIN(close_price)) / MIN(close_price) * 100 as price_range_pct
        FROM indicators_data 
        WHERE symbol = ? 
        AND datetime(timestamp) >= datetime('now', '-{} days')
        '''.format(days), (symbol,))
        
        stats = cursor.fetchone()
        
        # Señales generadas
        cursor.execute('''
        SELECT 
            COUNT(*) as total_signals,
            AVG(signal_strength) as avg_strength,
            signal_type
        FROM signals_sent 
        WHERE symbol = ? 
        AND datetime(timestamp) >= datetime('now', '-{} days')
        GROUP BY signal_type
        '''.format(days), (symbol,))
        
        signals = {}
        for row in cursor.fetchall():
            signals[row['signal_type']] = {
                'count': row['total_signals'],
                'avg_strength': round(row['avg_strength'], 1)
            }
        
        # Trending de precios (últimos 10 días)
        cursor.execute('''
        SELECT 
            DATE(timestamp) as date,
            AVG(close_price) as avg_price,
            AVG(rsi_value) as avg_rsi
        FROM indicators_data 
        WHERE symbol = ? 
        AND datetime(timestamp) >= datetime('now', '-10 days')
        GROUP BY DATE(timestamp)
        ORDER BY date DESC
        LIMIT 10
        ''', (symbol,))
        
        price_trend = []
        for row in cursor.fetchall():
            price_trend.append({
                'date': row['date'],
                'avg_price': round(row['avg_price'], 2),
                'avg_rsi': round(row['avg_rsi'], 1)
            })
        
        conn.close()
        
        result = {
            'symbol': symbol,
            'period_days': days,
            'statistics': {
                'total_readings': stats['total_readings'],
                'avg_rsi': round(stats['avg_rsi'], 1) if stats['avg_rsi'] else None,
                'avg_roc': round(stats['avg_roc'], 2) if stats['avg_roc'] else None,
                'avg_volatility': round(stats['avg_volatility'], 2) if stats['avg_volatility'] else None,
                'price_range': {
                    'min': round(stats['min_price'], 2) if stats['min_price'] else None,
                    'max': round(stats['max_price'], 2) if stats['max_price'] else None,
                    'range_pct': round(stats['price_range_pct'], 2) if stats['price_range_pct'] else None
                }
            },
            'signals_generated': signals,
            'price_trend': price_trend
        }
        
        return result
        
    except Exception as e:
        logger.error(f"❌ Error en symbol performance: {e}")
        return {}

# =============================================================================
# 🕐 ANÁLISIS TEMPORAL
# =============================================================================

def get_timing_analysis() -> Dict[str, Any]:
    """
    Análisis de mejores momentos para señales
    """
    try:
        conn = get_connection()
        if not conn:
            return {}
        
        cursor = conn.cursor()
        
        # Por hora del día
        cursor.execute('''
        SELECT 
            strftime('%H', timestamp) as hour,
            COUNT(*) as signal_count,
            AVG(signal_strength) as avg_strength
        FROM signals_sent 
        GROUP BY strftime('%H', timestamp)
        HAVING signal_count >= 2
        ORDER BY signal_count DESC
        ''')
        
        by_hour = {}
        for row in cursor.fetchall():
            by_hour[f"{row['hour']}:00"] = {
                'signal_count': row['signal_count'],
                'avg_strength': round(row['avg_strength'], 1)
            }
        
        # Por día de la semana  
        cursor.execute('''
        SELECT 
            strftime('%w', timestamp) as day_of_week,
            COUNT(*) as signal_count,
            AVG(signal_strength) as avg_strength
        FROM signals_sent 
        GROUP BY strftime('%w', timestamp)
        ORDER BY signal_count DESC
        ''')
        
        days_map = {'0': 'Domingo', '1': 'Lunes', '2': 'Martes', '3': 'Miércoles', 
                   '4': 'Jueves', '5': 'Viernes', '6': 'Sábado'}
        
        by_day = {}
        for row in cursor.fetchall():
            day_name = days_map.get(row['day_of_week'], 'Unknown')
            by_day[day_name] = {
                'signal_count': row['signal_count'],
                'avg_strength': round(row['avg_strength'], 1)
            }
        
        conn.close()
        
        return {
            'by_hour_of_day': by_hour,
            'by_day_of_week': by_day
        }
        
    except Exception as e:
        logger.error(f"❌ Error en timing analysis: {e}")
        return {}

# =============================================================================
# 📋 QUERIES RÁPIDAS PARA USO DIARIO
# =============================================================================

def get_recent_activity(hours: int = 24) -> Dict[str, Any]:
    """
    Resumen de actividad reciente
    """
    try:
        conn = get_connection()
        if not conn:
            return {}
        
        cursor = conn.cursor()
        
        # Últimas señales
        cursor.execute('''
        SELECT symbol, signal_type, signal_strength, timestamp
        FROM signals_sent 
        WHERE datetime(timestamp) >= datetime('now', '-{} hours')
        ORDER BY timestamp DESC
        LIMIT 5
        '''.format(hours))
        
        recent_signals = []
        for row in cursor.fetchall():
            recent_signals.append({
                'symbol': row['symbol'],
                'type': row['signal_type'],
                'strength': row['signal_strength'],
                'timestamp': row['timestamp']
            })
        
        # Actividad por símbolo
        cursor.execute('''
        SELECT 
            symbol,
            COUNT(*) as indicator_updates
        FROM indicators_data 
        WHERE datetime(timestamp) >= datetime('now', '-{} hours')
        GROUP BY symbol
        ORDER BY indicator_updates DESC
        '''.format(hours))
        
        symbol_activity = {}
        for row in cursor.fetchall():
            symbol_activity[row['symbol']] = row['indicator_updates']
        
        conn.close()
        
        return {
            'period_hours': hours,
            'recent_signals': recent_signals,
            'symbol_activity': symbol_activity,
            'total_signals': len(recent_signals),
            'total_symbols_active': len(symbol_activity)
        }
        
    except Exception as e:
        logger.error(f"❌ Error en recent activity: {e}")
        return {}

def get_database_health() -> Dict[str, Any]:
    """
    Estado de salud de la base de datos
    """
    try:
        conn = get_connection()
        if not conn:
            return {'status': 'ERROR', 'message': 'No connection'}
        
        cursor = conn.cursor()
        
        # Conteos básicos
        cursor.execute("SELECT COUNT(*) FROM indicators_data")
        indicators_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM signals_sent")
        signals_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(DISTINCT symbol) FROM indicators_data")
        unique_symbols = cursor.fetchone()[0]
        
        # Rango de fechas
        cursor.execute("SELECT MIN(timestamp), MAX(timestamp) FROM indicators_data")
        date_range = cursor.fetchone()
        
        # Actividad reciente
        cursor.execute('''
        SELECT COUNT(*) FROM indicators_data 
        WHERE datetime(timestamp) >= datetime('now', '-24 hours')
        ''')
        recent_activity = cursor.fetchone()[0]
        
        conn.close()
        
        # Tamaño del archivo
        file_size_mb = round(os.path.getsize(DB_PATH) / (1024*1024), 2) if os.path.exists(DB_PATH) else 0
        
        return {
            'status': 'HEALTHY',
            'indicators_count': indicators_count,
            'signals_count': signals_count,
            'unique_symbols': unique_symbols,
            'date_range': {
                'first_record': date_range[0],
                'last_record': date_range[1]
            },
            'recent_activity_24h': recent_activity,
            'database_size_mb': file_size_mb,
            'last_check': datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"❌ Error en database health: {e}")
        return {'status': 'ERROR', 'message': str(e)}

# =============================================================================
# 🧪 FUNCIÓN DE DEMO
# =============================================================================

def demo_all_queries():
    """
    Ejecutar todas las queries para ver qué datos tienes
    """
    print("📊 ANÁLISIS COMPLETO DE TUS DATOS DE TRADING")
    print("=" * 60)
    
    # 1. Estado de la base de datos
    print("\n1️⃣ ESTADO DE LA BASE DE DATOS:")
    health = get_database_health()
    print(f"   Estado: {health.get('status', 'Unknown')}")
    print(f"   Indicadores: {health.get('indicators_count', 0)}")
    print(f"   Señales: {health.get('signals_count', 0)}")
    print(f"   Símbolos únicos: {health.get('unique_symbols', 0)}")
    print(f"   Tamaño DB: {health.get('database_size_mb', 0)} MB")
    
    # 2. Actividad reciente
    print("\n2️⃣ ACTIVIDAD RECIENTE (24H):")
    activity = get_recent_activity(24)
    print(f"   Señales generadas: {activity.get('total_signals', 0)}")
    print(f"   Símbolos activos: {activity.get('total_symbols_active', 0)}")
    
    recent_signals = activity.get('recent_signals', [])
    if recent_signals:
        print("   Últimas señales:")
        for signal in recent_signals[:3]:
            print(f"     • {signal['symbol']} {signal['type']} ({signal['strength']} pts)")
    
    # 3. Resumen de señales
    print("\n3️⃣ RESUMEN DE SEÑALES (30 días):")
    signal_summary = get_signal_summary(30)
    by_type = signal_summary.get('by_type', {})
    
    for signal_type, data in by_type.items():
        print(f"   {signal_type}: {data['total']} señales (promedio {data['avg_strength']} pts)")
    
    # 4. Mejores condiciones
    print("\n4️⃣ MEJORES CONDICIONES DE SEÑAL:")
    conditions = get_best_signal_conditions()
    for i, condition in enumerate(conditions[:3], 1):
        print(f"   {i}. {condition['market_context']} - {condition['avg_strength']} pts promedio")
    
    # 5. Análisis de indicadores
    print("\n5️⃣ EFECTIVIDAD POR INDICADOR:")
    breakdown = get_indicator_breakdown()
    for indicator, data in breakdown.items():
        print(f"   {indicator}: {data['avg_score']} pts promedio ({data['high_score_rate']}% scores altos)")
    
    # 6. Timing
    print("\n6️⃣ ANÁLISIS DE TIMING:")
    timing = get_timing_analysis()
    
    by_hour = timing.get('by_hour_of_day', {})
    if by_hour:
        best_hour = max(by_hour.items(), key=lambda x: x[1]['signal_count'])
        print(f"   Mejor hora: {best_hour[0]} ({best_hour[1]['signal_count']} señales)")
    
    by_day = timing.get('by_day_of_week', {})
    if by_day:
        best_day = max(by_day.items(), key=lambda x: x[1]['signal_count'])
        print(f"   Mejor día: {best_day[0]} ({best_day[1]['signal_count']} señales)")
    
    print("\n✅ Análisis completado")

if __name__ == "__main__":
    # Ejecutar demo si se llama directamente
    demo_all_queries()