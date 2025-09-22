#!/usr/bin/env python3
"""
🔗 DATABASE CONNECTION - SQLite Simple - FIXED OHLC VERSION
=========================================================

FIXED: save_indicators_data() ahora guarda TODOS los campos OHLC
"""

import sqlite3
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
import json
import os

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
        
        # ✅ FIXED: Extraer TODOS los precios OHLC
        current_price = indicators.get('current_price', 0)  # Este será close_price
        open_price = indicators.get('open_price', current_price)  # Si no está, usar close
        high_price = indicators.get('high_price', current_price)  # Si no está, usar close
        low_price = indicators.get('low_price', current_price)   # Si no está, usar close
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
        
        # ✅ FIXED: INSERT con TODOS los campos OHLC
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

def get_database_stats() -> Dict[str, Any]:
    """
    Obtener estadísticas básicas de la base de datos
    
    Returns:
        Diccionario con estadísticas
    """
    try:
        conn = get_connection()
        if not conn:
            return {}
        
        cursor = conn.cursor()
        
        # Contar registros
        cursor.execute("SELECT COUNT(*) FROM indicators_data")
        indicators_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM signals_sent")
        signals_count = cursor.fetchone()[0]
        
        # Símbolos únicos
        cursor.execute("SELECT COUNT(DISTINCT symbol) FROM indicators_data")
        unique_symbols = cursor.fetchone()[0]
        
        # Rango de fechas
        cursor.execute("SELECT MIN(timestamp), MAX(timestamp) FROM signals_sent")
        date_range = cursor.fetchone()
        
        # Últimas señales por tipo
        cursor.execute('''
        SELECT signal_type, COUNT(*) 
        FROM signals_sent 
        WHERE datetime(timestamp) >= datetime('now', '-7 days')
        GROUP BY signal_type
        ''')
        recent_signals = dict(cursor.fetchall())
        
        conn.close()
        
        stats = {
            'indicators_count': indicators_count,
            'signals_count': signals_count,
            'unique_symbols': unique_symbols,
            'date_range': {
                'first_signal': date_range[0] if date_range[0] else None,
                'last_signal': date_range[1] if date_range[1] else None
            },
            'recent_signals_by_type': recent_signals,
            'database_path': DB_PATH,
            'database_size_mb': round(os.path.getsize(DB_PATH) / (1024*1024), 2) if os.path.exists(DB_PATH) else 0
        }
        
        return stats
        
    except Exception as e:
        logger.error(f"❌ Error obteniendo estadísticas: {e}")
        return {}

def test_database_connection():
    """
    Test básico de la conexión a la base de datos
    """
    print("🧪 TESTING DATABASE CONNECTION")
    print("=" * 40)
    
    try:
        # Test conexión
        conn = get_connection()
        if conn:
            print("✅ Conexión SQLite exitosa")
            conn.close()
        else:
            print("❌ Error en conexión")
            return False
        
        # Test estadísticas
        stats = get_database_stats()
        print(f"📊 Indicadores almacenados: {stats.get('indicators_count', 0)}")
        print(f"📤 Señales almacenadas: {stats.get('signals_count', 0)}")
        print(f"📈 Símbolos únicos: {stats.get('unique_symbols', 0)}")
        print(f"💾 Tamaño DB: {stats.get('database_size_mb', 0)} MB")
        
        print("✅ Database funcionando correctamente")
        return True
        
    except Exception as e:
        print(f"❌ Error en test: {e}")
        return False

if __name__ == "__main__":
    # Ejecutar test si se llama directamente
    test_database_connection()