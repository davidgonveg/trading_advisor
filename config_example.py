"""
Ejemplo de configuración global para el sistema de alertas de acciones.
Copie este archivo a config.py y actualice con sus propias claves API.
"""
import logging

# Configuración de Finnhub API
FINNHUB_API_KEY = "TU_CLAVE_API_FINNHUB"  # Reemplazar con tu clave API real

# Configuración de Telegram
TELEGRAM_BOT_TOKEN = "TU_TOKEN_BOT_TELEGRAM"
TELEGRAM_CHAT_ID = "TU_CHAT_ID_TELEGRAM"

# Configuración de la base de datos
DB_PATH = "data/stock_alerts.db"

# Configuración del análisis técnico
BOLLINGER_WINDOW = 18
BOLLINGER_DEVIATIONS = 2.25
MACD_FAST = 8
MACD_SLOW = 21
MACD_SIGNAL = 9
RSI_PERIOD = 14
STOCH_RSI_K_PERIOD = 14
STOCH_RSI_D_PERIOD = 3
STOCH_RSI_SMOOTH = 3

# Intervalos de tiempo
CHECK_INTERVAL_MINUTES = 20
INTEGRITY_CHECK_INTERVAL_SECONDS = 86400  # 24 horas

# Lista de acciones para monitorizar
def get_stock_list():
    """
    Devuelve la lista actualizada de acciones para monitorizar.
    """
    return [
        # Tecnológicas
        'NVDA',  # NVIDIA
        'TSLA',  # Tesla
        'META',  # Meta (Facebook)
        'AAPL',  # Apple
        'MSFT',  # Microsoft
        
        # Añade o elimina acciones según tus preferencias
        # La lista completa está en config.py
    ]