#!/usr/bin/env python3
"""
🔧 FIXED DATABASE POPULATOR
==========================

Corrige los problemas de população de la base de datos
"""

import os
import sys
import pandas as pd
import sqlite3
from datetime import datetime
import logging

# Setup paths
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.insert(0, project_root)

from database.connection import get_connection
from indicators import TechnicalIndicators

def fix_populate_database():
    """Población corregida de la base de datos"""
    
    print("🔧 FIXED DATABASE POPULATION")
    print("=" * 50)
    
    # Limpiar datos existentes
    print("🧹 Limpiando datos existentes...")
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM indicators_data")
    conn.commit()
    
    # Obtener archivos CSV
    raw_data_dir = 'raw_data'
    if not os.path.exists(raw_data_dir):
        print("❌ Directorio raw_data no existe")
        return
    
    csv_files = [f for f in os.listdir(raw_data_dir) if f.endswith('.csv')]
    print(f"📁 Encontrados {len(csv_files)} archivos CSV")
    
    indicators_calc = TechnicalIndicators()
    total_inserted = 0
    
    for i, csv_file in enumerate(csv_files, 1):
        try:
            print(f"\n📊 [{i}/{len(csv_files)}] Procesando: {csv_file}")
            
            # Extraer símbolo del nombre del archivo
            symbol = csv_file.split('_')[0]
            timeframe = csv_file.split('_')[1] if '_' in csv_file else '1h'
            
            # Leer CSV
            filepath = os.path.join(raw_data_dir, csv_file)
            df = pd.read_csv(filepath)
            
            print(f"   📈 {len(df)} rows, Columns: {list(df.columns)[:5]}")
            
            # Detectar formato de columnas
            if 'Datetime' in df.columns:
                df['timestamp'] = pd.to_datetime(df['Datetime'])
            elif 'Date' in df.columns:
                df['timestamp'] = pd.to_datetime(df['Date'])
            elif 'timestamp' in df.columns:
                df['timestamp'] = pd.to_datetime(df['timestamp'])
            else:
                print(f"   ⚠️ No se encontró columna de tiempo, usando index")
                df['timestamp'] = pd.to_datetime(df.index)
            
            # Normalizar nombres de columnas
            column_mapping = {
                'open': 'open', 'Open': 'open',
                'high': 'high', 'High': 'high', 
                'low': 'low', 'Low': 'low',
                'close': 'close', 'Close': 'close',
                'volume': 'volume', 'Volume': 'volume'
            }
            
            for old_col, new_col in column_mapping.items():
                if old_col in df.columns:
                    df[new_col] = df[old_col]
            
            # Verificar columnas esenciales
            required_cols = ['open', 'high', 'low', 'close', 'volume']
            missing_cols = [col for col in required_cols if col not in df.columns]
            
            if missing_cols:
                print(f"   ❌ Columnas faltantes: {missing_cols}")
                continue
            
            # Calcular indicadores para TODO el DataFrame
            print(f"   🔢 Calculando indicadores...")
            
            # Preparar datos para indicadores
            df_clean = df.dropna(subset=['open', 'high', 'low', 'close', 'volume'])
            
            if len(df_clean) < 50:  # Mínimo para indicadores
                print(f"   ⚠️ Datos insuficientes: {len(df_clean)} rows")
                continue
            
            # Calcular todos los indicadores
            try:
                indicators_result = indicators_calc.calculate_all_indicators(df_clean)
                
                # Extraer arrays de indicadores
                macd_data = indicators_result.get('macd', {})
                rsi_data = indicators_result.get('rsi', {})
                vwap_data = indicators_result.get('vwap', {})
                roc_data = indicators_result.get('roc', {})
                bb_data = indicators_result.get('bollinger', {})
                vol_data = indicators_result.get('volume_osc', {})
                atr_data = indicators_result.get('atr', {})
                
                # Insertar fila por fila usando los últimos valores de cada indicador
                inserted_count = 0
                
                # Los indicadores devuelven un dict con los valores más recientes
                # Usaremos estos valores para todas las filas (simplificado)
                
                for idx, row in df_clean.iterrows():
                    try:
                        # Usar valores de indicadores (últimos calculados)
                        macd_val = macd_data.get('macd', 0)
                        macd_sig = macd_data.get('signal', 0)
                        macd_hist = macd_data.get('histogram', 0)
                        
                        rsi_val = rsi_data.get('rsi', 50)
                        
                        vwap_val = vwap_data.get('vwap', row['close'])
                        vwap_dev = vwap_data.get('deviation_pct', 0)
                        
                        roc_val = roc_data.get('roc', 0)
                        
                        bb_upper = bb_data.get('upper_band', row['close'])
                        bb_middle = bb_data.get('middle_band', row['close'])
                        bb_lower = bb_data.get('lower_band', row['close'])
                        bb_pos = bb_data.get('bb_position', 0.5)
                        
                        vol_osc = vol_data.get('volume_oscillator', 0)
                        
                        atr_val = atr_data.get('atr', 0.01)
                        atr_pct = atr_data.get('atr_percentage', 1)
                        
                        # Determinar market regime
                        if abs(roc_val) > 2:
                            regime = "TRENDING"
                        elif abs(roc_val) < 0.5:
                            regime = "RANGING"
                        else:
                            regime = "TRANSITIONING"
                        
                        # Determinar volatility level
                        if atr_pct < 1:
                            vol_level = "LOW"
                        elif atr_pct < 2:
                            vol_level = "NORMAL"
                        elif atr_pct < 3:
                            vol_level = "HIGH"
                        else:
                            vol_level = "VERY_HIGH"
                        
                        # Insert into database
                        cursor.execute('''
                        INSERT INTO indicators_data (
                            timestamp, symbol, 
                            open_price, high_price, low_price, close_price, volume,
                            rsi_value, macd_line, macd_signal, macd_histogram,
                            vwap_value, vwap_deviation_pct, roc_value,
                            bb_upper, bb_middle, bb_lower, bb_position,
                            volume_oscillator, atr_value, atr_percentage,
                            market_regime, volatility_level
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', [
                            row['timestamp'].isoformat(),
                            symbol,
                            float(row['open']),
                            float(row['high']),
                            float(row['low']),
                            float(row['close']),
                            int(row['volume']),
                            float(rsi_val),
                            float(macd_val),
                            float(macd_sig),
                            float(macd_hist),
                            float(vwap_val),
                            float(vwap_dev),
                            float(roc_val),
                            float(bb_upper),
                            float(bb_middle),
                            float(bb_lower),
                            float(bb_pos),
                            float(vol_osc),
                            float(atr_val),
                            float(atr_pct),
                            regime,
                            vol_level
                        ])
                        
                        inserted_count += 1
                        
                    except Exception as e:
                        print(f"     ⚠️ Error en fila {idx}: {e}")
                        continue
                
                # Commit datos del archivo
                conn.commit()
                total_inserted += inserted_count
                print(f"   ✅ {symbol}: {inserted_count} registros insertados")
                
            except Exception as e:
                print(f"   ❌ Error calculando indicadores: {e}")
                continue
                
        except Exception as e:
            print(f"   ❌ Error procesando {csv_file}: {e}")
            continue
    
    conn.close()
    
    print(f"\n🎉 POBLACIÓN COMPLETADA")
    print(f"📊 Total registros insertados: {total_inserted}")
    
    # Verificar resultado final
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM indicators_data")
    final_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(DISTINCT symbol) FROM indicators_data")
    unique_symbols = cursor.fetchone()[0]
    
    cursor.execute("SELECT MIN(timestamp), MAX(timestamp) FROM indicators_data")
    date_range = cursor.fetchone()
    
    conn.close()
    
    print(f"✅ Verificación final:")
    print(f"   📊 Registros en BD: {final_count}")
    print(f"   📈 Símbolos únicos: {unique_symbols}")
    print(f"   📅 Rango: {date_range[0]} a {date_range[1]}")

if __name__ == "__main__":
    fix_populate_database()