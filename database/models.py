#!/usr/bin/env python3
"""
🗄️ DATABASE MODELS - SQLite Simple
==================================

Definición de tablas para el sistema de trading.
"""

import sqlite3
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Ruta del archivo de base de datos
DB_PATH = os.path.join(os.path.dirname(__file__), 'trading_data.db')

def create_database():
    """
    Crear base de datos y todas las tablas necesarias
    """
    try:
        logger.info("🗄️ Creando base de datos SQLite...")
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Tabla 1: Datos de indicadores (para retrofit/backtesting)
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS indicators_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            symbol TEXT NOT NULL,
            
            -- Precios OHLCV
            open_price REAL,
            high_price REAL,
            low_price REAL,
            close_price REAL,
            volume INTEGER,
            
            -- Indicadores técnicos calculados
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
            
            -- Contexto de mercado
            market_regime TEXT,
            volatility_level TEXT,
            
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            
            -- Índices para queries rápidas
            UNIQUE(timestamp, symbol)
        )
        ''')
        
        # Tabla 2: Señales enviadas por Telegram
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS signals_sent (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            symbol TEXT NOT NULL,
            
            -- Datos de la señal
            signal_type TEXT NOT NULL,
            signal_strength INTEGER,
            confidence_level TEXT,
            entry_quality TEXT,
            
            -- Precio y contexto
            current_price REAL,
            market_context TEXT,
            
            -- Breakdown puntuación por indicador
            macd_score INTEGER DEFAULT 0,
            rsi_score INTEGER DEFAULT 0,
            vwap_score INTEGER DEFAULT 0,
            roc_score INTEGER DEFAULT 0,
            bollinger_score INTEGER DEFAULT 0,
            volume_score INTEGER DEFAULT 0,
            
            -- Plan de posición
            strategy_type TEXT,
            max_risk_reward REAL,
            expected_hold_time TEXT,
            
            -- Tracking
            telegram_sent BOOLEAN DEFAULT 1,
            
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # Crear índices para mejorar performance
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_indicators_symbol_time ON indicators_data(symbol, timestamp)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_signals_symbol_time ON signals_sent(symbol, timestamp)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_signals_type ON signals_sent(signal_type)')
        
        conn.commit()
        conn.close()
        
        logger.info(f"✅ Base de datos creada exitosamente: {DB_PATH}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error creando base de datos: {e}")
        return False

def get_database_info():
    """
    Obtener información básica de la base de datos
    """
    try:
        if not os.path.exists(DB_PATH):
            return {"exists": False}
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Contar registros en cada tabla
        cursor.execute("SELECT COUNT(*) FROM indicators_data")
        indicators_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM signals_sent")
        signals_count = cursor.fetchone()[0]
        
        # Tamaño del archivo
        file_size = os.path.getsize(DB_PATH)
        
        conn.close()
        
        return {
            "exists": True,
            "path": DB_PATH,
            "indicators_count": indicators_count,
            "signals_count": signals_count,
            "file_size_mb": round(file_size / (1024*1024), 2)
        }
        
    except Exception as e:
        logger.error(f"❌ Error obteniendo info DB: {e}")
        return {"exists": False, "error": str(e)}

if __name__ == "__main__":
    # Crear base de datos si ejecutas directamente
    print("🗄️ CREANDO BASE DE DATOS SQLite")
    print("=" * 40)
    
    success = create_database()
    if success:
        info = get_database_info()
        print(f"✅ Base de datos creada")
        print(f"📁 Ubicación: {info['path']}")
        print(f"📊 Tablas: indicators_data, signals_sent")
        print("🚀 ¡Listo para usar!")
    else:
        print("❌ Error creando base de datos")