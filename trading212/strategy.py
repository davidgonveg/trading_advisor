# Estrategias de trading
"""
Estrategia de trading que coordina todo el proceso post-alerta.
"""
import threading
import time
import datetime
from utils.logger import logger
from .monitor import AlertMonitor, PositionMonitor
from .config import SIMULATION_MODE

class TradingStrategy:
    """
    Implementa la estrategia completa de trading basada en alertas técnicas.
    Gestiona el flujo desde la alerta hasta la ejecución de órdenes y seguimiento.
    """
    
    def __init__(self, order_manager):
        """
        Inicializa la estrategia.
        
        Args:
            order_manager: Gestor de órdenes para ejecutar trades
        """
        self.order_manager = order_manager
        self.active_monitors = {}  # {symbol: monitor}
        self.active_position_monitors = {}  # {symbol: position_monitor}
        self.active_trading_threads = {}  # {symbol: thread}
    
    def process_alert(self, symbol, alert_message):
        """
        Procesa una alerta técnica y comienza el monitoreo para entrada.
        
        Args:
            symbol: Símbolo que generó la alerta
            alert_message: Mensaje de alerta (para registro)
            
        Returns:
            bool: True si se inició el proceso correctamente
        """
        try:
            logger.info(f"Procesando alerta para {symbol}")
            logger.info(f"Mensaje de alerta: {alert_message[:100]}...")
            
            # Verificar si ya existe un proceso activo para este símbolo
            if symbol in self.active_trading_threads:
                thread = self.active_trading_threads[symbol]
                if thread.is_alive():
                    logger.warning(f"Ya existe un proceso activo para {symbol}")
                    return False
            
            # Iniciar el proceso en un hilo separado
            trading_thread = threading.Thread(
                target=self._execute_trading_process,
                args=(symbol, alert_message),
                daemon=True
            )
            
            self.active_trading_threads[symbol] = trading_thread
            trading_thread.start()
            
            logger.info(f"Iniciado proceso de trading para {symbol}")
            return True
            
        except Exception as e:
            logger.error(f"Error al procesar alerta para {symbol}: {e}")
            return False
    
    def _execute_trading_process(self, symbol, alert_message):
        """
        Ejecuta el proceso completo de trading para un símbolo:
        1. Monitorea para condiciones de entrada
        2. Ejecuta entrada si se detectan las condiciones
        3. Monitorea la posición para condiciones de salida
        4. Ejecuta salida cuando corresponda
        
        Args:
            symbol: Símbolo a operar
            alert_message: Mensaje de alerta (para registro)
        """
        try:
            # Registrar inicio del proceso
            process_start_time = datetime.datetime.now()
            logger.info(f"Iniciando proceso de trading para {symbol} a las {process_start_time}")
            
            # Paso 1: Crear y ejecutar monitor de alerta para detectar entrada
            alert_monitor = AlertMonitor(symbol, self.order_manager)
            self.active_monitors[symbol] = alert_monitor
            
            # Iniciar monitoreo para entrada
            entry_detected = alert_monitor.start_monitoring()
            
            # Esperar a que termine el monitoreo de entrada
            if alert_monitor.monitor_thread:
                alert_monitor.monitor_thread.join()
            
            # Obtener última posición conocida
            has_position = symbol in self.order_manager.active_positions
            
            # Si no se detectó entrada o no hay posición, terminar
            if not has_position:
                logger.info(f"No se detectó entrada o no se ejecutó compra para {symbol}")
                del self.active_monitors[symbol]
                return
            
            # Paso 2: La posición fue abierta, iniciar monitoreo de posición
            position = self.order_manager.active_positions[symbol]
            entry_price = position['entry_price']
            
            logger.info(f"Posición abierta para {symbol} a ${entry_price:.2f}")
            
            # Crear monitor de posición
            position_monitor = PositionMonitor(symbol, entry_price, self.order_manager)
            self.active_position_monitors[symbol] = position_monitor
            
            # Iniciar monitoreo de posición
            position_monitor.start_monitoring()
            
            # Esperar a que termine el monitoreo de posición
            if position_monitor.monitor_thread:
                position_monitor.monitor_thread.join()
            
            # Paso 3: Finalizado el proceso de trading
            process_end_time = datetime.datetime.now()
            duration = (process_end_time - process_start_time).total_seconds() / 60  # en minutos
            
            logger.info(f"Finalizado proceso de trading para {symbol} en {duration:.1f} minutos")
            
            # Limpiar referencias
            if symbol in self.active_monitors:
                del self.active_monitors[symbol]
            
            if symbol in self.active_position_monitors:
                del self.active_position_monitors[symbol]
            
        except Exception as e:
            logger.error(f"Error en el proceso de trading para {symbol}: {e}")
            
            # Limpiar referencias en caso de error
            if symbol in self.active_monitors:
                self.active_monitors[symbol].stop()
                del self.active_monitors[symbol]
            
            if symbol in self.active_position_monitors:
                self.active_position_monitors[symbol].stop()
                del self.active_position_monitors[symbol]
    
    def stop_all_processes(self):
        """
        Detiene todos los procesos de trading activos.
        """
        logger.info("Deteniendo todos los procesos de trading")
        
        # Detener monitores de alerta
        for symbol, monitor in list(self.active_monitors.items()):
            monitor.stop()
            logger.info(f"Detenido monitor de alerta para {symbol}")
        
        # Detener monitores de posición
        for symbol, monitor in list(self.active_position_monitors.items()):
            monitor.stop()
            logger.info(f"Detenido monitor de posición para {symbol}")
        
        # Esperar a que terminen los hilos
        for symbol, thread in list(self.active_trading_threads.items()):
            if thread.is_alive():
                thread.join(timeout=2)
                logger.info(f"Esperando a que termine el hilo de {symbol}")
        
        # Limpiar referencias
        self.active_monitors.clear()
        self.active_position_monitors.clear()
        self.active_trading_threads.clear()
        
        logger.info("Todos los procesos de trading detenidos")
    
    def get_status_summary(self):
        """
        Obtiene un resumen del estado actual de la estrategia.
        
        Returns:
            str: Resumen formateado del estado
        """
        summary = "ESTADO DE LA ESTRATEGIA:\n"
        
        # Resumen de procesos activos
        summary += f"Procesos de trading activos: {len(self.active_trading_threads)}\n"
        summary += f"Monitores de alerta activos: {len(self.active_monitors)}\n"
        summary += f"Monitores de posición activos: {len(self.active_position_monitors)}\n"
        
        # Detalles de procesos activos
        if self.active_monitors:
            summary += "\nSímbolos en monitoreo para entrada:\n"
            for symbol in self.active_monitors:
                summary += f"- {symbol}\n"
        
        if self.active_position_monitors:
            summary += "\nSímbolos con posiciones monitoreadas:\n"
            for symbol in self.active_position_monitors:
                summary += f"- {symbol}\n"
        
        # Añadir resumen de posiciones
        position_summary = self.order_manager.get_position_summary()
        summary += f"\n{position_summary}\n"
        
        # Añadir modo de operación
        if SIMULATION_MODE:
            summary += "\nModo de operación: SIMULACIÓN (sin ejecución real de órdenes)"
        else:
            summary += "\nModo de operación: REAL (ejecutando órdenes en Trading212)"
        
        return summary