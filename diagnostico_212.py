#!/usr/bin/env python3
"""
Script de diagnóstico para verificar la integración con Trading212.
"""
import os
import sys
import time
import pandas as pd
import numpy as np
from dotenv import load_dotenv

# Asegurar que podemos importar desde el directorio raíz
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from utils.logger import setup_logger, logger
from trading212 import integrator as trading212_integrator
import trading212
from market.data import get_yfinance_candles

def calculate_basic_indicators(df):
    """
    Calcula indicadores básicos para pruebas.
    
    Args:
        df: DataFrame con datos OHLCV
        
    Returns:
        DataFrame con indicadores calculados
    """
    # Versión simplificada para diagnóstico
    
    # Bandas de Bollinger
    window = 20
    std_dev = 2
    
    # Media móvil
    df['BB_MEDIA'] = df['Close'].rolling(window=window).mean()
    
    # Desviación estándar
    rolling_std = df['Close'].rolling(window=window).std()
    
    # Bandas superior e inferior
    df['BB_SUPERIOR'] = df['BB_MEDIA'] + (rolling_std * std_dev)
    df['BB_INFERIOR'] = df['BB_MEDIA'] - (rolling_std * std_dev)
    
    # MACD
    fast_period = 12
    slow_period = 26
    signal_period = 9
    
    # EMAs
    df['EMA_RAPIDA'] = df['Close'].ewm(span=fast_period, adjust=False).mean()
    df['EMA_LENTA'] = df['Close'].ewm(span=slow_period, adjust=False).mean()
    
    # MACD Line
    df['MACD'] = df['EMA_RAPIDA'] - df['EMA_LENTA']
    
    # Signal Line
    df['MACD_SIGNAL'] = df['MACD'].ewm(span=signal_period, adjust=False).mean()
    
    # Histogram
    df['MACD_HIST'] = df['MACD'] - df['MACD_SIGNAL']
    
    # RSI simplificado
    period = 14
    delta = df['Close'].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    
    rs = avg_gain / avg_loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    # RSI Estocástico simplificado
    df['RSI_K'] = 50  # Valor de ejemplo para pruebas
    df['RSI_D'] = 50  # Valor de ejemplo para pruebas
    
    return df

def get_test_data(symbol):
    """
    Obtiene datos de prueba para un símbolo y calcula los indicadores técnicos.
    
    Args:
        symbol: Símbolo de la acción
        
    Returns:
        DataFrame con datos e indicadores o None si hay error
    """
    try:
        print(f"Descargando datos para {symbol}...")
        # Usar la función get_yfinance_candles que está adaptada para este sistema
        df = get_yfinance_candles(symbol, period="1d", interval="5m")
        
        if df.empty:
            print(f"❌ No se pudieron obtener datos para {symbol}")
            return None
            
        print(f"✅ Datos obtenidos: {len(df)} registros")
        
        # Calcular indicadores básicos para diagnóstico
        print("Calculando indicadores técnicos básicos...")
        df = calculate_basic_indicators(df)
        print("✅ Indicadores calculados correctamente")
        
        return df
    except Exception as e:
        print(f"❌ Error al obtener datos: {e}")
        import traceback
        traceback.print_exc()
        return None

def test_trading212_integration():
    """
    Prueba la integración con Trading212.
    """
    print("\n" + "=" * 60)
    print("DIAGNÓSTICO DE INTEGRACIÓN CON TRADING212")
    print("=" * 60)
    
    # Cargar variables de entorno
    load_dotenv()
    
    # Obtener clave API
    api_key = os.getenv("TRADING212_API_KEY")
    api_url = os.getenv("TRADING212_API_URL", "https://demo.trading212.com")
    
    if not api_key:
        print("❌ No se ha configurado la clave API de Trading212")
        return False
    
    print(f"• API URL: {api_url}")
    print(f"• API Key: {'*' * 10}{api_key[-5:] if api_key else 'No configurada'}")
    
    # Paso 1: Inicializar integrador
    print("\n1. Inicializando integrador Trading212...")
    
    init_result = trading212_integrator.initialize(api_key=api_key)
    
    if init_result:
        print("✅ Integrador inicializado correctamente")
    else:
        print("❌ Error al inicializar integrador")
        return False
    
    # Paso 2: Habilitar integración
    print("\n2. Habilitando integración...")
    
    enable_result = trading212_integrator.enable_integration()
    
    if enable_result:
        print("✅ Integración habilitada correctamente")
    else:
        print("❌ Error al habilitar integración")
        return False
    
    # Paso 3: Verificar estado de integración
    print("\n3. Verificando estado de integración...")
    
    status = trading212_integrator.get_status()
    print(status)
    
    # Paso 4: Verificar proceso de alerta
    print("\n4. Probando procesamiento de alerta...")
    
    # Crear alerta de prueba
    symbol = "AAPL"
    
    # Obtener datos de ejemplo
    test_data = get_test_data(symbol)
    
    if test_data is not None:
        # Generar mensaje de alerta de prueba
        from trading212.utils import generate_test_alert_message
        
        print("Generando mensaje de alerta de prueba...")
        details = {"indice_bollinger": -1, "indice_rsi": -2, "indice_macd": -3}
        try:
            alert_message = generate_test_alert_message(symbol, test_data, details)
            print("Vista previa del mensaje:")
            print("----------------------------")
            preview = alert_message[:200] + "..." if len(alert_message) > 200 else alert_message
            print(preview)
            print("----------------------------")
            
            # Procesar alerta
            print(f"Procesando alerta de prueba para {symbol}...")
            result = trading212_integrator.process_alert(symbol, alert_message)
            
            if result:
                print("✅ Alerta procesada correctamente")
            else:
                print("❌ Error al procesar alerta")
        except Exception as e:
            print(f"❌ Error al generar o procesar alerta: {e}")
            import traceback
            traceback.print_exc()
    else:
        print("❌ No se pudo realizar la prueba de alerta por falta de datos")
    
    # Paso 5: Detener procesos
    print("\n5. Deteniendo procesos...")
    
    stop_result = trading212_integrator.stop_all_processes()
    
    if stop_result:
        print("✅ Procesos detenidos correctamente")
    else:
        print("❌ Error al detener procesos")
    
    print("\n" + "=" * 60)
    print("DIAGNÓSTICO COMPLETADO")
    print("=" * 60)
    
    return True

if __name__ == "__main__":
    # Nombre de este archivo
    script_name = os.path.basename(__file__)
    print(f"Ejecutando {script_name}...")
    
    test_trading212_integration()