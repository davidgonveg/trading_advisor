"""
Configuración global para el sistema de alertas de acciones.
"""
import os

# Rutas de directorios
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
LOGS_DIR = os.path.join(BASE_DIR, 'logs')

# Configuración de Telegram
TELEGRAM_BOT_TOKEN = ""
TELEGRAM_CHAT_ID = ""

# Configuración de la base de datos
DB_PATH = os.path.join(DATA_DIR, "stock_alerts.db")
DB_BACKUP_PATH = os.path.join(DATA_DIR, "backups")

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
LOG_ROTATION_DAYS = 30
LOG_MAX_FILES = 10

# Opciones de rendimiento del sistema
MAX_THREADS = 5
REQUESTS_TIMEOUT = 30  # segundos (aumentado para yfinance)
API_RETRY_ATTEMPTS = 3
RATE_LIMIT_THROTTLE = 1.0  # segundos entre solicitudes a yfinance (más conservador)

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
    ]

# Configuración de notificaciones
NOTIFICATIONS_ENABLED = True
DAILY_SUMMARY_ENABLED = True
DAILY_SUMMARY_TIME = "18:00"  # Hora para enviar resumen diario (formato 24h)
WEEKLY_SUMMARY_ENABLED = True
WEEKLY_SUMMARY_DAY = 5  # Viernes (0=Lunes, 6=Domingo)

# Crear directorios si no existen
for directory in [DATA_DIR, LOGS_DIR, DB_BACKUP_PATH]:
    os.makedirs(directory, exist_ok=True)
