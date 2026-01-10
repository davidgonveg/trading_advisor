#!/usr/bin/env python3
"""
⚙️ CONFIGURACIÓN DEL SISTEMA DE TRADING AUTOMATIZADO V3.2 - REAL DATA GAPS
=========================================================================

Este archivo contiene toda la configuración del sistema.
Modifica estos parámetros según tus necesidades.

🆕 V3.2: GAP FILLING CORREGIDO - USA DATOS REALES DE YFINANCE
"""

import os
from dotenv import load_dotenv
from pathlib import Path

# Cargar variables de entorno desde .env
load_dotenv()

# =============================================================================
# 📊 CONFIGURACIÓN DE SÍMBOLOS Y MERCADO
# =============================================================================

# Símbolos a monitorear - S&P 500, NASDAQ 100 y las 7 Magníficas
SYMBOLS = [
    # === ÍNDICES PRINCIPALES ===
    "^GSPC",  # S&P 500 Index
    "^NDX",   # Nasdaq 100 Index

    # === LAS 7 MAGNÍFICAS (Magnificent Seven) ===
    "AAPL",   # Apple Inc.
    "MSFT",   # Microsoft Corporation
    "GOOGL",  # Alphabet Inc.
    "NVDA",   # NVIDIA Corporation
    "TSLA",   # Tesla Inc.
    "META",   # Meta Platforms Inc.
    "AMZN",   # Amazon
]

# Timeframe para análisis (en minutos)
TIMEFRAME = "15m"
SCAN_INTERVAL = 15  # Minutos entre escaneos

# Período de datos históricos a descargar (días)
HISTORY_DAYS = 30

# =============================================================================
# 📈 PARÁMETROS DE INDICADORES TÉCNICOS
# =============================================================================

# RSI (Relative Strength Index)
RSI_PERIOD = 14
RSI_OVERSOLD = 40    # Umbral de sobreventa para LARGOS
RSI_OVERBOUGHT = 60  # Umbral de sobrecompra para CORTOS

# MACD (Moving Average Convergence Divergence)
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9

# Bollinger Bands
BB_PERIOD = 20
BB_STD_DEV = 2

# ROC (Rate of Change / Momentum)
ROC_PERIOD = 10
ROC_BULLISH_THRESHOLD = 1.5   # % mínimo para momentum alcista
ROC_BEARISH_THRESHOLD = -1.5  # % máximo para momentum bajista

# ATR (Average True Range)
ATR_PERIOD = 14

# Oscilador de Volumen
VOLUME_FAST = 5
VOLUME_SLOW = 20
VOLUME_THRESHOLD = 50  # % mínimo de oscilador de volumen

# VWAP (Volume Weighted Average Price)
VWAP_DEVIATION_LONG = 0.5   # % máximo de desviación para LARGOS
VWAP_DEVIATION_SHORT = 1.0  # % mínimo de desviación para CORTOS

# =============================================================================
# 🎯 SISTEMA DE PUNTUACIÓN Y SEÑALES
# =============================================================================

# Puntuaciones por indicador (máximo 100 puntos total)
SCORING = {
    'MACD': 20,        # 20 puntos máximo
    'RSI': 20,         # 20 puntos máximo
    'VWAP': 15,        # 15 puntos máximo
    'ROC': 20,         # 20 puntos máximo
    'BOLLINGER': 15,   # 15 puntos máximo
    'VOLUME': 10,      # 10 puntos máximo (bonus)
}

# Umbrales de señales
SIGNAL_THRESHOLDS = {
    'NO_TRADE': 55,      # < 55 puntos: No operar
    'PARTIAL_ENTRY': 65, # 65-74 puntos: Entrada parcial
    'FULL_ENTRY': 75,    # ≥ 75 puntos: Entrada completa
}

# =============================================================================
# 💰 GESTIÓN DE POSICIONES Y RIESGO
# =============================================================================

