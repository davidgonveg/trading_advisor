# Sistema de monitoreo post-alerta
"""
Monitor post-alerta para detectar condiciones de entrada y salida.
"""
import time
import threading
import datetime
import pandas as pd
import numpy as np
from market.data import get_yfinance_candles
from indicators.macd import calculate_macd
from indicators.rsi import calculate_stochastic_rsi
from indicators.bollinger import calculate_bollinger
from utils.logger import logger
from .config import (
    ENTRY_MONITOR_PERIOD_MINUTES,
    ENTRY_MONITOR_INTERVAL_SECONDS,
    POSITION_MONITOR_INTERVAL_SECONDS,
    MACD_PEAK_DETECTION_PERIODS,
    STOP_LOSS_PERCENT
)

class AlertMonitor:
    """Monitorea un símbolo después de una alerta para detectar condiciones de entrada."""
    
    def __init__(self, symbol, order_manager):
        """
        Inicializa el monitor de alerta.
        
        Args:
            symbol: Símbolo a monitorear
            order_manager: Gestor de órdenes para ejecutar trades
        """
        self.symbol = symbol
        self.order_manager = order_manager
        self.stop_monitoring = False
        self.monitor_thread = None
        self.last_data = None
        
    def start_monitoring(self):
        """Inicia el monitoreo en un hilo separado."""
        if self.monitor_thread and self.monitor_thread.is_alive():
            logger.warning(f"Ya existe un monitoreo activo para {self.symbol}")
            return False
            
        self.stop_monitoring = False
        self.monitor_thread = threading.Thread(
            target=self._monitor_for_entry,
            daemon=True
        )
        self.monitor_thread.start()
        logger.info(f"Iniciado monitoreo post-alerta para {self.symbol}")
        return True
        
    def stop(self):
        """Detiene el monitoreo."""
        self.stop_monitoring = True
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=2)
            logger.info(f"Detenido monitoreo para {self.symbol}")
    
    def _monitor_for_entry(self):
        """
        Monitorea el símbolo para detectar condiciones de entrada.
        Si se cumplen las condiciones, ejecuta una orden de compra.
        """
        start_time = time.time()
        entry_detected = False
        
        # Calcular tiempo máximo de monitoreo
        end_time = start_time + (ENTRY_MONITOR_PERIOD_MINUTES * 60)
        
        logger.info(f"Monitoreando {self.symbol} para entrada durante {ENTRY_MONITOR_PERIOD_MINUTES} minutos")
        
        while not self.stop_monitoring and time.time() < end_time:
            try:
                # Obtener datos actualizados (intervalos de 5 minutos)
                data = get_yfinance_candles(self.symbol, period="1d", interval="5m")
                
                if data.empty:
                    logger.warning(f"No se pudieron obtener datos para {self.symbol}")
                    time.sleep(ENTRY_MONITOR_INTERVAL_SECONDS)
                    continue
                
                # Calcular indicadores si aún no están calculados
                complete_indicators = all(col in data.columns for col in 
                                         ['MACD', 'MACD_SIGNAL', 'RSI_K', 'BB_INFERIOR'])
                                         
                if not complete_indicators:
                    data = calculate_bollinger(data)
                    data = calculate_macd(data)
                    data = calculate_stochastic_rsi(data)
                
                self.last_data = data
                
                # Verificar condición de entrada: MACD cruza por encima de la Señal
                entry_condition = self._check_entry_condition(data)
                
                if entry_condition:
                    logger.info(f"Condición de entrada detectada para {self.symbol}")
                    entry_detected = True
                    
                    # Ejecutar orden de compra a través del gestor de órdenes
                    success = self.order_manager.execute_entry(self.symbol, data)
                    
                    if success:
                        logger.info(f"Entrada ejecutada para {self.symbol}")
                    else:
                        logger.error(f"Fallo al ejecutar entrada para {self.symbol}")
                    
                    # Terminar monitoreo de entrada
                    break
                    
                # Esperar hasta la próxima verificación
                time.sleep(ENTRY_MONITOR_INTERVAL_SECONDS)
                
            except Exception as e:
                logger.error(f"Error al monitorear {self.symbol} para entrada: {e}")
                time.sleep(ENTRY_MONITOR_INTERVAL_SECONDS)
        
        # Registro al finalizar el monitoreo
        if not entry_detected:
            if self.stop_monitoring:
                logger.info(f"Monitoreo para {self.symbol} detenido externamente")
            else:
                logger.info(f"Tiempo de monitoreo agotado para {self.symbol} sin detectar entrada")
                
        return entry_detected
    
    def _check_entry_condition(self, data):
        """
        Verifica si se cumple la condición de entrada: MACD supera a la Señal.
        
        Args:
            data: DataFrame con indicadores calculados
            
        Returns:
            bool: True si se cumple la condición de entrada
        """
        if data.empty or len(data) < 2:
            return False
            
        # Obtener los últimos dos períodos para verificar el cruce
        last_row = data.iloc[-1]
        prev_row = data.iloc[-2]
        
        # Condición de cruce MACD: MACD estaba por debajo de la señal y ahora está por encima
        macd_crossover = (prev_row['MACD'] <= prev_row['MACD_SIGNAL'] and 
                          last_row['MACD'] > last_row['MACD_SIGNAL'])
        
        # Condiciones adicionales: RSI_K por debajo de 20 y precio por debajo de BB Inferior
        rsi_condition = last_row['RSI_K'] < 20
        bollinger_condition = last_row['Close'] < last_row['BB_INFERIOR']
        
        # Para la entrada, solo necesitamos el cruce de MACD (las otras ya se verificaron en la alerta)
        return macd_crossover


