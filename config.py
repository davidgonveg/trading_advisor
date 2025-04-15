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
CHECK_INTERVAL_MINUTES = 10.1
INTEGRITY_CHECK_INTERVAL_SECONDS = 86400  # 24 horas
LOG_ROTATION_DAYS = 30
LOG_MAX_FILES = 10

# Opciones de rendimiento del sistema
MAX_THREADS = 5
REQUESTS_TIMEOUT = 30  # segundos (aumentado para yfinance)
API_RETRY_ATTEMPTS = 3
RATE_LIMIT_THROTTLE = 1.2  # segundos entre solicitudes a yfinance (más conservador)
MAX_SYMBOLS_PER_BATCH = 6  # Nuevo parámetro para limitar el número de símbolos por lote


def get_stock_list():
    """
    Lista de acciones optimizada para alta liquidez (operaciones de $50,000+ instantáneas),
    spreads mínimos y características favorables para análisis técnico.
    """
    return [
        # Mega Caps - Extrema liquidez (volúmenes diarios de $1B+)
        'AAPL',  # Apple - Volumen diario ~$7B, spread típico <0.01%
        'MSFT',  # Microsoft - Volumen diario ~$6B, alta respuesta a patrones técnicos
        'AMZN',  # Amazon - Volumen diario ~$5B, alta volatilidad intradiaria
        'GOOGL', # Alphabet - Volumen diario ~$3B, movimientos suaves
        'META',  # Meta Platforms - Volumen diario ~$4B, reacciona bien a soportes/resistencias
        'NVDA',  # NVIDIA - Volumen diario ~$12B, alta sensibilidad a indicadores técnicos
        'TSLA',  # Tesla - Volumen diario ~$10B, extrema volatilidad para señales técnicas
        
        # Large Caps - Muy alta liquidez (volúmenes diarios $500M-$1B+)
        'AMD',   # Advanced Micro Devices - Excelente para seguir momentum
        'AVGO',  # Broadcom - Movimientos técnicos bien definidos
        'QCOM',  # Qualcomm - Responde bien a soportes/resistencias clave
        'INTC',  # Intel - Alta liquidez con volatilidad controlada
        'CRM',   # Salesforce - Patrones técnicos claros
        'CSCO',  # Cisco Systems - Movimientos predecibles con buen volumen
        'PEP',   # PepsiCo - Baja volatilidad, ideal para operaciones defensivas
        'KO',    # Coca-Cola - Alta liquidez con movimientos estables
        
        # Sectores clave con alta liquidez y volatilidad ideal
        'JPM',   # JPMorgan Chase - Líder financiero con excelente liquidez
        'BAC',   # Bank of America - Alta respuesta a señales MACD
        'GS',    # Goldman Sachs - Movimientos técnicos pronunciados
        'MS',    # Morgan Stanley - Clara respuesta a indicadores técnicos
        'WFC',   # Wells Fargo - Alta liquidez en sector financiero
        
        # Tecnología de alto volumen y clara respuesta a indicadores
        'ORCL',  # Oracle - Patrones técnicos definidos
        'IBM',   # IBM - Estructura técnica tradicional
        'TXN',   # Texas Instruments - Alta liquidez en semiconductores
        'PYPL',  # PayPal - Respuesta clara a Bollinger y RSI
        'ADBE',  # Adobe - Alto volumen con tendencias técnicas claras
        
        # Retail con alta liquidez
        'WMT',   # Walmart - Extrema liquidez con movimientos predecibles
        'COST',  # Costco - Responde bien a señales técnicas
        'HD',    # Home Depot - Alta liquidez con movimientos técnicos claros
        'TGT',   # Target - Buena respuesta a MACD y RSI
        
        # Salud - Estables con alto volumen
        'JNJ',   # Johnson & Johnson - Baja volatilidad, alta liquidez
        'PFE',   # Pfizer - Excelente liquidez con volatilidad moderada
        'MRK',   # Merck - Tendencias técnicas claras
        'ABT',   # Abbott Labs - Movimientos técnicos bien definidos
        
        # Energía - Alta liquidez y volatilidad controlada
        'XOM',   # Exxon Mobil - Enorme liquidez en sector energético
        'CVX',   # Chevron - Volumen alto con claras zonas de soporte/resistencia
        
        # ETFs de alta liquidez para diversificación
        'SPY',   # S&P 500 ETF - El instrumento más líquido del mercado (~$30B diarios)
        'QQQ',   # Nasdaq 100 ETF - Extrema liquidez (~$15B diarios)
        'IWM',   # Russell 2000 ETF - Alta liquidez para small caps (~$5B diarios)
        'EEM',   # Emerging Markets ETF - Liquidez internacional
        'XLK',   # Technology Sector ETF - Concentración sectorial con alta liquidez
        'XLF',   # Financial Sector ETF - Alta respuesta a indicadores técnicos
        
        # Acciones cíclicas con alta liquidez
        'CAT',   # Caterpillar - Excelente para señales técnicas
        'DE',    # Deere & Co - Liquidez alta con tendencias claras
        'BA',    # Boeing - Alta volatilidad con volumen considerable
        
        # High-Beta con liquidez extrema
        'UBER',  # Uber - Alta volatilidad con enorme volumen
        'COIN',  # Coinbase - Extrema volatilidad con alto volumen
        'CRWD',  # CrowdStrike - Movimientos técnicos pronunciados
        'SHOP',  # Shopify - Respuesta clara a Bollinger y RSI
        'SQ',    # Block (Square) - Alta volatilidad intradiaria
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