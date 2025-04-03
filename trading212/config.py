# Configuración específica de Trading212
"""
Configuración para la integración con Trading212.
"""
import os
import importlib

# Credenciales API - Deben configurarse en una instancia real
API_KEY = "37295314ZqQNNcqRhjKQBxuSEcSFIMhtvUdVU"  # Se debe establecer en una instalación real
API_URL = "https://demo.trading212.com"  # URL demo por defecto

# Parámetros de la estrategia
CAPITAL_ALLOCATION_PERCENT = 90  # Porcentaje del capital disponible para invertir
STOP_LOSS_PERCENT = 1.0  # Porcentaje de pérdida máxima permitida
ENTRY_MONITOR_PERIOD_MINUTES = 20  # Tiempo máximo para esperar condiciones de entrada
ENTRY_MONITOR_INTERVAL_SECONDS = 60  # Intervalo de verificación para entrada
POSITION_MONITOR_INTERVAL_SECONDS = 15  # Intervalo de verificación para posiciones abiertas
MAX_POSITION_DURATION_HOURS = 24  # Duración máxima de una posición (como seguridad)

# Lista de tickers de Trading212 mapeados desde tickers de YFinance
# Este mapeo es necesario porque los tickers pueden tener formatos diferentes
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
    "SHOP": "SHOP_US_EQ",  # Asumiendo que CRSP era un error y se refería a Shopify
    "UBER": "UBER_US_EQ",
    "SNAP": "SNAP_US_EQ",
    # Añadir más mappings según necesidad
}

# Inversión inversa del mapeo para búsquedas rápidas
REVERSE_TICKER_MAPPING = {v: k for k, v in TICKER_MAPPING.items()}

# Limites de operación para evitar problemas
MAX_ORDERS_PER_DAY = 10
MIN_ORDER_VALUE_USD = 50  # Valor mínimo de orden en USD

# Parámetros de MACD para determinar condiciones de entrada/salida
MACD_PEAK_DETECTION_PERIODS = 3  # Número de períodos para detectar un pico en MACD

# Flags de control para habilitar/deshabilitar funcionalidades
ENABLE_TRADING = False  # Por defecto deshabilitado por seguridad
ENABLE_STOP_LOSS = True
SIMULATION_MODE = True  # En modo simulación, no se ejecutan órdenes reales

# Reutilizar la lista de acciones del sistema principal
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