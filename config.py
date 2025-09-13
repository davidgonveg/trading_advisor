#!/usr/bin/env python3
"""
⚙️ CONFIGURACIÓN DEL SISTEMA DE TRADING AUTOMATIZADO V2.0
========================================================

Este archivo contiene toda la configuración del sistema.
Modifica estos parámetros según tus necesidades.
"""

import os
from dotenv import load_dotenv

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
    'NO_TRADE': 70,      # < 70 puntos: No operar
    'PARTIAL_ENTRY': 80, # 70-79 puntos: Entrada parcial
    'FULL_ENTRY': 100,   # ≥ 100 puntos: Entrada completa
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

# Horarios de trading permitidos (formato 24h)
TRADING_SESSIONS = {
    'MORNING': {
        'START': "09:45",
        'END': "11:45"
    },
    'AFTERNOON': {
        'START': "13:30", 
        'END': "15:30"
    }
}

# Días de la semana permitidos (0=Lunes, 6=Domingo)
ALLOWED_WEEKDAYS = [0, 1, 2, 3, 4]  # Lunes a Viernes

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
}

# =============================================================================
# 🔧 CONFIGURACIÓN TÉCNICA
# =============================================================================

# Logging
LOG_LEVEL = "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_FILE = "trading_system.log"

# API Configuration
API_CONFIG = {
    'YFINANCE_TIMEOUT': 30,
    'MAX_RETRIES': 3,
    'RETRY_DELAY': 5,  # segundos
}

# Performance
PERFORMANCE_CONFIG = {
    'MAX_CONCURRENT_DOWNLOADS': 6,  # Máximo símbolos en paralelo
    'DATA_CACHE_MINUTES': 5,        # Cache de datos en minutos
}

# =============================================================================
# 🧪 CONFIGURACIÓN DE DESARROLLO Y TESTING
# =============================================================================

# Modo de desarrollo (más logs, sin alertas reales en testing)
DEVELOPMENT_MODE = os.getenv('DEVELOPMENT_MODE', 'False').lower() == 'true'

# Testing
TEST_MODE = os.getenv('TEST_MODE', 'False').lower() == 'true'

# Símbolos para testing (más pequeño)
TEST_SYMBOLS = ["SPY", "AAPL"]

# =============================================================================
# 🔍 VALIDACIÓN DE CONFIGURACIÓN
# =============================================================================

def validate_config():
    """
    Validar que la configuración es correcta
    """
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
    
    return errors

def print_config_summary():
    """
    Imprimir resumen de configuración actual
    """
    print("⚙️ CONFIGURACIÓN DEL SISTEMA")
    print("=" * 50)
    print(f"📊 Símbolos: {', '.join(SYMBOLS)}")
    print(f"⏰ Intervalo: {SCAN_INTERVAL} minutos")
    print(f"💰 Riesgo por operación: {RISK_PER_TRADE}%")
    print(f"🎯 Umbral señal mínima: {SIGNAL_THRESHOLDS['NO_TRADE']} puntos")
    print(f"🤖 Modo desarrollo: {'Sí' if DEVELOPMENT_MODE else 'No'}")
    print(f"📱 Telegram configurado: {'Sí' if TELEGRAM_TOKEN and CHAT_ID else 'No'}")
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