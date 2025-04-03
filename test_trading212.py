#!/usr/bin/env python3
"""
Script de prueba para verificar la integración del sistema de alertas con Trading212.
"""
import os
import sys
import time
import argparse
import datetime

# Asegurar que podemos importar desde el directorio raíz
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from utils.logger import setup_logger
from market.data import get_yfinance_candles
from indicators.bollinger import calculate_bollinger
from indicators.macd import calculate_macd
from indicators.rsi import calculate_stochastic_rsi
from trading212.utils import generate_test_alert_message
from analysis.detector import detect_signal_sequence
from trading212 import integrator as trading212_integrator

# Configurar logger
logger = setup_logger()

def simulate_alert(symbol):
    """
    Simula una alerta para un símbolo específico.
    
    Args:
        symbol: Símbolo para el que se generará la alerta
        
    Returns:
        (bool, str): Tupla con (alerta_generada, mensaje_alerta)
    """
    # Obtener datos para el símbolo
    data = get_yfinance_candles(symbol, period="5d", interval="5m")
    
    if data.empty:
        print(f"❌ No se pudieron obtener datos para {symbol}")
        return False, ""
    
    print(f"✅ Obtenidos {len(data)} registros para {symbol}")
    
    # Calcular indicadores
    data = calculate_bollinger(data)
    data = calculate_macd(data)
    data = calculate_stochastic_rsi(data)
    
    # Detectar secuencia de señales
    sequence_detected, details = detect_signal_sequence(data)
    
    if sequence_detected:
        print(f"🔔 SEÑAL DETECTADA para {symbol}")
        print(f"  - Índice Bollinger: {details['indice_bollinger']}")
        print(f"  - Índice RSI: {details['indice_rsi']}")
        print(f"  - Índice MACD: {details['indice_macd']}")
        
        # Generar mensaje de alerta
        message = generate_test_alert_message(symbol, data, details)
        return True, message
    else:
        # Si no se detectó señal real, simular una
        print(f"ℹ️ No se detectó señal real para {symbol}, simulando alerta...")
        
        # Crear detalles sintéticos para una alerta simulada
        synthetic_details = {
            "secuencia_ok": True,
            "indice_bollinger": -5,  # 5 períodos atrás
            "indice_rsi": -4,         # 4 períodos atrás
            "indice_macd": -3,        # 3 períodos atrás
            "distancia_bollinger_rsi": 1,
            "ventana_total": 2,
            "velas_para_cruce": 1.5
        }
        
        # Generar mensaje de alerta sintético
        message = generate_test_alert_message(symbol, data, synthetic_details)
        return True, message
        
def test_trading212_integration(symbol, simulation_mode=True):
    """
    Prueba la integración con Trading212.
    
    Args:
        symbol: Símbolo para probar
        simulation_mode: Usar modo simulación (default: True)
        
    Returns:
        bool: True si la prueba fue exitosa
    """
    print("\n" + "=" * 60)
    print(f"PRUEBA DE INTEGRACIÓN CON TRADING212 PARA {symbol}")
    print("=" * 60)
    
    # Inicializar Trading212
    print("\nInicializando Trading212...")
    result = trading212_integrator.initialize(simulation_mode=simulation_mode)
    
    if not result:
        print("❌ Error al inicializar Trading212")
        return False
    
    print("✅ Trading212 inicializado correctamente")
    
    # Habilitar integración
    trading212_integrator.enable_integration()
    print("✅ Integración habilitada")
    
    # Simular alerta
    print(f"\nSimulando alerta para {symbol}...")
    alert_generated, alert_message = simulate_alert(symbol)
    
    if not alert_generated:
        print("❌ No se pudo generar alerta simulada")
        return False
    
    print(f"✅ Alerta simulada generada para {symbol}")
    
    # Procesar alerta
    print(f"\nProcesando alerta con Trading212...")
    processing_result = trading212_integrator.process_alert(symbol, alert_message)
    
    if not processing_result:
        print("❌ Error al procesar alerta con Trading212")
        return False
    
    print("✅ Alerta procesada correctamente por Trading212")
    
    # Mostrar estado inicial
    print("\nEstado inicial:")
    initial_status = trading212_integrator.get_status()
    print(initial_status)
    
    # Esperar a que se procese la alerta
    print("\nEsperando a que se procese la alerta (20 segundos)...")
    time.sleep(20)
    
    # Mostrar estado intermedio
    print("\nEstado intermedio:")
    mid_status = trading212_integrator.get_status()
    print(mid_status)
    
    # Preguntar si se desea esperar más tiempo
    wait_more = input("\n¿Desea esperar más tiempo para ver el proceso completo? (s/n): ").lower()
    
    if wait_more == 's':
        wait_minutes = 5
        print(f"\nEsperando {wait_minutes} minutos adicionales...")
        for i in range(wait_minutes):
            time.sleep(60)
            print(f"Transcurridos {i+1} de {wait_minutes} minutos...")
    
    # Mostrar estado final
    print("\nEstado final:")
    final_status = trading212_integrator.get_status()
    print(final_status)
    
    # Detener todos los procesos
    print("\nDeteniendo todos los procesos...")
    trading212_integrator.stop_all_processes()
    print("✅ Todos los procesos detenidos")
    
    return True

