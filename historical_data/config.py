#!/usr/bin/env python3
"""
⚙️ CONFIGURACIÓN SIMPLE - DATOS HISTÓRICOS V4.0
============================================

Configuración minimalista para descarga histórica y backtesting.
Compatible con sistema principal, multi-API para rate limits.
"""

import os
import sys
from datetime import datetime, timedelta
from typing import List, Dict
from dotenv import load_dotenv

# Cargar .env desde directorio padre
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(parent_dir, '.env'))

# Agregar directorio padre al path para importar config principal si es necesario
sys.path.insert(0, parent_dir)

# =============================================================================
# 🔑 CONFIGURACIÓN DE APIs
# =============================================================================

# API Keys desde .env
API_KEYS = {
    'ALPHA_VANTAGE': os.getenv('ALPHA_VANTAGE_API_KEY'),
    'TWELVE_DATA': os.getenv('TWELVE_DATA_API_KEY'), 
    'POLYGON': os.getenv('POLYGON_API_KEY'),
}

# URLs base de las APIs
API_ENDPOINTS = {
    'YAHOO': 'https://query1.finance.yahoo.com/v8/finance/chart/',
    'ALPHA_VANTAGE': 'https://www.alphavantage.co/query',
    'TWELVE_DATA': 'https://api.twelvedata.com/time_series',
    'POLYGON': 'https://api.polygon.io/v2/aggs/ticker/'
}

# Rate limits (segundos entre requests) - Conservadores para evitar problemas
RATE_LIMITS = {
    'YAHOO': 1.0,           # 1 seg (sin límite oficial pero conservador)
    'ALPHA_VANTAGE': 13.0,  # 13 seg = ~5 requests/min (respeta 500/día)
    'TWELVE_DATA': 2.0,     # 2 seg = 30 requests/min (respeta 800/día)
    'POLYGON': 15.0,        # 15 seg = 4 requests/min (respeta 100/día)
}

# Límites diarios de requests
DAILY_LIMITS = {
    'YAHOO': 10000,         # Sin límite oficial, ponemos alto
    'ALPHA_VANTAGE': 500,   # Plan gratuito
    'TWELVE_DATA': 800,     # Plan gratuito
    'POLYGON': 100,         # Plan gratuito
}

# Prioridad de APIs (Yahoo primero porque no tiene límites estrictos)
API_PRIORITY = ['YAHOO', 'TWELVE_DATA', 'ALPHA_VANTAGE', 'POLYGON']

# =============================================================================
# 📊 CONFIGURACIÓN DE SÍMBOLOS Y DATOS
# =============================================================================

# Símbolos principales para descarga histórica
# Importar desde config principal si está disponible, sino usar estos
try:
    import config as main_config
    SYMBOLS = getattr(main_config, 'SYMBOLS', [
        'AAPL', 'MSFT', 'GOOGL', 'NVDA', 'TSLA', 
        'META', 'AMZN', 'NFLX', 'CRM', 'ADBE'
    ])
except ImportError:
    SYMBOLS = [
        'AAPL', 'MSFT', 'GOOGL', 'NVDA', 'TSLA', 
        'META', 'AMZN', 'NFLX', 'CRM', 'ADBE'
    ]

# Timeframes disponibles
TIMEFRAMES = ['1d', '1h', '15m']

# Período histórico por defecto
HISTORICAL_MONTHS = 6  # 6 meses hacia atrás
HISTORICAL_START_DATE = (datetime.now() - timedelta(days=HISTORICAL_MONTHS * 30)).strftime('%Y-%m-%d')

# =============================================================================
# 🔧 CONFIGURACIÓN DE PROCESAMIENTO
# =============================================================================

# Configuración de workers paralelos
PARALLEL_CONFIG = {
    'max_workers': 4,           # Máximo workers paralelos
    'timeout_per_request': 30,  # Timeout por request (segundos)
    'batch_size': 50,           # Símbolos por batch
}

# Configuración de archivos y directorios
PATHS = {
    'raw_data': 'raw_data',
    'logs': 'logs', 
    'temp': 'temp',
    'progress_file': 'logs/download_progress.json',
    'api_usage_file': 'logs/api_usage.json'
}

# =============================================================================
# 🚀 FUNCIONES DE UTILIDAD
# =============================================================================

def is_api_available(api_name: str) -> bool:
    """Verificar si API está disponible"""
    if api_name.upper() == 'YAHOO':
        return True  # Yahoo no necesita API key
    
    key = API_KEYS.get(api_name.upper())
    return key is not None and key.strip() != ''

def get_available_apis() -> List[str]:
    """Obtener lista de APIs disponibles"""
    available = []
    for api in API_PRIORITY:
        if is_api_available(api):
            available.append(api)
    return available

def validate_config() -> List[str]:
    """Validar configuración"""
    errors = []
    
    # Verificar al menos una API
    available_apis = get_available_apis()
    if not available_apis:
        errors.append("❌ No hay APIs disponibles")
    
    # Verificar símbolos
    if not SYMBOLS:
        errors.append("❌ No hay símbolos configurados")
    
    # Verificar timeframes
    if not TIMEFRAMES:
        errors.append("❌ No hay timeframes configurados")
        
    return errors

def print_config_summary():
    """Mostrar resumen de configuración"""
    print("⚙️ CONFIGURACIÓN SISTEMA HISTÓRICO")
    print("=" * 45)
    
    # APIs
    available_apis = get_available_apis()
    print(f"🔑 APIs disponibles: {len(available_apis)}")
    for api in available_apis:
        print(f"   ✅ {api}")
    
    unavailable_apis = [api for api in API_PRIORITY if api not in available_apis]
    if unavailable_apis:
        for api in unavailable_apis:
            print(f"   ❌ {api} (sin API key)")
    
    # Datos
    print(f"📊 Símbolos: {len(SYMBOLS)} ({', '.join(SYMBOLS[:3])}...)")
    print(f"⏱️ Timeframes: {', '.join(TIMEFRAMES)}")
    print(f"📅 Período: {HISTORICAL_START_DATE} a hoy")
    print(f"🔧 Workers: {PARALLEL_CONFIG['max_workers']}")
    
    print("=" * 45)

# Ejecutar validación al importar
if __name__ == "__main__":
    errors = validate_config()
    if errors:
        print("❌ ERRORES DE CONFIGURACIÓN:")
        for error in errors:
            print(f"  {error}")
    else:
        print("✅ Configuración válida")
        print_config_summary()