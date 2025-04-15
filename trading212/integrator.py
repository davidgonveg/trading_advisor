"""
Integrador del sistema de alertas con el módulo de Trading212.
"""
import os
import sys
import time
import datetime
import threading
from utils.logger import logger
import trading212

class AlertsTrading212Integrator:
    """
    Integra el sistema de alertas con Trading212 para ejecutar operaciones
    basadas en las alertas generadas.
    """
    
    def __init__(self, api_key=None):
        """
        Inicializa el integrador.
        
        Args:
            api_key: Clave API para Trading212 (opcional)
        """
        self.initialized = False
        self.integration_enabled = False
        self.alerted_symbols = {}  # {symbol: {timestamp, message}}
        
        # Inicializar el módulo Trading212
        try:
            if api_key:
                self.initialized = trading212.initialize(api_key=api_key)
                
                if self.initialized:
                    logger.info("Integración Trading212 inicializada correctamente")
                else:
                    logger.error("Error al inicializar integración Trading212")
            else:
                logger.error("No se proporcionó API Key para Trading212")
        except Exception as e:
            logger.error(f"Error durante la inicialización de Trading212: {e}")
            self.initialized = False
        
    def enable(self):
        """Habilita la integración."""
        if not self.initialized:
            logger.error("No se puede habilitar la integración, no está inicializada")
            return False
            
        self.integration_enabled = True
        logger.info("Integración Trading212 habilitada")
        return True
        
    def disable(self):
        """Deshabilita la integración."""
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
        
        # Si la integración no está habilitada, solo registrar
        if not self.integration_enabled:
            logger.info("Integración deshabilitada, la alerta no será procesada para trading")
            return False
        
        # Enviar alerta a Trading212 para iniciar el proceso de trading
        result = trading212.process_alert(symbol, alert_message)
        
        if result:
            logger.info(f"Alerta para {symbol} enviada al sistema de trading")
        else:
            logger.error(f"Error al enviar alerta para {symbol} al sistema de trading")
        
        return result
    
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

def initialize(api_key=None):
    """
    Inicializa la integración con Trading212.
    
    Args:
        api_key: Clave API para Trading212 (opcional)
        
    Returns:
        bool: True si la inicialización fue exitosa
    """
    global _integrator
    
    # Limpiar cualquier instancia previa
    if _integrator is not None:
        logger.warning("Reinicializando la integración")
        _integrator = None
    
    # Crear nueva instancia
    try:
        _integrator = AlertsTrading212Integrator(api_key)
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
    return _integrator is not None