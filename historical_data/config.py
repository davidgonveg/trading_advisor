#!/usr/bin/env python3
"""
⚙️ CONFIGURACIÓN SISTEMA DE DATOS HISTÓRICOS - V3.0
================================================

Configuración centralizada para:
- Multi-API management (Yahoo, Alpha Vantage, Twelve Data, Polygon)
- Rate limiting inteligente
- Parámetros de descarga y procesamiento
- Configuración de backtesting
"""

import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# =============================================================================
# 🔑 CONFIGURACIÓN DE APIs
# =============================================================================

# API Keys desde .env
API_KEYS = {
    'ALPHA_VANTAGE': os.getenv('ALPHA_VANTAGE_API_KEY'),
    'TWELVE_DATA': os.getenv('TWELVE_DATA_API_KEY'), 
    'POLYGON': os.getenv('POLYGON_API_KEY'),
    # Yahoo Finance no requiere API key
}

# URLs base de las APIs
API_ENDPOINTS = {
    'YAHOO': 'https://query1.finance.yahoo.com/v8/finance/chart/',
    'ALPHA_VANTAGE': 'https://www.alphavantage.co/query',
    'TWELVE_DATA': 'https://api.twelvedata.com/',
    'POLYGON': 'https://api.polygon.io/v2/aggs/ticker/'
}

# Rate limits para cada API (segundos entre requests)
RATE_LIMITS = {
    'YAHOO': 0.5,           # 0.5 seg = ~120 requests/min (conservador)
    'ALPHA_VANTAGE': 12.5,  # 12.5 seg = ~5 requests/min (límite oficial)
    'TWELVE_DATA': 1.0,     # 1 seg = 60 requests/min (conservador)
    'POLYGON': 10.0,        # 10 seg = 6 requests/min (muy conservador)
}

# Límites diarios de requests
DAILY_LIMITS = {
    'YAHOO': 50000,         # Sin límite oficial, estimación conservadora
    'ALPHA_VANTAGE': 500,   # Límite oficial plan gratuito
    'TWELVE_DATA': 800,     # Límite oficial plan gratuito
    'POLYGON': 100,         # Límite oficial plan gratuito
}

# Prioridad de APIs (orden de preferencia)
API_PRIORITY = [
    'YAHOO',         # Primera opción: rápido y sin límites
    'TWELVE_DATA',   # Segunda opción: buena calidad, 800 requests/día
    'ALPHA_VANTAGE', # Tercera opción: confiable, 500 requests/día
    'POLYGON'        # Última opción: muy limitado, solo emergencias
]

# =============================================================================
# 📅 CONFIGURACIÓN DE DATOS HISTÓRICOS
# =============================================================================

# Período de datos a descargar
HISTORICAL_START_DATE = os.getenv('HISTORICAL_START_DATE', '2021-01-01')
HISTORICAL_END_DATE = os.getenv('HISTORICAL_END_DATE', '2024-12-31')

# Símbolos a procesar (usar los mismos que el sistema principal)
def get_symbols_from_main_config():
    """Obtener símbolos del config principal, con fallback"""
    try:
        import sys
        import os
        
        # Añadir directorio padre al path
        parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if parent_dir not in sys.path:
            sys.path.insert(0, parent_dir)
        
        # Importar config principal evitando conflicto de nombres
        import importlib.util
        config_path = os.path.join(parent_dir, 'config.py')
        spec = importlib.util.spec_from_file_location("main_config", config_path)
        main_config = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(main_config)
        
        return main_config.SYMBOLS
        
    except Exception as e:
        print(f"⚠️ Warning: No se pudo importar config principal: {e}")
        # Fallback con los símbolos por defecto
        return [
            "^GSPC", "^NDX", "AAPL", "MSFT", "GOOGL", 
            "NVDA", "TSLA", "META", "AMZN"
        ]

# Obtener símbolos
SYMBOLS = get_symbols_from_main_config()

# Timeframes a descargar (orden de prioridad)
TIMEFRAMES = {
    '1d': {
        'yahoo_interval': '1d',
        'alpha_vantage_function': 'TIME_SERIES_DAILY',
        'twelve_data_interval': '1day',
        'polygon_timespan': 'day',
        'priority': 1,  # Más importante
        'max_period': '5y'  # Yahoo puede hasta 5 años en daily
    },
    '15m': {
        'yahoo_interval': '15m', 
        'alpha_vantage_function': 'TIME_SERIES_INTRADAY',
        'twelve_data_interval': '15min',
        'polygon_timespan': 'minute',
        'priority': 2,  # Principal para backtesting
        'max_period': '730d'  # Yahoo límite para intraday
    },
    '5m': {
        'yahoo_interval': '5m',
        'alpha_vantage_function': 'TIME_SERIES_INTRADAY', 
        'twelve_data_interval': '5min',
        'polygon_timespan': 'minute',
        'priority': 3,  # Opcional para análisis futuro
        'max_period': '60d'  # Más limitado para 5m
    }
}