# Riesgo por operación (% del capital)
RISK_PER_TRADE = 1.5

# Distribución de entradas escalonadas (debe sumar 100%)
ENTRY_DISTRIBUTION = {
    'ENTRY_1': 40,  # 40% en primera entrada
    'ENTRY_2': 30,  # 30% en segunda entrada  
    'ENTRY_3': 30,  # 30% en tercera entrada
}

# Distribución de salidas escalonadas (debe sumar 100%)
EXIT_DISTRIBUTION = {
    'TP1': 25,  # 25% en TP1
    'TP2': 25,  # 25% en TP2
    'TP3': 25,  # 25% en TP3
    'TP4': 25,  # 25% en TP4 (trailing)
}

# Multiplicadores de ATR para niveles
ATR_MULTIPLIERS = {
    # Entradas escalonadas
    'ENTRY_2': 0.5,  # Entrada 2 a 0.5 ATR
    'ENTRY_3': 1.0,  # Entrada 3 a 1.0 ATR
    
    # Stop Loss
    'STOP_LOSS': 1.0,  # Stop a 1 ATR
    
    # Take Profits (en múltiplos de riesgo R)
    'TP1': 1.5,  # 1.5R
    'TP2': 2.5,  # 2.5R
    'TP3': 4.0,  # 4.0R
    'TP4': 4.0,  # 4.0R + trailing
}

# =============================================================================
# ⏰ FILTROS TEMPORALES
# =============================================================================

# Zona horaria del mercado (configuración flexible desde .env)
MARKET_TIMEZONE = os.getenv('TIMEZONE', 'US/Eastern')

# Horarios de trading permitidos (formato 24h) - CONFIGURACIÓN ORIGINAL
TRADING_SESSIONS = {
    'MORNING': {
        'START': "10:00",
        'END': "12:00"
    },
    'AFTERNOON': {
        'START': "13:30", 
        'END': "15:30"
    }
}

# 🆕 HORARIOS EXTENDIDOS COMPLETOS (24/5 coverage) - NUEVA FUNCIONALIDAD
EXTENDED_TRADING_SESSIONS = {
    'PRE_MARKET': {
        'START': "04:00",
        'END': "09:30",
        'ENABLED': True,
        'DATA_INTERVAL': 30,  # minutos entre recolecciones
        'DESCRIPTION': "Pre-market trading hours"
    },
    'MORNING': {
        'START': "10:00", 
        'END': "12:00",
        'ENABLED': True,
        'DATA_INTERVAL': 15,  # tu configuración actual
        'DESCRIPTION': "Morning active trading"
    },
    'AFTERNOON': {
        'START': "13:30",
        'END': "15:30", 
        'ENABLED': True,
        'DATA_INTERVAL': 15,  # tu configuración actual
        'DESCRIPTION': "Afternoon active trading"
    },
    'POST_MARKET': {
        'START': "16:00",
        'END': "20:00",
        'ENABLED': True,
        'DATA_INTERVAL': 30,  # menos frecuente que regular hours
        'DESCRIPTION': "Post-market trading hours"
    },
    'OVERNIGHT': {
        'START': "20:00",
        'END': "04:00",  # next day
        'ENABLED': True,
        'DATA_INTERVAL': 120,  # cada 2 horas para gaps
        'DESCRIPTION': "Overnight gap monitoring"
    }
}

# Días de la semana permitidos (0=Lunes, 6=Domingo)
ALLOWED_WEEKDAYS = [0, 1, 2, 3, 4]  # Lunes a Viernes

# =============================================================================
# 🆕 CONFIGURACIÓN DE DATOS CONTINUOS V3.2
# =============================================================================

