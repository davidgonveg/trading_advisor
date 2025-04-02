#!/usr/bin/env python3
"""
Script para probar que los datos obtenidos con yfinance se guardan correctamente en la base de datos.
"""
import os
import sys
import pandas as pd
import sqlite3
import datetime

# Asegurar que podemos importar desde el directorio raíz
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from market.data import get_yfinance_candles
from indicators.bollinger import calculate_bollinger
from indicators.macd import calculate_macd
from indicators.rsi import calculate_stochastic_rsi
from database.connection import create_connection, create_tables
from database.operations import save_historical_data, get_last_data_from_db
from utils.logger import setup_logger

# Configurar logger
logger = setup_logger()

def test_database_storage():
    """
    Prueba el proceso completo: 
    1. Obtener datos de yfinance
    2. Calcular indicadores
    3. Guardar en base de datos
    4. Recuperar de la base de datos
    """
    print("\n=== PRUEBA DE ALMACENAMIENTO EN BASE DE DATOS ===")
    
    # Definir ruta de base de datos de prueba
    test_db_path = "data/test_stock_alerts.db"
    
    # Eliminar la base de datos de prueba si ya existe
    if os.path.exists(test_db_path):
        print(f"Eliminando base de datos de prueba anterior: {test_db_path}")
        os.remove(test_db_path)
    
    # Crear conexión a la base de datos
    print("Creando conexión a la base de datos...")
    connection = create_connection(test_db_path)
    
    if not connection:
        print("❌ No se pudo crear la conexión a la base de datos.")
        return False
    
    # Crear tablas
    print("Creando tablas en la base de datos...")
    create_tables(connection)
    
    # Obtener datos para un símbolo
    symbol = "MSFT"
    print(f"\nObteniendo datos para {symbol}...")
    data = get_yfinance_candles(symbol, period="2d", interval="15m")
    
    if data.empty:
        print(f"❌ No se pudieron obtener datos para {symbol}")
        connection.close()
        return False
    
    print(f"✅ Obtenidos {len(data)} registros para {symbol}")
    
    # Calcular indicadores
    print("\nCalculando indicadores técnicos...")
    data = calculate_bollinger(data)
    data = calculate_macd(data)
    data = calculate_stochastic_rsi(data)
    
    print("✅ Indicadores calculados")
    
    # Guardar en la base de datos
    print("\nGuardando datos en la base de datos...")
    success = save_historical_data(connection, symbol, data)
    
    if not success:
        print("❌ Error al guardar datos históricos en la base de datos")
        connection.close()
        return False
    
    print("✅ Datos guardados correctamente")
    
    # Consultar la base de datos para verificar que se guardaron correctamente
    print("\nConsultando datos de la base de datos...")
    # Usar función del sistema para obtener datos
    db_data = get_last_data_from_db(connection, symbol)
    
    if db_data is None or db_data.empty:
        print("❌ No se pudieron recuperar datos de la base de datos")
        connection.close()
        return False
    
    print(f"✅ Recuperados {len(db_data)} registros de la base de datos")
    
    # Verificar que todos los campos necesarios están presentes
    print("\nVerificando campos en los datos recuperados:")
    required_fields = ['Open', 'High', 'Low', 'Close', 'Volume', 
                      'BB_MEDIA', 'BB_SUPERIOR', 'BB_INFERIOR',
                      'MACD', 'MACD_SIGNAL', 'MACD_HIST',
                      'RSI', 'RSI_K', 'RSI_D']
    
    missing_fields = []
    for field in required_fields:
        if field not in db_data.columns:
            missing_fields.append(field)
            print(f"  - ❌ Campo faltante: {field}")
        else:
            print(f"  - ✅ Campo presente: {field}")
    
    if missing_fields:
        print(f"\n❌ Faltan {len(missing_fields)} campos en los datos recuperados")
    else:
        print("\n✅ Todos los campos necesarios están presentes")
    
    # Verificar la cantidad de registros
    if len(db_data) != len(data):
        print(f"⚠️ Número de registros diferentes: Original: {len(data)}, BD: {len(db_data)}")
    else:
        print(f"✅ Número de registros coincide: {len(data)}")
    
    # Examinar directamente la base de datos con SQL para verificación adicional
    print("\nRealizando consulta SQL directa a la base de datos:")
    cursor = connection.cursor()
    cursor.execute("SELECT COUNT(*) FROM datos_historicos WHERE simbolo = ?", (symbol,))
    count = cursor.fetchone()[0]
    print(f"  - Registros en tabla datos_historicos para {symbol}: {count}")
    
    # Obtener la primera y última fecha
    cursor.execute("SELECT MIN(fecha_hora), MAX(fecha_hora) FROM datos_historicos WHERE simbolo = ?", (symbol,))
    min_date, max_date = cursor.fetchone()
    print(f"  - Rango de fechas: {min_date} a {max_date}")
    
    # Muestra algunos registros específicos
    print("\nMuestra de registros en la base de datos:")
    cursor.execute("""
    SELECT fecha_hora, precio_close, bb_media, macd, rsi_k 
    FROM datos_historicos 
    WHERE simbolo = ? 
    ORDER BY fecha_hora DESC 
    LIMIT 3
    """, (symbol,))
    
    records = cursor.fetchall()
    for record in records:
        fecha, precio, bb, macd, rsi = record
        print(f"  - {fecha}: Precio=${precio:.2f}, BB_Media=${bb:.2f}, MACD={macd:.4f}, RSI_K={rsi:.2f}")
    
    # Cerrar conexión
    connection.close()
    
    # Mostrar tamaño de la base de datos
    db_size = os.path.getsize(test_db_path) / 1024  # Tamaño en KB
    print(f"\nTamaño de la base de datos: {db_size:.2f} KB")
    
    # Limpiar
    print("\n¿Desea conservar la base de datos de prueba? (s/n): ", end="")
    keep_db = input().strip().lower()
    if keep_db != 's':
        os.remove(test_db_path)
        print(f"Base de datos de prueba eliminada: {test_db_path}")
    else:
        print(f"Base de datos de prueba conservada en: {test_db_path}")
    
    return True

if __name__ == "__main__":
    # Crear directorio de datos si no existe
    os.makedirs("data", exist_ok=True)
    
    print("=" * 60)
    print("PRUEBA DE INTEGRACIÓN CON BASE DE DATOS")
    print("=" * 60)
    
    success = test_database_storage()
    
    print("\n" + "=" * 60)
    if success:
        print("✅ PRUEBA EXITOSA: El almacenamiento en base de datos funciona correctamente.")
    else:
        print("❌ PRUEBA FALLIDA: Revisa los errores anteriores.")
    print("=" * 60)