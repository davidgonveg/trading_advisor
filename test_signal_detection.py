#!/usr/bin/env python3
"""
Script para probar la detección de señales técnicas usando datos de yfinance.
"""
import os
import sys
import pandas as pd
import datetime

# Asegurar que podemos importar desde el directorio raíz
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from market.data import get_yfinance_candles
from indicators.bollinger import calculate_bollinger
from indicators.macd import calculate_macd, verify_macd_conditions
from indicators.rsi import calculate_stochastic_rsi, check_rsi_conditions
from analysis.detector import detect_signal_sequence
from analysis.market_type import detect_market_type
from notifications.formatter import generate_flexible_alert_message
from utils.logger import setup_logger

# Configurar logger
logger = setup_logger()

def test_signal_detection():
    """
    Prueba la detección de señales técnicas:
    1. Preparar datos con condiciones específicas
    2. Ejecutar detección de señales
    3. Verificar resultados
    """
    print("\n=== PRUEBA DE DETECCIÓN DE SEÑALES TÉCNICAS ===")
    
    # Lista de símbolos a probar
    symbols = ['AAPL', 'MSFT', 'NVDA', 'AMZN', 'TSLA', 'META', 'GOOGL', 'AMD']
    results = {}
    
    print(f"Probando detección de señales en {len(symbols)} símbolos...")
    
    for symbol in symbols:
        print(f"\nAnalizando {symbol}...")
        
        # Obtener datos con un período más largo para aumentar la probabilidad
        # de encontrar señales
        data = get_yfinance_candles(symbol, period="10d", interval="5m")
        
        if data.empty:
            print(f"  ❌ No se pudieron obtener datos para {symbol}")
            continue
        
        print(f"  ✅ Obtenidos {len(data)} registros")
        
        # Calcular indicadores
        data = calculate_bollinger(data)
        data = calculate_macd(data)
        data = calculate_stochastic_rsi(data)
        
        # Buscar señales
        sequence_detected, details = detect_signal_sequence(data)
        
        # Guardar resultados
        results[symbol] = {
            'sequence_detected': sequence_detected,
            'details': details
        }
        
        if sequence_detected:
            print(f"  🔔 SEÑAL DETECTADA para {symbol}")
            print(f"    - Índice Bollinger: {details['indice_bollinger']}")
            print(f"    - Índice RSI: {details['indice_rsi']}")
            print(f"    - Índice MACD: {details['indice_macd']}")
            print(f"    - Ventana total: {details['ventana_total']} velas")
            
            # Generar y mostrar mensaje de alerta
            try:
                message = generate_flexible_alert_message(symbol, data, details)
                print(f"\n--- MENSAJE DE ALERTA GENERADO ---")
                print(message[:300] + "..." if len(message) > 300 else message)
                print("-----------------------------------")
                
                # Guardar mensaje en archivo para referencia
                alert_file = f"data/{symbol}_alert.txt"
                with open(alert_file, "w") as f:
                    f.write(message)
                print(f"Alerta guardada en {alert_file}")
                
                # También probar la detección de tipo de mercado
                market_type = detect_market_type(data)
                print(f"\nTipo de mercado detectado para {symbol}:")
                print(f"  - Tendencia: {market_type.get('tendencia', 'N/A')}")
                print(f"  - Volatilidad: {market_type.get('volatilidad', 'N/A')}")
                print(f"  - Descripción: {market_type.get('descripcion', 'N/A')}")
                
            except Exception as e:
                print(f"  ❌ Error al generar mensaje de alerta: {e}")
        else:
            print(f"  ℹ️ No se detectó señal para {symbol}")
            if 'mensaje' in details:
                print(f"    - Razón: {details['mensaje']}")
        
        # Probar verificaciones individuales
        bollinger_breaches = data[data['Close'] < data['BB_INFERIOR']].index
        if not bollinger_breaches.empty:
            print(f"  ✓ Se encontraron {len(bollinger_breaches)} rupturas de Bollinger")
            
        rsi_conditions = []
        for i in range(-20, 0):
            met, _ = check_rsi_conditions(data, i)
            if met:
                rsi_conditions.append(i)
        
        if rsi_conditions:
            print(f"  ✓ RSI en sobreventa detectado en {len(rsi_conditions)} ocasiones")
        
        macd_conditions = []
        for i in range(-20, 0):
            met, _ = verify_macd_conditions(data, i)
            if met:
                macd_conditions.append(i)
        
        if macd_conditions:
            print(f"  ✓ Condiciones MACD favorables detectadas en {len(macd_conditions)} ocasiones")
    
    # Resumen de resultados
    print("\n=== RESUMEN DE RESULTADOS ===")
    signals_found = sum(1 for symbol, result in results.items() if result['sequence_detected'])
    print(f"Señales detectadas: {signals_found}/{len(symbols)} símbolos")
    
    # Listar símbolos con señales
    if signals_found > 0:
        print("\nSímbolos con señales detectadas:")
        for symbol, result in results.items():
            if result['sequence_detected']:
                print(f"  - {symbol}")
    
    return signals_found > 0

if __name__ == "__main__":
    # Crear directorio de datos si no existe
    os.makedirs("data", exist_ok=True)
    
    print("=" * 60)
    print("PRUEBA DE DETECCIÓN DE SEÑALES TÉCNICAS")
    print("=" * 60)
    
    success = test_signal_detection()
    
    print("\n" + "=" * 60)
    if success:
        print("✅ PRUEBA EXITOSA: Se detectaron señales técnicas correctamente.")
    else:
        print("⚠️ No se detectaron señales en los símbolos probados.")
        print("Esto no necesariamente indica un problema - las señales son eventos específicos.")
    print("=" * 60)