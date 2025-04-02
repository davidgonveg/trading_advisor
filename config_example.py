#!/usr/bin/env python3
"""
Script de prueba para verificar la integración con yfinance después de la corrección.
"""
import os
import sys
import pandas as pd
import numpy as np

# Asegurar que podemos importar desde el directorio raíz
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from market.data import get_yfinance_candles
from indicators.bollinger import calculate_bollinger
from indicators.macd import calculate_macd
from indicators.rsi import calculate_stochastic_rsi

def test_data_format():
    """
    Verifica el formato de datos devuelto por yfinance y prueba los cálculos de indicadores.
    """
    print("\n=== PRUEBA DE FORMATO DE DATOS ===")
    symbol = "AAPL"
    
    # Obtener datos de yfinance
    print(f"Obteniendo datos para {symbol}...")
    data = get_yfinance_candles(symbol, period="5d", interval="5m")
    
    if data.empty:
        print("❌ No se pudieron obtener datos.")
        return False
    
    print(f"✅ Se obtuvieron {len(data)} registros.")
    
    # Mostrar estructura de las columnas
    print("\nEstructura de las columnas:")
    print(f"Tipo de columnas: {type(data.columns)}")
    print(f"Columnas: {list(data.columns)}")
    
    # Mostrar primeras filas para verificar formato
    print("\nPrimeras 2 filas de datos:")
    print(data.head(2))
    
    # Probar cálculo de Bollinger
    print("\nCalculando Bandas de Bollinger...")
    try:
        data_with_bollinger = calculate_bollinger(data)
        print("✅ Bandas de Bollinger calculadas correctamente.")
        
        # Verificar columnas creadas
        bb_columns = ['BB_MEDIA', 'BB_SUPERIOR', 'BB_INFERIOR']
        for col in bb_columns:
            if col in data_with_bollinger.columns:
                print(f"  - {col}: OK")
                # Mostrar algunos valores para verificación
                print(f"    Valores muestra: {data_with_bollinger[col].iloc[10:13].values}")
            else:
                print(f"  - ❌ {col} falta")
                
        # Probar MACD
        print("\nCalculando MACD...")
        data_with_macd = calculate_macd(data_with_bollinger)
        print("✅ MACD calculado correctamente.")
        
        # Verificar columnas creadas
        macd_columns = ['MACD', 'MACD_SIGNAL', 'MACD_HIST']
        for col in macd_columns:
            if col in data_with_macd.columns:
                print(f"  - {col}: OK")
            else:
                print(f"  - ❌ {col} falta")
        
        # Probar RSI
        print("\nCalculando RSI Estocástico...")
        full_data = calculate_stochastic_rsi(data_with_macd)
        print("✅ RSI Estocástico calculado correctamente.")
        
        # Verificar columnas creadas
        rsi_columns = ['RSI', 'RSI_K', 'RSI_D']
        for col in rsi_columns:
            if col in full_data.columns:
                print(f"  - {col}: OK")
            else:
                print(f"  - ❌ {col} falta")
        
        # Guardar el DataFrame completo para referencia
        output_file = "data/test_indicators_output.csv"
        full_data.to_csv(output_file)
        print(f"\n✅ Datos con indicadores guardados en {output_file}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error durante los cálculos: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    # Crear directorio de datos si no existe
    os.makedirs("data", exist_ok=True)
    
    print("=" * 60)
    print("PRUEBA DE INTEGRACIÓN YFINANCE - FORMATO DE DATOS")
    print("=" * 60)
    
    success = test_data_format()
    
    print("\n" + "=" * 60)
    if success:
        print("✅ PRUEBA EXITOSA: El formato de datos y los cálculos de indicadores funcionan correctamente.")
    else:
        print("❌ PRUEBA FALLIDA: Revisa los errores anteriores.")
    print("=" * 60)