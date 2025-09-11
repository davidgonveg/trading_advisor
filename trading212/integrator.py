"""
Integrador mejorado del sistema de alertas con el módulo de Trading212.
Corrige los problemas de inicialización y habilitación.
"""
import os
import time
import datetime
import threading
import pandas as pd
from utils.logger import logger
import trading212

class AlertsTrading212Integrator:
    """
    Integra el sistema de alertas con Trading212 para ejecutar operaciones
    basadas en las alertas generadas.
    """
    
    def __init__(self, api_key=None, api_url=None, simulation_mode=True):
        """
        Inicializa el integrador.
        
        Args:
            api_key: Clave API para Trading212 (opcional)
            api_url: URL base de Trading212 (opcional)
            simulation_mode: Si es True, usa modo simulación (por defecto: True)
        """
        self.initialized = False
        self.integration_enabled = False
        self.simulation_mode = simulation_mode
        self.alerted_symbols = {}  # {symbol: {timestamp, message}}
        self.last_initialization_attempt = 0
        
        # Inicializar el módulo Trading212
        try:
            logger.info("Intentando inicializar integración Trading212...")
            
            if not api_key:
                # Si no se proporciona API key, usar la de la configuración
                try:
                    from config import TRADING212_API_KEY, TRADING212_API_URL
                    api_key = api_key or TRADING212_API_KEY
                    api_url = api_url or TRADING212_API_URL
                except (ImportError, AttributeError):
                    pass
                
            if api_key:
                self.initialized = trading212.initialize(
                    api_key=api_key,
                    api_url=api_url,
                    simulation_mode=simulation_mode
                )
                
                if self.initialized:
                    logger.info(f"Integración Trading212 inicializada correctamente en modo {'SIMULACIÓN' if simulation_mode else 'REAL'}")
                    # Habilitar automáticamente la integración al inicializar
                    self.integration_enabled = True
                    logger.info("Integración Trading212 habilitada automáticamente")
                else:
                    logger.error("Error al inicializar integración Trading212")
            else:
                logger.error("No se proporcionó API Key para Trading212")
                
            self.last_initialization_attempt = time.time()
        except Exception as e:
            logger.error(f"Error durante la inicialización de Trading212: {e}")
            self.initialized = False
            self.integration_enabled = False
    
    def reinitialize(self, api_key=None, api_url=None, simulation_mode=None):
        """
        Reinicializa la integración con Trading212.
        
        Args:
            api_key: Clave API para Trading212 (opcional)
            api_url: URL base de Trading212 (opcional)
            simulation_mode: Si es True, usa modo simulación (opcional)
            
        Returns:
            bool: True si se reinicializó correctamente
        """
        # Limitar reintentos para evitar bloqueos de API
        current_time = time.time()
        if current_time - self.last_initialization_attempt < 60:  # Esperar al menos 60 segundos entre intentos
            logger.warning("Intento de reinicialización demasiado pronto. Esperando...")
            return False
            
        # Actualizar modo de simulación si se proporciona
        if simulation_mode is not None:
            self.simulation_mode = simulation_mode
            
        # Reinicializar el módulo
        try:
            logger.info(f"Reinicializando integración Trading212 en modo {'SIMULACIÓN' if self.simulation_mode else 'REAL'}...")
            
            # Detener procesos activos si los hay
            if self.initialized:
                try:
                    trading212.stop_all()
                    logger.info("Procesos anteriores detenidos")
                except Exception as e:
                    logger.warning(f"Error al detener procesos anteriores: {e}")
            
            # Reinicializar
            self.initialized = trading212.initialize(
                api_key=api_key,
                api_url=api_url,
                simulation_mode=self.simulation_mode
            )
            
            if self.initialized:
                logger.info("Integración Trading212 reinicializada correctamente")
                self.integration_enabled = True
                logger.info("Integración Trading212 habilitada automáticamente")
            else:
                logger.error("Error al reinicializar integración Trading212")
                
            self.last_initialization_attempt = time.time()
            return self.initialized
        except Exception as e:
            logger.error(f"Error durante la reinicialización de Trading212: {e}")
            self.initialized = False
            self.integration_enabled = False
            self.last_initialization_attempt = time.time()
            return False
        
    def enable(self):
        """
        Habilita la integración.
        
        Returns:
            bool: True si se habilitó correctamente
        """
        if not self.initialized:
            logger.error("No se puede habilitar la integración, no está inicializada")
            return False
            
        self.integration_enabled = True
        logger.info("Integración Trading212 habilitada")
        return True
        
    def disable(self):
        """
        Deshabilita la integración.
        
        Returns:
            bool: True si se deshabilitó correctamente
        """
        self.integration_enabled = False
        logger.info("Integración Trading212 deshabilitada")
        return True
    
    def handle_alert(self, symbol, alert_message):
        """
        Procesa una alerta y la envía al módulo Trading212 si la integración está habilitada.
        
        Args:
            symbol: Símbolo que generó la alerta
            alert_message: Mensaje de alerta
            
        Returns:
            bool: True si la alerta fue procesada
        """
        # Registrar la alerta
        logger.info(f"Alerta recibida para {symbol}")
        
        # Guardar la alerta en el historial
        timestamp = datetime.datetime.now()
        self.alerted_symbols[symbol] = {
            'timestamp': timestamp,
            'message': alert_message
        }
        
        # Si la integración no está habilitada o inicializada, verificar si podemos reiniciarla
        if not self.initialized or not self.integration_enabled:
            if not self.initialized:
                logger.warning(f"Integración no inicializada, intentando reinicializar para {symbol}...")
                self.reinitialize()
                
            if not self.integration_enabled and self.initialized:
                logger.warning(f"Integración deshabilitada, habilitando para {symbol}...")
                self.enable()
                
            # Verificar nuevamente si se logró habilitar
            if not self.initialized or not self.integration_enabled:
                logger.warning("Integración deshabilitada, la alerta no será procesada para trading")
                return False
        
        # Enviar alerta a Trading212 para iniciar el proceso de trading
        try:
            logger.info(f"Enviando alerta de {symbol} a Trading212...")
            result = trading212.process_alert(symbol, alert_message)
            
            if result:
                logger.info(f"Alerta para {symbol} enviada al sistema de trading")
            else:
                logger.error(f"Error al enviar alerta para {symbol} al sistema de trading")
            
            return result
        except Exception as e:
            logger.error(f"Excepción al procesar alerta para {symbol}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    def get_status(self):
        """
        Obtiene un resumen del estado actual de la integración.
        
        Returns:
            str: Resumen formateado del estado
        """
        if not self.initialized:
            return "Integración Trading212 no inicializada"
        
        status = f"ESTADO DE INTEGRACIÓN TRADING212:\n"
        status += f"Inicializada: {self.initialized}\n"
        status += f"Habilitada: {self.integration_enabled}\n"
        status += f"Modo: {'SIMULACIÓN' if self.simulation_mode else 'REAL'}\n"
        status += f"Alertas recibidas: {len(self.alerted_symbols)}\n\n"
        
        # Añadir estado de Trading212
        if self.initialized:
            status += trading212.get_status()
            status += "\n\n"
            status += trading212.get_order_history()
        
        return status
    
    def stop_all_processes(self):
        """
        Detiene todos los procesos de trading activos.
        
        Returns:
            bool: True si la operación fue exitosa
        """
        if not self.initialized:
            logger.error("Integración Trading212 no inicializada")
            return False
        
        result = trading212.stop_all()
        
        if result:
            logger.info("Todos los procesos de trading detenidos")
        else:
            logger.error("Error al detener procesos de trading")
        
        return result

# Instancia global del integrador
_integrator = None

def initialize(api_key=None, api_url=None, simulation_mode=True):
    """
    Inicializa la integración con Trading212.
    
    Args:
        api_key: Clave API para Trading212 (opcional)
        api_url: URL base de Trading212 (opcional)
        simulation_mode: Si es True, usa modo simulación (por defecto: True)
        
    Returns:
        bool: True si la inicialización fue exitosa
    """
    global _integrator
    
    # Limpiar cualquier instancia previa
    if _integrator is not None:
        logger.warning("Reinicializando la integración")
        _integrator.stop_all_processes()
        _integrator = None
    
    # Crear nueva instancia
    try:
        _integrator = AlertsTrading212Integrator(api_key, api_url, simulation_mode)
        return _integrator.initialized
    except Exception as e:
        logger.error(f"Error al inicializar la integración: {e}")
        _integrator = None
        return False

def enable_integration():
    """
    Habilita la integración.
    
    Returns:
        bool: True si la operación fue exitosa
    """
    if _integrator is None:
        logger.error("La integración no está inicializada")
        return False
    
    return _integrator.enable()

def disable_integration():
    """
    Deshabilita la integración.
    
    Returns:
        bool: True si la operación fue exitosa
    """
    if _integrator is None:
        logger.error("La integración no está inicializada")
        return False
    
    return _integrator.disable()

def process_alert(symbol, alert_message):
    """
    Procesa una alerta y la envía al módulo Trading212 si la integración está habilitada.
    
    Args:
        symbol: Símbolo que generó la alerta
        alert_message: Mensaje de alerta
        
    Returns:
        bool: True si la alerta fue procesada
    """
    if _integrator is None:
        logger.error("La integración no está inicializada")
        return False
    
    return _integrator.handle_alert(symbol, alert_message)

def get_status():
    """
    Obtiene un resumen del estado actual de la integración.
    
    Returns:
        str: Resumen formateado del estado
    """
    if _integrator is None:
        return "La integración no está inicializada"
    
    return _integrator.get_status()

def stop_all_processes():
    """
    Detiene todos los procesos de trading activos.
    
    Returns:
        bool: True si la operación fue exitosa
    """
    if _integrator is None:
        logger.error("La integración no está inicializada")
        return False
    
    return _integrator.stop_all_processes()

def is_initialized():
    """
    Verifica si la integración está inicializada.
    
    Returns:
        bool: True si la integración está inicializada
    """
    return _integrator is not None and _integrator.initialized

def get_simulation_mode():
    """
    Obtiene el modo de simulación actual.
    
    Returns:
        bool: True si está en modo simulación
    """
    if _integrator is None:
        return True  # Por defecto, asumir modo simulación
    
    return _integrator.simulation_mode