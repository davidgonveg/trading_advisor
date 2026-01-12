#!/usr/bin/env python3
"""
🔍 QUICK DATA CHECK - Diagnóstico Rápido
========================================

Script para verificar la estructura exacta de tu base de datos
y qué columnas están disponibles realmente.
"""

import os
import sys
import sqlite3
import pandas as pd

# Configurar paths
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

try:
    from database.connection import get_connection
    print("✅ Conexión a BD importada correctamente")
except ImportError as e:
    print(f"❌ Error importing database: {e}")
    sys.exit(1)

def check_table_structure():
    """Verificar estructura exacta de indicators_data"""
    print("🔍 VERIFICANDO ESTRUCTURA EXACTA DE indicators_data")
    print("=" * 60)
    
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Obtener info de columnas
        cursor.execute("PRAGMA table_info(indicators_data)")
        columns = cursor.fetchall()
        
        print(f"📊 Total columnas: {len(columns)}")
        print("\n📋 TODAS LAS COLUMNAS DISPONIBLES:")
        
        for i, col in enumerate(columns, 1):
            col_id, col_name, col_type, not_null, default_val, is_pk = col
            pk_str = " (PK)" if is_pk else ""
            not_null_str = " NOT NULL" if not_null else ""
            print(f"   {i:2d}. {col_name:<20} {col_type:<10}{pk_str}{not_null_str}")
        
        # Verificar datos de muestra
        print(f"\n📈 DATOS DE MUESTRA:")
        cursor.execute("SELECT COUNT(*) FROM indicators_data")
        total_count = cursor.fetchone()[0]
        print(f"   Total registros: {total_count:,}")
        
        if total_count > 0:
            # Obtener algunos registros de muestra
            cursor.execute("SELECT * FROM indicators_data LIMIT 1")
            sample_data = cursor.fetchone()
            
            print(f"\n🔬 PRIMER REGISTRO (valores):")
            col_names = [col[1] for col in columns]
            for col_name, value in zip(col_names, sample_data):
                print(f"   {col_name:<20} = {value}")
        
        conn.close()
        return [col[1] for col in columns]
        
    except Exception as e:
        print(f"❌ Error verificando estructura: {e}")
        return []

def suggest_correct_query(available_columns):
    """Sugerir query correcta basada en columnas disponibles"""
    print(f"\n🛠️ SUGERENCIA DE QUERY CORRECTA:")
    print("=" * 60)
    
    # Mapeo de nombres posibles
    column_mapping = {
        # OHLCV
        'Open': ['open', 'open_price', 'Open'],
        'High': ['high', 'high_price', 'High'], 
        'Low': ['low', 'low_price', 'Low'],
        'Close': ['close', 'close_price', 'Close'],
        'Volume': ['volume', 'Volume'],
        
        # Indicadores técnicos
        'RSI': ['rsi', 'rsi_14', 'rsi_value', 'RSI'],
        'MACD': ['macd', 'macd_line', 'macd_value', 'MACD'],
        'MACD_Signal': ['macd_signal', 'macd_sig', 'signal'],
        'MACD_Histogram': ['macd_histogram', 'macd_hist', 'histogram'],
        'VWAP': ['vwap', 'vwap_price', 'vwap_value', 'VWAP'],
        'ATR': ['atr', 'atr_14', 'atr_value', 'ATR'],
        'ROC': ['roc', 'roc_10', 'roc_value', 'ROC'],
        'BB_Upper': ['bb_upper', 'bollinger_upper', 'upper_band'],
        'BB_Lower': ['bb_lower', 'bollinger_lower', 'lower_band'],
        'BB_Middle': ['bb_middle', 'bollinger_middle', 'middle_band']
    }
    
    # Encontrar matches
    found_columns = {}
    for standard_name, possible_names in column_mapping.items():
        for possible in possible_names:
            if possible in available_columns:
                found_columns[standard_name] = possible
                break
    
    print("🎯 COLUMNAS ENCONTRADAS:")
    for standard, actual in found_columns.items():
        print(f"   {standard:<15} -> {actual}")
    
    # Generar query sugerida
    essential_cols = ['timestamp', 'symbol']
    query_cols = essential_cols.copy()
    
    for standard, actual in found_columns.items():
        query_cols.append(actual)
    
    print(f"\n📝 QUERY SUGERIDA:")
    print("SELECT")
    for i, col in enumerate(query_cols):
        comma = "," if i < len(query_cols) - 1 else ""
        print(f"    {col}{comma}")
    print("FROM indicators_data")
    print("WHERE symbol = ?")
    print("AND timestamp BETWEEN ? AND ?")
    print("ORDER BY timestamp")
    
    return found_columns

def check_sample_data():
    """Verificar algunos datos de muestra para símbolos específicos"""
    print(f"\n📊 VERIFICANDO DATOS PARA SÍMBOLOS ESPECÍFICOS:")
    print("=" * 60)
    
    try:
        conn = get_connection()
        
        # Verificar qué símbolos están disponibles
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT symbol FROM indicators_data LIMIT 10")
        symbols = [row[0] for row in cursor.fetchall()]
        
        print(f"🎯 Símbolos disponibles: {symbols}")
        
        if symbols:
            # Tomar el primer símbolo y mostrar algunos datos
            test_symbol = symbols[0]
            cursor.execute("""
            SELECT COUNT(*) FROM indicators_data 
            WHERE symbol = ? 
            """, (test_symbol,))
            count = cursor.fetchone()[0]
            
            print(f"\n📈 Datos para {test_symbol}: {count:,} registros")
            
            # Rango de fechas
            cursor.execute("""
            SELECT MIN(timestamp), MAX(timestamp) FROM indicators_data 
            WHERE symbol = ? 
            """, (test_symbol,))
            date_range = cursor.fetchone()
            
            print(f"📅 Rango: {date_range[0]} a {date_range[1]}")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Error verificando datos de muestra: {e}")

def main():
    """Ejecutar diagnóstico completo"""
    print("🔍 DIAGNÓSTICO RÁPIDO DE BASE DE DATOS")
    print("=" * 70)
    
    # 1. Verificar estructura
    available_columns = check_table_structure()
    
    if available_columns:
        # 2. Sugerir query correcta
        found_columns = suggest_correct_query(available_columns)
        
        # 3. Verificar datos de muestra
        check_sample_data()
        
        print(f"\n🎯 PRÓXIMOS PASOS:")
        print("1. Usa las columnas encontradas arriba para corregir la query")
        print("2. Actualiza el método get_historical_data_with_indicators()")
        print("3. Ejecuta nuevamente el backtest")
        
    else:
        print("❌ No se pudo obtener información de la base de datos")

if __name__ == "__main__":
    main()