# Configuración de descarga por timeframe
DOWNLOAD_CONFIG = {
    '1d': {
        'batch_size': 1,        # 1 request por símbolo (todo el período)
        'parallel_workers': 3,   # 3 símbolos en paralelo
        'retry_attempts': 3,
        'timeout_seconds': 30
    },
    '15m': {
        'batch_size': 30,       # 30 días por request (Yahoo límite)
        'parallel_workers': 2,   # Más conservador para intraday
        'retry_attempts': 5,     # Más reintentos (más propenso a fallar)
        'timeout_seconds': 45
    },
    '5m': {
        'batch_size': 7,        # 7 días por request (muy limitado)
        'parallel_workers': 1,   # Secuencial para 5m
        'retry_attempts': 3,
        'timeout_seconds': 60
    }
}

# =============================================================================
# 🔧 CONFIGURACIÓN DE PROCESAMIENTO
# =============================================================================

# Procesamiento paralelo
MAX_WORKERS = int(os.getenv('MAX_WORKERS', '4'))  # Ajustado para tu Ryzen 5 5500

# Modo de descarga (conservative/normal/aggressive)
DOWNLOAD_MODE = os.getenv('DOWNLOAD_MODE', 'normal')

# Configuración según modo
DOWNLOAD_MODES = {
    'conservative': {
        'rate_multiplier': 2.0,      # Delays x2 más largos
        'max_retries': 3,
        'parallel_workers': 2,
        'batch_size_reduction': 0.5   # Batches más pequeños
    },
    'normal': {
        'rate_multiplier': 1.0,      # Delays normales
        'max_retries': 5,
        'parallel_workers': 4,
        'batch_size_reduction': 1.0   # Batches normales
    },
    'aggressive': {
        'rate_multiplier': 0.7,      # Delays más cortos
        'max_retries': 8,
        'parallel_workers': 6,
        'batch_size_reduction': 1.5   # Batches más grandes
    }
}

# =============================================================================
# 📊 CONFIGURACIÓN DE BASE DE DATOS
# =============================================================================

# Extensión del schema de base de datos
HISTORICAL_TABLES = {
    'historical_ohlcv': {
        'columns': [
            'id INTEGER PRIMARY KEY AUTOINCREMENT',
            'timestamp TEXT NOT NULL',
            'symbol TEXT NOT NULL', 
            'timeframe TEXT NOT NULL',
            'open_price REAL NOT NULL',
            'high_price REAL NOT NULL',
            'low_price REAL NOT NULL', 
            'close_price REAL NOT NULL',
            'volume INTEGER NOT NULL',
            'source_api TEXT NOT NULL',
            'created_at TEXT DEFAULT CURRENT_TIMESTAMP'
        ],
        'indexes': [
            'CREATE INDEX IF NOT EXISTS idx_historical_symbol_time ON historical_ohlcv(symbol, timeframe, timestamp)',
            'CREATE INDEX IF NOT EXISTS idx_historical_timestamp ON historical_ohlcv(timestamp)',
            'CREATE INDEX IF NOT EXISTS idx_historical_source ON historical_ohlcv(source_api)'
        ],
        'unique_constraint': 'UNIQUE(timestamp, symbol, timeframe, source_api)'
    },
    
    'download_progress': {
        'columns': [
            'id INTEGER PRIMARY KEY AUTOINCREMENT',
            'symbol TEXT NOT NULL',
            'timeframe TEXT NOT NULL',
            'start_date TEXT NOT NULL',
            'end_date TEXT NOT NULL',
            'total_requests INTEGER',
            'completed_requests INTEGER DEFAULT 0',
            'failed_requests INTEGER DEFAULT 0',
            'status TEXT DEFAULT "PENDING"',  # PENDING, IN_PROGRESS, COMPLETED, FAILED
            'source_api TEXT',
            'error_message TEXT',
            'started_at TEXT',
            'completed_at TEXT',
            'created_at TEXT DEFAULT CURRENT_TIMESTAMP'
        ],
        'indexes': [
            'CREATE INDEX IF NOT EXISTS idx_progress_symbol ON download_progress(symbol)',
            'CREATE INDEX IF NOT EXISTS idx_progress_status ON download_progress(status)'
        ]
    },
    
    'api_usage_stats': {
        'columns': [
            'id INTEGER PRIMARY KEY AUTOINCREMENT',
            'api_name TEXT NOT NULL',
            'date TEXT NOT NULL',  # YYYY-MM-DD
            'requests_made INTEGER DEFAULT 0',
            'requests_successful INTEGER DEFAULT 0',
            'requests_failed INTEGER DEFAULT 0',
            'avg_response_time REAL DEFAULT 0',
            'updated_at TEXT DEFAULT CURRENT_TIMESTAMP'
        ],
        'indexes': [
            'CREATE INDEX IF NOT EXISTS idx_usage_api_date ON api_usage_stats(api_name, date)'
        ],
        'unique_constraint': 'UNIQUE(api_name, date)'
    }
}

