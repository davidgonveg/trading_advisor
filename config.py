"""
Configuración global para el sistema de alertas de acciones.
"""
import os

# Rutas de directorios
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
LOGS_DIR = os.path.join(BASE_DIR, 'logs')

# Configuración de Telegram
TELEGRAM_BOT_TOKEN = "7869353980:AAGGPrOKCTD4afFc8k3PifPOzLLE6KY3E2E"
TELEGRAM_CHAT_ID = "477718262"

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
    Returns the updated list of stocks to monitor.
    """
    return [
        # Magnificent 7
        'NVDA',  # NVIDIA
        'TSLA',  # Tesla
        'META',  # Meta (Facebook)
        'AAPL',  # Apple
        'MSFT',  # Microsoft
        'GOOGL', # Google
        'AMZN',  # Amazon
        
        # Growth stocks
        'ASTS',  # AST SpaceMobile
        'PLTR',  # Palantir
        'AMD',   # AMD - Good for technical analysis with volatility
        'SMCI',  # Super Micro Computer - Highly volatile, good for TA signals
        
        # AI and tech with strong momentum
        'ARM',   # ARM Holdings
        'CRWD',  # CrowdStrike - Cybersecurity with clear technical patterns
        'SHOP',  # Shopify
        'UBER',  # Uber - Shows clear technical patterns
        'SNAP',  # Snap Inc. - Highly responsive to technical indicators
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