def test_trading212_alert_monitoring(symbol, simulation_mode=True):
    """
    Prueba específicamente el monitoreo posterior a una alerta sin ejecutar operaciones.
    
    Args:
        symbol: Símbolo para probar
        simulation_mode: Usar modo simulación (default: True)
        
    Returns:
        bool: True si la prueba fue exitosa
    """
    print("\n" + "=" * 60)
    print(f"PRUEBA DE MONITOREO POST-ALERTA PARA {symbol}")
    print("=" * 60)
    
    # Inicializar Trading212
    print("\nInicializando Trading212...")
    result = trading212_integrator.initialize(simulation_mode=simulation_mode)
    
    if not result:
        print("❌ Error al inicializar Trading212")
        return False
    
    print("✅ Trading212 inicializado correctamente")
    
    # Habilitar integración
    trading212_integrator.enable_integration()
    print("✅ Integración habilitada")
    
    # Simular alerta
    print(f"\nSimulando alerta para {symbol}...")
    alert_generated, alert_message = simulate_alert(symbol)
    
    if not alert_generated:
        print("❌ No se pudo generar alerta simulada")
        return False
    
    print(f"✅ Alerta simulada generada para {symbol}")
    
    # Procesar alerta
    print(f"\nProcesando alerta con Trading212...")
    processing_result = trading212_integrator.process_alert(symbol, alert_message)
    
    if not processing_result:
        print("❌ Error al procesar alerta con Trading212")
        return False
    
    print("✅ Alerta procesada correctamente por Trading212")
    
    # Monitorear proceso
    monitor_duration = 20  # minutos
    print(f"\nMonitoreando proceso durante {monitor_duration} minutos...")
    
    for i in range(monitor_duration):
        time.sleep(60)  # Esperar 1 minuto
        print(f"\nEstado después de {i+1} minutos:")
        status = trading212_integrator.get_status()
        print(status)
        
        # Preguntar si se desea detener el monitoreo antes de tiempo
        if (i+1) % 5 == 0 and i < monitor_duration - 1:  # Cada 5 minutos
            stop_early = input("\n¿Desea detener el monitoreo ahora? (s/n): ").lower()
            if stop_early == 's':
                break
    
    # Detener todos los procesos
    print("\nDeteniendo todos los procesos...")
    trading212_integrator.stop_all_processes()
    print("✅ Todos los procesos detenidos")
    
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Prueba de integración con Trading212')
    
    parser.add_argument('--symbol', type=str, default='AAPL', help='Símbolo a usar para la prueba')
    parser.add_argument('--real', action='store_true', help='Usar modo real (por defecto: simulación)')
    parser.add_argument('--monitor', action='store_true', help='Realizar prueba de monitoreo extendido')
    
    args = parser.parse_args()
    
    # Crear directorio de datos si no existe
    os.makedirs("data", exist_ok=True)
    
    # Ejecutar la prueba correspondiente
    if args.monitor:
        test_trading212_alert_monitoring(args.symbol, not args.real)
    else:
        test_trading212_integration(args.symbol, not args.real)