# Configuración de bulk inserts
BULK_INSERT_CONFIG = {
    'batch_size': 1000,           # Registros por transacción
    'commit_frequency': 5000,     # Commit cada N registros
    'vacuum_after_insert': True,  # Optimizar DB después de inserts masivos
    'temp_table_prefix': 'temp_'
}

# =============================================================================
# 🧪 CONFIGURACIÓN DE BACKTESTING
# =============================================================================

# Capital y comisiones
BACKTEST_CONFIG = {
    'initial_capital': float(os.getenv('BACKTEST_INITIAL_CAPITAL', '10000')),
    'commission_per_trade': float(os.getenv('BACKTEST_COMMISSION_PER_TRADE', '1.0')),
    'slippage_pct': float(os.getenv('BACKTEST_SLIPPAGE_PCT', '0.05')),
    
    # Configuración de posiciones
    'max_positions': 3,           # Máximo 3 posiciones simultáneas
    'position_sizing': 'fixed',   # fixed, percentage, volatility_adjusted
    'risk_per_trade': 1.5,       # % del capital por operación
    
    # Configuración temporal
    'start_date': HISTORICAL_START_DATE,
    'end_date': HISTORICAL_END_DATE,
    'warmup_period': 50,          # Días para calcular indicadores iniciales
    
    # Métricas a calcular
    'calculate_metrics': [
        'total_return', 'sharpe_ratio', 'max_drawdown', 
        'win_rate', 'profit_factor', 'avg_trade_duration'
    ]
}

# =============================================================================
# 🔍 CONFIGURACIÓN DE VALIDACIÓN
# =============================================================================

# Validación de calidad de datos
DATA_QUALITY_CONFIG = {
    'enable_cross_validation': os.getenv('ENABLE_CROSS_VALIDATION', 'true').lower() == 'true',
    'max_price_deviation_pct': 5.0,    # Máximo 5% diferencia entre fuentes
    'min_volume_threshold': 100,        # Volumen mínimo para considerar válido
    'max_gap_hours': 72,                # Máximo gap de datos (horas)
    
    # Detección de outliers
    'outlier_detection': {
        'enable': True,
        'price_change_threshold': 20.0,  # % cambio precio sospechoso
        'volume_spike_threshold': 10.0,  # Multiplicador volumen sospechoso
        'consecutive_same_price': 5      # Precios iguales consecutivos sospechosos
    },
    
    # Corrección automática
    'auto_correction': {
        'enable': True,
        'interpolate_gaps': True,        # Interpolar gaps pequeños
        'remove_outliers': False,        # Solo marcar, no remover
        'use_multiple_sources': True     # Validar con múltiples APIs
    }
}

# =============================================================================
# 📝 CONFIGURACIÓN DE LOGGING
# =============================================================================

# Logging detallado
LOGGING_CONFIG = {
    'level': os.getenv('HISTORICAL_LOG_LEVEL', 'INFO'),
    'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    'file_handler': {
        'filename': 'historical_data/logs/historical_system.log',
        'max_bytes': 10 * 1024 * 1024,  # 10 MB
        'backup_count': 5
    },
    'console_handler': {
        'enabled': True,
        'colored': True
    }
}

# Progress tracking
PROGRESS_CONFIG = {
    'update_frequency': 10,           # Actualizar progreso cada N requests
    'save_progress_file': True,       # Guardar progreso en archivo
    'progress_file': 'historical_data/logs/download_progress.json',
    'estimated_time': True,           # Mostrar tiempo estimado restante
    'detailed_stats': True           # Mostrar estadísticas detalladas
}

