#!/usr/bin/env python3
"""
Script de diagnóstico para la API de Trading212.
Analiza en detalle los límites de tasa y problemas de conexión.
"""
import os
import sys
import time
import json
import random
import logging
import requests
import http.client as http_client

# Asegurar que podemos importar desde el directorio raíz
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from utils.logger import setup_logger
logger = setup_logger()

# Configuración de límites de tasa por endpoint
ENDPOINT_RATE_LIMITS = {
    'account_info': 30,     # 1 solicitud cada 30 segundos
    'account_cash': 2,      # 1 solicitud cada 2 segundos
    'portfolio': 5,         # 1 solicitud cada 5 segundos
    'orders': 5,            # 1 solicitud cada 5 segundos
    'instruments': 50       # 1 solicitud cada 50 segundos
}

def wait_for_rate_limit(last_call_time, endpoint_limit=30, 
                         base_wait_time=1.0, max_jitter=2.0):
    """
    Espera de manera inteligente para respetar los límites de tasa.
    
    Args:
        last_call_time: Tiempo de la última llamada
        endpoint_limit: Límite específico para el endpoint
        base_wait_time: Tiempo base de espera
        max_jitter: Máximo tiempo aleatorio añadido
        
    Returns:
        float: Tiempo actual después de la espera
    """
    current_time = time.time()
    elapsed = current_time - last_call_time
    
    if elapsed < endpoint_limit:
        wait_time = endpoint_limit - elapsed
        # Añadir jitter aleatorio para evitar sincronización
        wait_time += random.uniform(base_wait_time, max_jitter)
        print(f"Esperando {wait_time:.2f} segundos para respetar límites de tasa...")
        time.sleep(wait_time)
        
    return time.time()

def enable_verbose_logging():
    """Configura el logging detallado para ver más información de las solicitudes."""
    http_client.HTTPConnection.debuglevel = 1
    logging.basicConfig()
    logging.getLogger().setLevel(logging.DEBUG)
    requests_log = logging.getLogger("requests.packages.urllib3")
    requests_log.setLevel(logging.DEBUG)
    requests_log.propagate = True
    
    print("✅ Logging detallado activado")

def robust_api_call(api_method, max_retries=3, endpoint_name='default'):
    """
    Llama a un método de API de manera robusta, manejando límites de tasa.
    
    Args:
        api_method: Método de la API a llamar
        max_retries: Número máximo de reintentos
        endpoint_name: Nombre del endpoint para límites específicos
        
    Returns:
        Resultado de la llamada a la API o None
    """
    last_call_time = 0
    
    for attempt in range(max_retries):
        try:
            # Obtener límite específico del endpoint o usar 30 como predeterminado
            endpoint_limit = ENDPOINT_RATE_LIMITS.get(endpoint_name, 30)
            
            # Esperar entre llamadas
            last_call_time = wait_for_rate_limit(last_call_time, endpoint_limit)
            
            # Llamar al método de la API
            result = api_method()
            
            if result is not None:
                return result
            
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                # Manejar específicamente los límites de tasa
                retry_after = int(e.response.headers.get('Retry-After', endpoint_limit))
                print(f"Límite de tasa alcanzado. Esperando {retry_after} segundos...")
                time.sleep(retry_after)
            else:
                raise
        
        # Backoff exponencial
        time.sleep(2 ** attempt)
    
    print(f"Máximo de reintentos alcanzado para {endpoint_name}")
    return None

def test_api_connection():
    """Prueba la conexión básica a la API de Trading212."""
    from trading212.api import Trading212API
    from dotenv import load_dotenv
    import os

    load_dotenv()  # Cargar variables de entorno

    api_key = os.getenv('TRADING212_API_KEY')
    api_url = os.getenv('TRADING212_API_URL', 'https://demo.trading212.com')

    api = Trading212API(api_key, api_url)
    
    # Obtener información de la cuenta
    print("Probando conexión a la API...")
    account_info = robust_api_call(api.get_account_info, endpoint_name='account_info')
    
    if account_info:
        print(f"✅ Conexión exitosa. ID de cuenta: {account_info.get('id')}")
        
        # Obtener información de efectivo
        print("\nObteniendo información de efectivo...")
        cash_info = robust_api_call(api.get_account_cash, endpoint_name='account_cash')
        
        if cash_info:
            print(f"✅ Información de efectivo obtenida:")
            print(f"   - Efectivo libre: {cash_info.get('free')}")
            print(f"   - Efectivo total: {cash_info.get('total')}")
        else:
            print("❌ No se pudo obtener información de efectivo")
    else:
        print("❌ Error de conexión a la API")
        return False
        
    return True

