#!/usr/bin/env python3
"""
⚙️ CONFIGURACIÓN MÍNIMA - SISTEMA DATOS HISTÓRICOS V3.0
=====================================================

Configuración simplificada que funciona independientemente del sistema principal.
Use este archivo si hay problemas con config.py completo.
"""

import os
from datetime import datetime, timedelta
from typing import Dict, List
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# =============================================================================
# 🔑 CONFIGURACIÓN BÁSICA DE APIs
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
    'TWELVE_DATA': 'https://api.twelvedata.com/',
    'POLYGON': 'https://api.polygon.io/v2/aggs/ticker/'
}

# Rate limits (segundos entre requests)
RATE_LIMITS = {
    'YAHOO': 1.0,           # 1 seg entre requests
    'ALPHA_VANTAGE': 13.0,  # 13 seg = ~5 requests/min
    'TWELVE_DATA': 2.0,     # 2 seg = 30 requests/min
    'POLYGON': 15.0,        # 15 seg = 4 requests/min
}

# Límites diarios de requests
DAILY_LIMITS = {
    'YAHOO': 50000,         # Sin límite oficial
    'ALPHA_VANTAGE': 500,   # Plan gratuito
    'TWELVE_DATA': 800,     # Plan gratuito
    'POLYGON': 100,         # Plan gratuito
}

# Prioridad de APIs
API_PRIORITY = ['YAHOO', 'TWELVE_DATA', 'ALPHA_VANTAGE', 'POLYGON']

# =============================================================================
# 📅 CONFIGURACIÓN DE DATOS
# =============================================================================

# Período de datos históricos
HISTORICAL_START_DATE = os.getenv('HISTORICAL_START_DATE', '2023-01-01')

# Símbolos principales
SYMBOLS = [
    'AAPL', 'MSFT', 'GOOGL', 'NVDA', 'TSLA', 
    'META', 'AMZN', 'NFLX', 'CRM', 'ADBE'
]

# Timeframes disponibles
TIMEFRAMES = ['1d', '1h', '15m']

# =============================================================================
# 🔧 CONFIGURACIÓN DE PROCESAMIENTO
# =============================================================================

# Configuración de workers paralelos
PARALLEL_CONFIG = {
    'max_workers': 3,
    'timeout_per_request': 30
}

# Configuración de progreso
PROGRESS_CONFIG = {
    'progress_file': 'historical_data/logs/download_progress.json'
}

# Configuración de logging básica
LOGGING_CONFIG = {
    'level': 'INFO'
}

# =============================================================================
# 🚀 FUNCIONES DE UTILIDAD
# =============================================================================

def is_api_available(api_name: str) -> bool:
    """Verificar si API está disponible"""
    if api_name.upper() == 'YAHOO':
        return True
    
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
    """Validar configuración básica"""
    errors = []
    
    # Verificar al menos una API
    available_apis = get_available_apis()
    if not available_apis:
        errors.append("❌ No hay APIs disponibles")
        
    return errors

if __name__ == "__main__":
    print("⚙️ CONFIG MÍNIMO - DATOS HISTÓRICOS V3.0")
    print("-" * 50)
    
    # Mostrar APIs disponibles
    available = get_available_apis()
    print(f"🔑 APIs disponibles: {available}")
    
    # Validar
    errors = validate_config()
    if errors:
        print("❌ Errores:")
        for error in errors:
            print(f"  {error}")
    else:
        print("✅ Configuración básica válida")
        print(f"📅 Período: {HISTORICAL_START_DATE}")
        print(f"📊 Símbolos: {len(SYMBOLS)}")
        print(f"🔧 Workers: {PARALLEL_CONFIG['max_workers']}")