# =============================================================================
# 🧹 CONFIGURACIÓN DE LIMPIEZA
# =============================================================================

# Auto cleanup
CLEANUP_CONFIG = {
    'auto_cleanup': os.getenv('AUTO_CLEANUP_TEMP_DATA', 'true').lower() == 'true',
    'temp_data_retention_days': 7,    # Mantener datos temporales 7 días
    'log_retention_days': 30,         # Mantener logs 30 días
    'progress_file_retention_days': 7, # Mantener archivos de progreso 7 días
    
    # Archivos a limpiar automáticamente
    'cleanup_patterns': [
        'historical_data/temp_data/*.csv',
        'historical_data/temp_data/*.json',
        'historical_data/logs/*.tmp'
    ]
}

# =============================================================================
# 🚀 FUNCIONES DE UTILIDAD
# =============================================================================

def get_effective_rate_limit(api_name: str) -> float:
    """Obtener rate limit efectivo según modo de descarga"""
    base_rate = RATE_LIMITS.get(api_name.upper(), 1.0)
    multiplier = DOWNLOAD_MODES[DOWNLOAD_MODE]['rate_multiplier']
    return base_rate * multiplier

def get_effective_workers(base_workers: int) -> int:
    """Obtener número efectivo de workers según modo"""
    mode_workers = DOWNLOAD_MODES[DOWNLOAD_MODE]['parallel_workers']
    return min(base_workers, mode_workers)

def is_api_available(api_name: str) -> bool:
    """Verificar si API está disponible (tiene key configurada)"""
    if api_name.upper() == 'YAHOO':
        return True  # Yahoo no requiere key
    
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
    """Validar configuración y retornar lista de errores"""
    errors = []
    
    # Verificar que al menos una API esté disponible
    available_apis = get_available_apis()
    if not available_apis:
        errors.append("❌ No hay APIs disponibles. Configura al menos ALPHA_VANTAGE_API_KEY")
    
    # Verificar fechas
    try:
        start_date = datetime.strptime(HISTORICAL_START_DATE, '%Y-%m-%d')
        end_date = datetime.strptime(HISTORICAL_END_DATE, '%Y-%m-%d')
        
        if start_date >= end_date:
            errors.append("❌ HISTORICAL_START_DATE debe ser anterior a HISTORICAL_END_DATE")
            
        if end_date > datetime.now():
            errors.append("⚠️ HISTORICAL_END_DATE es en el futuro")
            
    except ValueError as e:
        errors.append(f"❌ Error en formato de fechas: {e}")
    
    # Verificar workers
    if MAX_WORKERS < 1 or MAX_WORKERS > 10:
        errors.append("❌ MAX_WORKERS debe estar entre 1 y 10")
    
    # Verificar modo de descarga
    if DOWNLOAD_MODE not in DOWNLOAD_MODES:
        errors.append(f"❌ DOWNLOAD_MODE debe ser uno de: {list(DOWNLOAD_MODES.keys())}")
    
    return errors

def print_config_summary():
    """Imprimir resumen de configuración"""
    print("⚙️ CONFIGURACIÓN SISTEMA HISTÓRICO")
    print("=" * 60)
    
    # APIs disponibles
    available_apis = get_available_apis()
    print(f"🔑 APIs disponibles: {', '.join(available_apis)}")
    
    # Período de datos
    print(f"📅 Período: {HISTORICAL_START_DATE} a {HISTORICAL_END_DATE}")
    
    # Símbolos
    print(f"📊 Símbolos: {len(SYMBOLS)} ({', '.join(SYMBOLS[:3])}{'...' if len(SYMBOLS) > 3 else ''})")
    
    # Timeframes
    print(f"⏰ Timeframes: {', '.join(TIMEFRAMES.keys())}")
    
    # Procesamiento
    print(f"🔧 Workers: {MAX_WORKERS} | Modo: {DOWNLOAD_MODE}")
    
    # Backtesting
    print(f"💰 Capital inicial: ${BACKTEST_CONFIG['initial_capital']:,.0f}")
    
    print("=" * 60)

if __name__ == "__main__":
    # Ejecutar validación si se ejecuta directamente
    errors = validate_config()
    
    if errors:
        print("❌ ERRORES DE CONFIGURACIÓN:")
        for error in errors:
            print(f"  {error}")
    else:
        print("✅ Configuración válida")
        print_config_summary()