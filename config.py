"""
Configuración global para el sistema de alertas de acciones.
Usa variables de entorno para credenciales sensibles.
"""
import os
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Rutas de directorios
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
LOGS_DIR = os.path.join(BASE_DIR, 'logs')

# Configuración de Telegram
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')

# Verificar que las credenciales de Telegram estén configuradas
if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    print("⚠️ ADVERTENCIA: Credenciales de Telegram no configuradas")

# Configuración de la base de datos
DB_PATH = os.path.join(DATA_DIR, "stock_alerts.db")
DB_BACKUP_PATH = os.path.join(DATA_DIR, "backups")

# Configuración de APIs
FINNHUB_API_KEY = os.getenv('FINNHUB_API_KEY', '')

# Configuración de Trading212
TRADING212_API_KEY = os.getenv('TRADING212_API_KEY', '')
TRADING212_API_URL = os.getenv('TRADING212_API_URL', 'https://demo.trading212.com')

# Configuraciones de depuración y modo de operación
DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'
ENABLE_TRADING = os.getenv('ENABLE_TRADING', 'False').lower() == 'true'
SIMULATION_MODE = os.getenv('SIMULATION_MODE', 'True').lower() == 'true'

# Eliminar estas variables o establecerlas a valores fijos
ENABLE_TRADING = True  # Siempre habilitado
SIMULATION_MODE = False  # Nunca en modo simulación

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
CHECK_INTERVAL_MINUTES = 15.1
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
import os
for directory in [DATA_DIR, LOGS_DIR, DB_BACKUP_PATH]:
    os.makedirs(directory, exist_ok=True)

# Imprimir advertencias de configuración
if DEBUG:
    print("🔍 Modo de depuración activado")
if ENABLE_TRADING:
    print("💹 Trading automático HABILITADO")
if SIMULATION_MODE:
    print("🎮 Modo de simulación activado")