CONTINUOUS_DATA_CONFIG = {
    'ENABLE_EXTENDED_HOURS': True,
    'ENABLE_OVERNIGHT_MONITORING': True,
    'AUTO_FILL_GAPS': True,
    'MAX_GAP_HOURS': 4,  # gaps > 4h se consideran overnight
    'FORWARD_FILL_OVERNIGHT': False,  # 🔧 CAMBIADO: No usar forward fill
    'PRESERVE_WEEKEND_GAPS': False,  # ✅ CORRECTO: forzar relleno para persistencia
    'QUALITY_CHECK_BEFORE_BACKTEST': True
}

# =============================================================================
# 🆕 CONFIGURACIÓN DE GAP DETECTION Y FILLING V3.2 - CORREGIDO
# =============================================================================

GAP_DETECTION_CONFIG = {
    'MIN_GAP_MINUTES': 60,  # gaps menores a 1h = normales
    'OVERNIGHT_GAP_HOURS': [20, 4],  # 8PM - 4AM considerado overnight
    'WEEKEND_GAP_HOURS': 48,  # > 48h = gap de fin de semana
    'HOLIDAY_GAP_HOURS': 24,  # > 24h en día laborable = posible festivo
    
    # 🔧 ESTRATEGIAS CORREGIDAS - USA DATOS REALES
    'FILL_STRATEGIES': {
        'SMALL_GAP': 'REAL_DATA',        # ✅ Intentar datos reales primero
        'OVERNIGHT_GAP': 'REAL_DATA',    # ✅ CRÍTICO: datos reales para stops
        'WEEKEND_GAP': 'REAL_DATA',   # ✅ Rellenar para mantener estado
        'HOLIDAY_GAP': 'REAL_DATA',    # ✅ Rellenar para mantener estado
        'UNKNOWN_GAP': 'REAL_DATA'     # ✅ Rellenar siempre
    },
    
    # 🆕 CONFIGURACIÓN PARA DESCARGA DE DATOS REALES
    'REAL_DATA_CONFIG': {
        'USE_YFINANCE': True,
        'INCLUDE_PREPOST': True,              # ✅ Extended hours
        'FALLBACK_TO_CONSERVATIVE': True,     # Si falla, usar worst-case
        'MAX_GAP_TO_FILL_HOURS': 168,         # Permitir gaps de 1 semana (weekends)
        'RETRY_ATTEMPTS': 3,                  # Reintentos si falla API
        'RETRY_DELAY_SECONDS': 2,            # Delay entre reintentos
        'USE_WORST_CASE_ON_FAIL': True       # Usar worst-case si falla todo
    },
    
    # 🆕 WORST-CASE SCENARIO PARA GAPS SIN DATOS
    'WORST_CASE_CONFIG': {
        'ENABLED': True,
        'METHOD': 'CONSERVATIVE_RANGE',       # Asumir precio se movió
        'PRICE_MOVEMENT_ESTIMATE': 0.02,     # Asumir ±2% de movimiento
        'USE_ATR_IF_AVAILABLE': True,        # Usar ATR histórico si está disponible
        'SAFE_MARGIN': 1.2                   # Multiplicador de seguridad
    },
    
    # Validación de calidad
    'QUALITY_THRESHOLDS': {
        'MIN_COMPLETENESS_PCT': 95,          # >= 95% datos disponibles
        'MAX_CONSECUTIVE_GAPS': 5,           # máximo 5 gaps seguidos
        'MAX_GAP_DURATION_HOURS': 72,        # máximo 72h de gap continuo
        'MIN_REAL_DATA_PCT': 80              # 🆕 Mínimo 80% datos reales (no sintéticos)
    }
}

# 🆕 CONFIGURACIÓN DE YFINANCE EXTENDIDA
YFINANCE_EXTENDED_CONFIG = {
    'INCLUDE_PREPOST': True,  # ✅ CRÍTICO: incluir extended hours
    'EXTENDED_HOURS_ENABLED': True,
    'OVERNIGHT_DATA_ENABLED': True,
    'PREPOST_REQUIRED': True,  # forzar prepost=True siempre
    'AUTO_ADJUST': True,       # Ajustar por splits/dividendos
    'TIMEOUT_SECONDS': 30      # Timeout para requests
}