class PositionMonitor:
    """Monitorea una posición abierta para detectar condiciones de salida."""
    
    def __init__(self, symbol, entry_price, order_manager):
        """
        Inicializa el monitor de posición.
        
        Args:
            symbol: Símbolo a monitorear
            entry_price: Precio de entrada
            order_manager: Gestor de órdenes para ejecutar trades
        """
        self.symbol = symbol
        self.entry_price = entry_price
        self.order_manager = order_manager
        self.stop_monitoring = False
        self.monitor_thread = None
        self.last_data = None
        self.macd_values = []  # Para detectar picos en MACD
        
    def start_monitoring(self):
        """Inicia el monitoreo en un hilo separado."""
        if self.monitor_thread and self.monitor_thread.is_alive():
            logger.warning(f"Ya existe un monitoreo activo para la posición {self.symbol}")
            return False
            
        self.stop_monitoring = False
        self.monitor_thread = threading.Thread(
            target=self._monitor_position,
            daemon=True
        )
        self.monitor_thread.start()
        logger.info(f"Iniciado monitoreo de posición para {self.symbol}")
        return True
        
    def stop(self):
        """Detiene el monitoreo."""
        self.stop_monitoring = True
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=2)
            logger.info(f"Detenido monitoreo de posición para {self.symbol}")
    
    def _monitor_position(self):
        """
        Monitorea continuamente la posición para detectar condiciones de salida.
        """
        logger.info(f"Monitoreando posición para {self.symbol}")
        
        while not self.stop_monitoring:
            try:
                # Obtener datos actualizados
                data = get_yfinance_candles(self.symbol, period="1h", interval="1m")
                
                if data.empty:
                    logger.warning(f"No se pudieron obtener datos para {self.symbol}")
                    time.sleep(POSITION_MONITOR_INTERVAL_SECONDS)
                    continue
                
                # Calcular indicadores si aún no están calculados
                data = calculate_macd(data)
                
                self.last_data = data
                current_price = data['Close'].iloc[-1]
                
                # Actualizar historial de MACD para detección de picos
                self.macd_values.append(data['MACD'].iloc[-1])
                if len(self.macd_values) > MACD_PEAK_DETECTION_PERIODS * 2:
                    self.macd_values.pop(0)
                
                # Verificar condición de stop loss
                stop_loss_price = self.entry_price * (1 - STOP_LOSS_PERCENT/100)
                stop_loss_triggered = current_price <= stop_loss_price
                
                # Verificar condición de toma de ganancias (máximo de MACD)
                take_profit_condition = self._check_macd_peak()
                
                # Si se cumple alguna condición de salida, cerrar la posición
                if stop_loss_triggered or take_profit_condition:
                    exit_reason = "Stop Loss" if stop_loss_triggered else "Toma de Ganancias"
                    logger.info(f"Condición de salida detectada para {self.symbol}: {exit_reason}")
                    
                    # Ejecutar orden de venta
                    success = self.order_manager.execute_exit(self.symbol, data, exit_reason)
                    
                    if success:
                        logger.info(f"Salida ejecutada para {self.symbol}")
                    else:
                        logger.error(f"Fallo al ejecutar salida para {self.symbol}")
                    
                    # Terminar monitoreo
                    break
                    
                # Esperar hasta la próxima verificación
                time.sleep(POSITION_MONITOR_INTERVAL_SECONDS)
                
            except Exception as e:
                logger.error(f"Error al monitorear posición {self.symbol}: {e}")
                time.sleep(POSITION_MONITOR_INTERVAL_SECONDS)
        
        logger.info(f"Finalizado monitoreo de posición para {self.symbol}")
    
    def _check_macd_peak(self):
        """
        Verifica si MACD ha alcanzado un pico.
        Un pico se detecta cuando el valor actual de MACD es menor que el anterior
        y hay suficientes valores para hacer la comparación.
        
        Returns:
            bool: True si se detecta un pico en MACD
        """
        if len(self.macd_values) < MACD_PEAK_DETECTION_PERIODS:
            return False
        
        # Verificar si el valor anterior es mayor que los valores actual y pre-anterior
        # Esto indica que hemos pasado un máximo local
        peak_values = self.macd_values[-MACD_PEAK_DETECTION_PERIODS:]
        middle_idx = len(peak_values) // 2
        
        # El valor medio debe ser mayor que los valores adyacentes para ser un pico
        is_peak = peak_values[middle_idx] > peak_values[middle_idx-1] and peak_values[middle_idx] > peak_values[middle_idx+1]
        
        return is_peak