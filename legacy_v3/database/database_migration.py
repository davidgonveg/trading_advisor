#!/usr/bin/env python3
"""
🗄️ DATABASE MIGRATION - Agregar tabla OHLCV_DATA
===============================================

Script para agregar la nueva tabla ohlcv_data a la base de datos existente.
Esta tabla almacenará los datos raw OHLCV antes de calcular indicadores.

USO:
    python database_migration.py
"""

import os
import sys
import sqlite3
import logging
from datetime import datetime

# Configurar paths
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir) if current_dir.endswith('database') else current_dir
sys.path.insert(0, project_root)

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# Ruta de la base de datos
DB_PATH = os.path.join(os.path.dirname(__file__), 'trading_data.db')

def backup_database():
    """Crear backup de la base de datos antes de la migración"""
    try:
        if os.path.exists(DB_PATH):
            backup_name = f"trading_data_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
            backup_path = os.path.join(os.path.dirname(DB_PATH), backup_name)
            
            # Copiar archivo
            import shutil
            shutil.copy2(DB_PATH, backup_path)
            
            logger.info(f"✅ Backup creado: {backup_name}")
            return backup_path
        else:
            logger.info("ℹ️ No existe base de datos previa, no se necesita backup")
            return None
            
    except Exception as e:
        logger.error(f"❌ Error creando backup: {e}")
        return None

def check_current_tables():
    """Verificar tablas existentes"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]
        
        logger.info(f"📊 Tablas existentes: {tables}")
        
        # Contar registros en cada tabla
        for table in tables:
            cursor.execute(f"SELECT COUNT(*) FROM {table};")
            count = cursor.fetchone()[0]
            logger.info(f"   {table}: {count:,} registros")
        
        conn.close()
        return tables
        
    except Exception as e:
        logger.error(f"❌ Error verificando tablas: {e}")
        return []

def add_ohlcv_table():
    """Agregar la nueva tabla ohlcv_data"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        logger.info("🔧 Creando tabla ohlcv_data...")
        
        # Crear tabla OHLCV raw data
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS ohlcv_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            symbol TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            
            -- Datos OHLCV básicos
            open_price REAL NOT NULL,
            high_price REAL NOT NULL,
            low_price REAL NOT NULL,
            close_price REAL NOT NULL,
            volume INTEGER NOT NULL,
            
            -- Metadatos adicionales (si están disponibles en CSV)
            dividends REAL DEFAULT 0.0,
            stock_splits REAL DEFAULT 0.0,
            
            -- Timestamps de control
            source_file TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            
            -- Constraint único por timestamp, símbolo y timeframe
            UNIQUE(timestamp, symbol, timeframe)
        )
        ''')
        
        # Crear índices para performance
        logger.info("📑 Creando índices...")
        
        cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_ohlcv_symbol_timeframe 
        ON ohlcv_data(symbol, timeframe)
        ''')
        
        cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_ohlcv_timestamp 
        ON ohlcv_data(timestamp)
        ''')
        
        cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_ohlcv_symbol_timestamp 
        ON ohlcv_data(symbol, timestamp)
        ''')
        
        # Crear trigger para actualizar updated_at automáticamente
        logger.info("⚡ Creando trigger para updated_at...")
        
        cursor.execute('''
        CREATE TRIGGER IF NOT EXISTS update_ohlcv_timestamp 
        AFTER UPDATE ON ohlcv_data
        FOR EACH ROW
        BEGIN
            UPDATE ohlcv_data 
            SET updated_at = CURRENT_TIMESTAMP 
            WHERE id = NEW.id;
        END
        ''')
        
        conn.commit()
        conn.close()
        
        logger.info("✅ Tabla ohlcv_data creada exitosamente")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error creando tabla ohlcv_data: {e}")
        return False

def verify_migration():
    """Verificar que la migración fue exitosa"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Verificar que la tabla existe
        cursor.execute('''
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name='ohlcv_data';
        ''')
        
        if not cursor.fetchone():
            logger.error("❌ La tabla ohlcv_data no fue creada")
            return False
        
        # Verificar estructura de la tabla
        cursor.execute("PRAGMA table_info(ohlcv_data);")
        columns = cursor.fetchall()
        
        logger.info(f"📋 Tabla ohlcv_data tiene {len(columns)} columnas:")
        for col in columns:
            col_id, col_name, col_type, not_null, default_val, is_pk = col
            pk_str = " (PK)" if is_pk else ""
            not_null_str = " NOT NULL" if not_null else ""
            default_str = f" DEFAULT {default_val}" if default_val else ""
            logger.info(f"   {col_name}: {col_type}{pk_str}{not_null_str}{default_str}")
        
        # Verificar índices
        cursor.execute("PRAGMA index_list(ohlcv_data);")
        indexes = cursor.fetchall()
        
        logger.info(f"📑 Índices creados: {len(indexes)}")
        for idx in indexes:
            logger.info(f"   {idx[1]}")
        
        conn.close()
        
        logger.info("✅ Migración verificada correctamente")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error verificando migración: {e}")
        return False

def main():
    """Función principal de migración"""
    print("🗄️ DATABASE MIGRATION - AGREGAR TABLA OHLCV")
    print("=" * 50)
    
    # 1. Verificar estado actual
    logger.info("🔍 Verificando estado actual de la base de datos...")
    current_tables = check_current_tables()
    
    if 'ohlcv_data' in current_tables:
        logger.warning("⚠️ La tabla ohlcv_data ya existe")
        response = input("¿Continuar anyway? (y/N): ").lower().strip()
        if response != 'y':
            logger.info("🛑 Migración cancelada")
            return
    
    # 2. Crear backup
    logger.info("💾 Creando backup...")
    backup_path = backup_database()
    
    # 3. Aplicar migración
    logger.info("🚀 Aplicando migración...")
    success = add_ohlcv_table()
    
    if not success:
        logger.error("❌ Migración falló")
        return
    
    # 4. Verificar migración
    logger.info("🔍 Verificando migración...")
    if verify_migration():
        print("\n" + "=" * 50)
        print("✅ MIGRACIÓN COMPLETADA EXITOSAMENTE")
        print("=" * 50)
        print("📊 Nueva tabla: ohlcv_data")
        print("📑 Índices: 3 índices creados")
        print("⚡ Trigger: update timestamp automático")
        if backup_path:
            print(f"💾 Backup: {os.path.basename(backup_path)}")
        print("\n🚀 ¡Listo para poblar datos históricos!")
    else:
        logger.error("❌ Error en verificación - revisar logs")

if __name__ == "__main__":
    main()