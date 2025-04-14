# Exporta funciones principales
"""
Módulo de integración con Trading212 para ejecutar operaciones basadas en el sistema de alertas.
"""
from .api import Trading212API
from .config import (
    API_KEY, 
    API_URL, 
    TICKER_MAPPING, 
    SIMULATION_MODE, 
    ENABLE_TRADING
)
from .order_manager import OrderManager
from .strategy import TradingStrategy
from utils.logger import logger

# Instancia global de la API
_api_client = None

# Instancia global del gestor de órdenes
_order_manager = None

# Instancia global de la estrategia
_strategy = None

def initialize(api_key=None, api_url=None):
    """
    Inicializa el módulo de Trading212.
    
    Args:
        api_key: Clave API para Trading212 (opcional, usa el valor de config si no se proporciona)
        api_url: URL base de Trading212 (opcional, usa el valor de config si no se proporciona)
        
    Returns:
        bool: True si la inicialización fue exitosa
    """
    global _api_client, _order_manager, _strategy
    
    try:
        # Usar valores proporcionados o los de configuración
        key = api_key or API_KEY
        url = api_url or API_URL
        
        # Verificar si la clave API está configurada
        if not key:
            logger.error("Se requiere una clave API para Trading212")
            return False
        
        # Crear cliente API
        _api_client = Trading212API(key, url)
        
        # Verificar conexión
        account_info = _api_client.get_account_info()
        if not account_info:
            logger.error("No se pudo conectar a Trading212")
            return False
        
        logger.info(f"Conectado a Trading212: ID de cuenta {account_info.get('id')}")
        
        # Crear gestor de órdenes
        _order_manager = OrderManager(_api_client)
        
        # Crear estrategia
        _strategy = TradingStrategy(_order_manager)
        
        logger.info("Módulo Trading212 inicializado correctamente")
        return True
        
    except Exception as e:
        logger.error(f"Error al inicializar módulo Trading212: {e}")
        return False

def process_alert(symbol, alert_message):
    """
    Procesa una alerta técnica y comienza el monitoreo para entrada.
    
    Args:
        symbol: Símbolo que generó la alerta
        alert_message: Mensaje de alerta
        
    Returns:
        bool: True si se inició el proceso correctamente
    """
    if not _strategy:
        logger.error("El módulo Trading212 no está inicializado")
        return False
    
    return _strategy.process_alert(symbol, alert_message)

def get_status():
    """
    Obtiene un resumen del estado actual de la estrategia.
    
    Returns:
        str: Resumen formateado del estado
    """
    if not _strategy:
        return "El módulo Trading212 no está inicializado"
    
    return _strategy.get_status_summary()

def get_order_history():
    """
    Obtiene un resumen del historial de órdenes.
    
    Returns:
        str: Resumen formateado del historial de órdenes
    """
    if not _order_manager:
        return "El módulo Trading212 no está inicializado"
    
    return _order_manager.get_order_history_summary()

def stop_all():
    """
    Detiene todos los procesos de trading activos.
    
    Returns:
        bool: True si la operación fue exitosa
    """
    if not _strategy:
        logger.error("El módulo Trading212 no está inicializado")
        return False
    
    _strategy.stop_all_processes()
    return True

def is_initialized():
    """
    Verifica si el módulo está inicializado.
    
    Returns:
        bool: True si el módulo está inicializado
    """
    return _api_client is not None and _order_manager is not None and _strategy is not None