# =============================================================================
# 📱 CONFIGURACIÓN DE TELEGRAM
# =============================================================================

# Token del bot de Telegram (desde variable de entorno)
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')

# Chat ID donde enviar alertas (desde variable de entorno)
CHAT_ID = os.getenv('CHAT_ID')

# Configuración de mensajes
TELEGRAM_CONFIG = {
    'PARSE_MODE': 'HTML',
    'DISABLE_WEB_PAGE_PREVIEW': True,
    'TIMEOUT': 30,
}

# Tipos de alertas a enviar
ALERT_TYPES = {
    'SIGNAL_DETECTED': True,    # Enviar cuando se detecta señal
    'SYSTEM_START': True,       # Enviar cuando inicia el sistema
    'SYSTEM_ERROR': True,       # Enviar cuando hay errores
    'DAILY_SUMMARY': False,     # Enviar resumen diario (desactivado por defecto)
    'GAP_DETECTED': True,       # 🆕 alertas de gaps detectados
    'DATA_QUALITY_ISSUE': True, # 🆕 alertas de calidad de datos
    'REAL_DATA_FAILED': True    # 🆕 alerta si no se pueden obtener datos reales
}

# =============================================================================
# 🔧 CONFIGURACIÓN TÉCNICA
# =============================================================================

# Logging
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

LOG_LEVEL = "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_FILE = LOG_DIR / "trading_system.log"

# Logs específicos
SCANNER_LOG_FILE = LOG_DIR / "scanner.log"
EXIT_MANAGER_LOG_FILE = LOG_DIR / "exit_manager.log"
DATABASE_LOG_FILE = LOG_DIR / "database.log"
GAP_DETECTOR_LOG_FILE = LOG_DIR / "gap_detector.log"
CONTINUOUS_COLLECTOR_LOG_FILE = LOG_DIR / "continuous_collector.log"
DATA_VALIDATOR_LOG_FILE = LOG_DIR / "data_validator.log"

# API Configuration
API_CONFIG = {
    'YFINANCE_TIMEOUT': 30,
    'MAX_RETRIES': 3,
    'RETRY_DELAY': 5,  # segundos
    'RATE_LIMIT_DELAY': 0.1,
}

# Performance
PERFORMANCE_CONFIG = {
    'MAX_CONCURRENT_DOWNLOADS': 6,  # Máximo símbolos en paralelo
    'DATA_CACHE_MINUTES': 5,        # Cache de datos en minutos
}

# =============================================================================
# 🧪 CONFIGURACIÓN DE DESARROLLO Y TESTING
# =============================================================================

DEVELOPMENT_MODE = os.getenv('DEVELOPMENT_MODE', 'False').lower() == 'true'
TEST_MODE = os.getenv('TEST_MODE', 'False').lower() == 'true'
TEST_SYMBOLS = ["SPY", "AAPL"]

# Habilitar/deshabilitar sistema adaptativo
USE_ADAPTIVE_TARGETS = True

# Límites de R:R por estrategia
ADAPTIVE_RR_LIMITS = {
    'SCALP': {'min': 1.2, 'max': 3.0},
    'SWING_SHORT': {'min': 1.5, 'max': 5.0},
    'SWING_MEDIUM': {'min': 1.8, 'max': 6.0},
    'POSITION': {'min': 2.0, 'max': 6.0}
}

# Configuración análisis técnico
TECHNICAL_ANALYSIS_CONFIG = {
    'LOOKBACK_PERIOD': 50,
    'FIBONACCI_LEVELS': [1.236, 1.382, 1.618, 2.618],
    'PSYCHOLOGICAL_LEVELS': [1, 2.5, 5, 10],
    'ATR_EXTENSIONS': [2, 3, 4, 6],
    'MAX_TARGET_DISTANCE_PCT': 20
}

