#!/usr/bin/env python3
"""
🔍 DATABASE DIAGNOSTIC TOOL
===========================

Herramienta para diagnosticar el estado de la base de datos
y identificar problemas con datos históricos.
"""

import os
import sys
import sqlite3
import pandas as pd
from datetime import datetime, timedelta

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

try:
    from database.connection import get_connection
    print("✅ Conexión a BD importada correctamente")
except ImportError as e:
    print(f"❌ Error importing database: {e}")
    sys.exit(1)

def check_database_structure():
    """Verificar estructura de base de datos"""
    print("🔍 VERIFICANDO ESTRUCTURA DE BASE DE DATOS")
    print("=" * 50)
    
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Listar todas las tablas
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        
        print(f"📊 Tablas encontradas: {len(tables)}")
        for table in tables:
            table_name = table[0]
            
            # Contar registros en cada tabla
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            count = cursor.fetchone()[0]
            
            print(f"   • {table_name}: {count:,} registros")
            
            # Mostrar estructura de tabla
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = cursor.fetchall()
            print(f"     Columnas: {[col[1] for col in columns]}")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Error verificando estructura: {e}")

def check_ohlcv_data():
    """Verificar datos OHLCV específicamente"""
    print("\n📊 VERIFICANDO DATOS OHLCV")
    print("=" * 50)
    
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Verificar si existe tabla ohlcv_data
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ohlcv_data';")
        if not cursor.fetchone():
            print("❌ Tabla 'ohlcv_data' no existe")
            
            # Buscar tablas similares
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [table[0] for table in cursor.fetchall()]
            print(f"📋 Tablas disponibles: {tables}")
            
            conn.close()
            return
        
        # Obtener información básica
        cursor.execute("SELECT COUNT(*) FROM ohlcv_data")
        total_records = cursor.fetchone()[0]
        print(f"📈 Total registros OHLCV: {total_records:,}")
        
        if total_records == 0:
            print("❌ No hay datos OHLCV en la base de datos")
            conn.close()
            return
        
        # Obtener símbolos únicos
        cursor.execute("SELECT DISTINCT symbol FROM ohlcv_data ORDER BY symbol")
        symbols = [row[0] for row in cursor.fetchall()]
        print(f"📊 Símbolos únicos: {len(symbols)}")
        print(f"   Primeros 10: {symbols[:10]}")
        
        # Verificar rango de fechas
        cursor.execute("SELECT MIN(timestamp), MAX(timestamp) FROM ohlcv_data")
        min_date, max_date = cursor.fetchone()
        print(f"📅 Rango de fechas: {min_date} → {max_date}")
        
        # Mostrar algunos registros de ejemplo
        cursor.execute("""
            SELECT symbol, timestamp, open_price, high_price, low_price, close_price, volume 
            FROM ohlcv_data 
            ORDER BY timestamp DESC 
            LIMIT 5
        """)
        
        print(f"\n📋 REGISTROS DE EJEMPLO:")
        records = cursor.fetchall()
        for record in records:
            symbol, timestamp, open_p, high_p, low_p, close_p, volume = record
            print(f"   {symbol} | {timestamp} | O:{open_p:.2f} H:{high_p:.2f} L:{low_p:.2f} C:{close_p:.2f} | Vol:{volume:,}")
        
        # Verificar datos para AAPL específicamente
        cursor.execute("SELECT COUNT(*) FROM ohlcv_data WHERE symbol = 'AAPL'")
        aapl_count = cursor.fetchone()[0]
        print(f"\n🍎 AAPL registros: {aapl_count:,}")
        
        if aapl_count > 0:
            cursor.execute("""
                SELECT MIN(timestamp), MAX(timestamp), COUNT(*) 
                FROM ohlcv_data 
                WHERE symbol = 'AAPL'
            """)
            min_date, max_date, count = cursor.fetchone()
            print(f"   📅 Rango AAPL: {min_date} → {max_date} ({count:,} registros)")
        
        # Verificar MSFT
        cursor.execute("SELECT COUNT(*) FROM ohlcv_data WHERE symbol = 'MSFT'")
        msft_count = cursor.fetchone()[0]
        print(f"🪟 MSFT registros: {msft_count:,}")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Error verificando OHLCV: {e}")

def check_timestamp_formats():
    """Verificar formatos de timestamp problemáticos"""
    print("\n🕐 VERIFICANDO FORMATOS DE TIMESTAMP")
    print("=" * 50)
    
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Obtener algunos timestamps para análisis
        cursor.execute("""
            SELECT DISTINCT timestamp 
            FROM ohlcv_data 
            ORDER BY timestamp 
            LIMIT 10
        """)
        
        timestamps = [row[0] for row in cursor.fetchall()]
        
        print(f"📅 Primeros 10 timestamps:")
        for i, ts in enumerate(timestamps, 1):
            print(f"   {i}. {ts} (tipo: {type(ts).__name__}, longitud: {len(str(ts))})")
            
            # Intentar parsear con pandas
            try:
                parsed = pd.to_datetime(ts)
                print(f"      ✅ Parseado: {parsed}")
            except Exception as e:
                print(f"      ❌ Error parseando: {e}")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Error verificando timestamps: {e}")

def suggest_solutions():
    """Sugerir soluciones basadas en hallazgos"""
    print("\n💡 POSIBLES SOLUCIONES")
    print("=" * 50)
    
    print("1. 🔄 Si no hay datos OHLCV:")
    print("   → Ejecutar: python historical_data/downloader.py")
    print("   → Verificar conexión a fuente de datos")
    
    print("\n2. 🕐 Si hay problemas de timestamp:")
    print("   → Actualizar formato de parseo en historical_indicators_calc.py")
    print("   → Verificar zona horaria en datos originales")
    
    print("\n3. 📊 Si hay datos pero pocos símbolos:")
    print("   → Verificar lista de símbolos en config.py")
    print("   → Asegurar descarga completa de datos")
    
    print("\n4. 🔍 Para debugging adicional:")
    print("   → python -c \"import sqlite3; conn=sqlite3.connect('database/trading_data.db'); print(pd.read_sql('SELECT * FROM ohlcv_data LIMIT 3', conn))\"")

def main():
    """Ejecutar diagnóstico completo"""
    print("🔍 DIAGNÓSTICO COMPLETO DE BASE DE DATOS")
    print("=" * 70)
    
    check_database_structure()
    check_ohlcv_data()
    check_timestamp_formats()
    suggest_solutions()
    
    print(f"\n✅ Diagnóstico completado")

if __name__ == "__main__":
    main()