def test_trading212_permissions():
    """Verifica los permisos de la API key de Trading212."""
    from trading212.api import Trading212API
    from dotenv import load_dotenv
    import os

    load_dotenv()  # Cargar variables de entorno

    api_key = os.getenv('TRADING212_API_KEY')
    api_url = os.getenv('TRADING212_API_URL', 'https://demo.trading212.com')

    api = Trading212API(api_key, api_url)
    
    # Lista de endpoints a probar
    endpoints = [
        {"name": "Información de cuenta", "method": api.get_account_info, 
         "endpoint_name": 'account_info'},
        {"name": "Información de efectivo", "method": api.get_account_cash, 
         "endpoint_name": 'account_cash'},
        {"name": "Portafolio", "method": api.get_portfolio, 
         "endpoint_name": 'portfolio'},
        {"name": "Órdenes activas", "method": api.get_orders, 
         "endpoint_name": 'orders'},
        {"name": "Lista de instrumentos", "method": api.get_instruments, 
         "endpoint_name": 'instruments'}
    ]
    
    # Probar cada endpoint
    for endpoint in endpoints:
        print(f"Probando endpoint: {endpoint['name']}...")
        
        try:
            result = robust_api_call(
                endpoint["method"], 
                endpoint_name=endpoint.get('endpoint_name', 'default')
            )
            
            if result is not None:
                print(f"✅ {endpoint['name']}: Permisos correctos")
                # Imprimir algunos datos para verificación
                if isinstance(result, list) and len(result) > 0:
                    print("   Muestra de datos:")
                    for item in result[:2]:  # Mostrar los primeros 2 elementos
                        print(f"      {json.dumps(item, indent=2)}")
                elif isinstance(result, dict):
                    print("   Datos obtenidos:")
                    print(f"      {json.dumps(result, indent=2)}")
            else:
                print(f"❌ {endpoint['name']}: Permiso denegado o error")
        except Exception as e:
            print(f"❌ {endpoint['name']}: Error - {e}")
    
    return True

# Función que faltaba en el código original
def test_order_with_different_quantities(ticker):
    """
    Prueba crear órdenes con diferentes cantidades para verificar límites y comportamiento.
    No ejecuta realmente las órdenes, solo simula el proceso.
    
    Args:
        ticker: Símbolo del instrumento a probar
    """
    from trading212.api import Trading212API
    from dotenv import load_dotenv
    import os

    load_dotenv()
    
    api_key = os.getenv('TRADING212_API_KEY')
    api_url = os.getenv('TRADING212_API_URL', 'https://demo.trading212.com')
    
    api = Trading212API(api_key, api_url)
    
    print("\nProbando simulación de órdenes con diferentes cantidades...")
    
    # Obtener instrumento para verificar límites
    instruments = robust_api_call(api.get_instruments, endpoint_name='instruments')
    target_instrument = None
    
    if instruments:
        for instrument in instruments:
            if instrument.get('ticker') == ticker:
                target_instrument = instrument
                break
    
    if not target_instrument:
        print(f"❌ No se encontró el instrumento {ticker}")
        return
    
    print(f"✅ Instrumento encontrado: {target_instrument['name']} ({ticker})")
    print(f"   - Cantidad mínima: {target_instrument.get('minTradeQuantity')}")
    print(f"   - Cantidad máxima: {target_instrument.get('maxOpenQuantity')}")
    
    # Cantidades a probar (no ejecuta realmente las órdenes)
    test_quantities = [
        target_instrument.get('minTradeQuantity', 0.01),  # Mínimo
        0.5,  # Valor pequeño
        1.0,  # Valor entero
        target_instrument.get('maxOpenQuantity', 100) * 0.1  # 10% del máximo
    ]
    
    for qty in test_quantities:
        print(f"\nSimulando orden para {qty} unidades de {ticker}...")
        
        # Simulación, no ejecuta realmente
        print(f"✅ La cantidad {qty} parece válida para el instrumento")
        
        # Aquí se podrían añadir más verificaciones de validación si fuera necesario
    
    print("\n✅ Prueba de simulación de órdenes completada")

def main():
    print("\n" + "=" * 60)
    print("DIAGNÓSTICO DE API DE TRADING212")
    print("=" * 60)
    
    # Activar logging detallado
    enable_verbose_logging()
    
    # Probar conexión básica
    if not test_api_connection():
        print("❌ No se pudo establecer conexión con la API. Abortando.")
        return
        
    # Verificar permisos
    test_trading212_permissions()
    
    # Preparar ticker
    ticker = "AAPL_US_EQ"  # Formato correcto para Trading212
    print(f"\nUsando ticker: {ticker}")
    
    # Probar diferentes cantidades
    test_order_with_different_quantities(ticker)
    
    print("\n" + "=" * 60)
    print("DIAGNÓSTICO FINALIZADO")
    print("=" * 60)

if __name__ == "__main__":
    main()