# Configuración scoring
TARGET_SCORING_WEIGHTS = {
    'FIBONACCI': 90,
    'VWAP': 85,
    'RESISTANCE': 80,
    'SUPPORT': 80,
    'BOLLINGER': 75,
    'PSYCHOLOGICAL': 65,
    'ATR_EXTENSION': 60
}

# Position Management System V3.0 Configuration
USE_POSITION_MANAGEMENT = False
ENABLE_POSITION_CACHE = True
POSITION_CACHE_TIMEOUT_MINUTES = 5

# =============================================================================
# 🆕 CONFIGURACIÓN ESPECÍFICA PARA BACKTESTING V3.2
# =============================================================================

BACKTEST_CONFIG = {
    'REQUIRE_CONTINUOUS_DATA': True,    # exigir datos sin gaps
    'AUTO_FILL_BEFORE_BACKTEST': True,  # rellenar gaps automáticamente
    'VALIDATE_DATA_QUALITY': True,      # validar calidad antes de empezar
    'MIN_DATA_COMPLETENESS': 95,        # % mínimo de datos requerido
    'EXTENDED_HOURS_ANALYSIS': True,    # incluir extended hours en análisis
    'OVERNIGHT_GAP_ANALYSIS': True,     # analizar gaps overnight para stop-loss
    'REQUIRE_REAL_DATA': True,          # 🆕 Exigir datos reales (no sintéticos)
    'MAX_SYNTHETIC_DATA_PCT': 20,       # 🆕 Máximo 20% datos sintéticos
    'STOP_ON_QUALITY_FAIL': True        # 🆕 Detener si calidad insuficiente
}

# =============================================================================
# 🔄 CONFIGURACIÓN DE MANTENIMIENTO Y LIMPIEZA V3.2
# =============================================================================

MAINTENANCE_CONFIG = {
    'AUTO_CLEANUP_ENABLED': True,
    'CLEANUP_INTERVAL_HOURS': 24,
    'KEEP_RAW_DATA_DAYS': 30,
    'KEEP_PROCESSED_DATA_DAYS': 90,
    'AUTO_GAP_DETECTION_INTERVAL': 6,
    'DATA_QUALITY_CHECK_INTERVAL': 12,
    'REAL_DATA_REFRESH_DAYS': 7         # 🆕 Re-descargar datos reales cada 7 días
}

# =============================================================================
# 🆕 UTILIDADES PARA OTROS MÓDULOS V3.2
# =============================================================================

def get_current_trading_session():
    """Determinar sesión de trading actual basada en hora"""
    from datetime import datetime, time
    import pytz
    
    now = datetime.now(pytz.timezone(MARKET_TIMEZONE))
    current_time = now.time()
    
    for session_name, session_config in EXTENDED_TRADING_SESSIONS.items():
        if not session_config['ENABLED']:
            continue
            
        start_time = time.fromisoformat(session_config['START'])
        end_time = time.fromisoformat(session_config['END'])
        
        # Handle overnight session (crosses midnight)
        if session_name == 'OVERNIGHT':
            if current_time >= start_time or current_time <= end_time:
                return session_name, session_config
        else:
            if start_time <= current_time <= end_time:
                return session_name, session_config
    
    return None, None

def is_extended_hours_enabled():
    """Verificar si extended hours está habilitado"""
    return CONTINUOUS_DATA_CONFIG['ENABLE_EXTENDED_HOURS']

def get_data_collection_interval():
    """Obtener intervalo de recolección para sesión actual"""
    session_name, session_config = get_current_trading_session()
    if session_config:
        return session_config['DATA_INTERVAL']
    return 60  # default 1 hora si no hay sesión activa

def should_use_extended_hours():
    """Verificar si se debe usar extended hours en yfinance"""
    return YFINANCE_EXTENDED_CONFIG['PREPOST_REQUIRED']

