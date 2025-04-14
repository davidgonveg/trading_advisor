# Configuración específica de Trading212
"""
Configuración para la integración con Trading212 usando variables de entorno.
"""
import os
import importlib
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Credenciales API - Usando variables de entorno
API_KEY = os.getenv('TRADING212_API_KEY', '')
API_URL = os.getenv('TRADING212_API_URL', '')

# Parámetros de la estrategia
CAPITAL_ALLOCATION_PERCENT = int(os.getenv('TRADING212_CAPITAL_ALLOCATION', 90))
STOP_LOSS_PERCENT = float(os.getenv('TRADING212_STOP_LOSS_PERCENT', 1.0))
ENTRY_MONITOR_PERIOD_MINUTES = int(os.getenv('TRADING212_ENTRY_MONITOR_PERIOD', 20))
ENTRY_MONITOR_INTERVAL_SECONDS = int(os.getenv('TRADING212_ENTRY_MONITOR_INTERVAL', 60))
POSITION_MONITOR_INTERVAL_SECONDS = int(os.getenv('TRADING212_POSITION_MONITOR_INTERVAL', 15))
MAX_POSITION_DURATION_HOURS = int(os.getenv('TRADING212_MAX_POSITION_DURATION', 24))

# Lista de tickers de Trading212 mapeados desde tickers de YFinance
TICKER_MAPPING = {
    # YFinance ticker -> Trading212 ticker
    "AAPL": "AAPL_US_EQ",
    "MSFT": "MSFT_US_EQ",
    "GOOGL": "GOOGL_US_EQ",
    "AMZN": "AMZN_US_EQ",
    "META": "META_US_EQ",
    "TSLA": "TSLA_US_EQ",
    "NVDA": "NVDA_US_EQ",
    "AMD": "AMD_US_EQ",
    "PLTR": "PLTR_US_EQ",
    "ASTS": "ASTS_US_EQ",
    "SMCI": "SMCI_US_EQ",
    "ARM": "ARM_US_EQ",
    "CRWD": "CRWD_US_EQ",
    "SHOP": "SHOP_US_EQ",
    "UBER": "UBER_US_EQ",
    "SNAP": "SNAP_US_EQ",
}

# Inversión inversa del mapeo para búsquedas rápidas
REVERSE_TICKER_MAPPING = {v: k for k, v in TICKER_MAPPING.items()}

# Limites de operación para evitar problemas
MAX_ORDERS_PER_DAY = int(os.getenv('TRADING212_MAX_ORDERS_PER_DAY', 10))
MIN_ORDER_VALUE_USD = float(os.getenv('TRADING212_MIN_ORDER_VALUE', 50))

# Parámetros de MACD para determinar condiciones de entrada/salida
MACD_PEAK_DETECTION_PERIODS = int(os.getenv('TRADING212_MACD_PEAK_PERIODS', 3))

# Flags de control para habilitar/deshabilitar funcionalidades
ENABLE_TRADING = os.getenv('ENABLE_TRADING', 'False').lower() == 'true'
ENABLE_STOP_LOSS = os.getenv('ENABLE_STOP_LOSS', 'True').lower() == 'true'
SIMULATION_MODE = os.getenv('SIMULATION_MODE', 'False').lower() == 'true'

def get_stock_list():
    """
    Devuelve la lista de acciones del sistema principal.
    Se asegura de que todas las acciones tengan un mapeo definido.
    """
    try:
        # Importar la configuración del sistema principal
        main_config = importlib.import_module('config')
        
        # Obtener la lista de acciones del sistema principal
        stocks = main_config.get_stock_list()
        
        # Filtrar stocks que no tienen mapeo en Trading212
        tradeable_stocks = []
        for stock in stocks:
            if stock in TICKER_MAPPING:
                tradeable_stocks.append(stock)
            else:
                # Registrar advertencia para los stocks sin mapeo
                from utils.logger import logger
                logger.warning(f"El símbolo {stock} no tiene mapeo en Trading212 y será ignorado")
        
        return tradeable_stocks
    except (ImportError, AttributeError):
        # Si hay un error, usar una lista de respaldo
        from utils.logger import logger
        logger.warning("No se pudo importar la lista de acciones del sistema principal. Usando lista de respaldo.")
        return list(TICKER_MAPPING.keys())