def get_gap_fill_strategy(gap_type: str) -> str:
    """
    🆕 V3.2: Obtener estrategia de filling para un tipo de gap
    """
    return GAP_DETECTION_CONFIG['FILL_STRATEGIES'].get(gap_type, 'PRESERVE_GAP')

def should_use_real_data() -> bool:
    """
    🆕 V3.2: Verificar si se debe usar datos reales para gaps
    """
    return GAP_DETECTION_CONFIG['REAL_DATA_CONFIG']['USE_YFINANCE']

# =============================================================================
# 🔍 VALIDACIÓN DE CONFIGURACIÓN
# =============================================================================

def validate_config():
    """Validar que la configuración es correcta"""
    errors = []
    
    # Validar Telegram
    if not TELEGRAM_TOKEN:
        errors.append("❌ TELEGRAM_TOKEN no configurado en .env")
    
    if not CHAT_ID:
        errors.append("❌ CHAT_ID no configurado en .env")
    
    # Validar símbolos
    if not SYMBOLS:
        errors.append("❌ No hay símbolos configurados")
    
    # Validar distribuciones
    if sum(ENTRY_DISTRIBUTION.values()) != 100:
        errors.append(f"❌ ENTRY_DISTRIBUTION debe sumar 100%, actual: {sum(ENTRY_DISTRIBUTION.values())}%")
    
    if sum(EXIT_DISTRIBUTION.values()) != 100:
        errors.append(f"❌ EXIT_DISTRIBUTION debe sumar 100%, actual: {sum(EXIT_DISTRIBUTION.values())}%")
    
    # Validar umbrales
    if RSI_OVERSOLD >= RSI_OVERBOUGHT:
        errors.append("❌ RSI_OVERSOLD debe ser menor que RSI_OVERBOUGHT")
    
    # Validar riesgo
    if not 0.1 <= RISK_PER_TRADE <= 5.0:
        errors.append("❌ RISK_PER_TRADE debe estar entre 0.1% y 5.0%")
    
    # 🆕 Validar estrategias de gap filling
    valid_strategies = ['REAL_DATA', 'PRESERVE_GAP', 'FORWARD_FILL', 'INTERPOLATE']
    for gap_type, strategy in GAP_DETECTION_CONFIG['FILL_STRATEGIES'].items():
        if strategy not in valid_strategies:
            errors.append(f"❌ Estrategia inválida para {gap_type}: {strategy}")
    
    return errors

def print_config_summary():
    """Imprimir resumen de configuración actual"""
    print("⚙️ CONFIGURACIÓN DEL SISTEMA V3.2")
    print("=" * 50)
    print(f"📊 Símbolos: {', '.join(SYMBOLS)}")
    print(f"⏰ Intervalo: {SCAN_INTERVAL} minutos")
    print(f"💰 Riesgo por operación: {RISK_PER_TRADE}%")
    print(f"🎯 Umbral señal mínima: {SIGNAL_THRESHOLDS['NO_TRADE']} puntos")
    print(f"🤖 Modo desarrollo: {'Sí' if DEVELOPMENT_MODE else 'No'}")
    print(f"📱 Telegram configurado: {'Sí' if TELEGRAM_TOKEN and CHAT_ID else 'No'}")
    print(f"🕐 Extended hours: {'Sí' if is_extended_hours_enabled() else 'No'}")
    
    # 🆕 Info de gap filling
    print(f"\n🔧 GAP FILLING V3.2:")
    print(f"   Usar datos reales: {'Sí' if should_use_real_data() else 'No'}")
    for gap_type, strategy in GAP_DETECTION_CONFIG['FILL_STRATEGIES'].items():
        print(f"   {gap_type}: {strategy}")
    
    current_session, config = get_current_trading_session()
    if current_session:
        print(f"\n🎯 Sesión actual: {current_session} (intervalo: {config['DATA_INTERVAL']} min)")
    else:
        print("\n💤 No hay sesión activa actualmente")
    print("=" * 50)

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