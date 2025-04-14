"""
Gestor de órdenes para Trading212.
Maneja la ejecución de órdenes de compra y venta.
"""
import time
import datetime
import pandas as pd
from utils.logger import logger
from .api import Trading212API
from .config import (
    CAPITAL_ALLOCATION_PERCENT,
    TICKER_MAPPING,
    REVERSE_TICKER_MAPPING,
    MIN_ORDER_VALUE_USD,
    MAX_ORDERS_PER_DAY,
    ENABLE_TRADING,
    SIMULATION_MODE
)

class OrderManager:
    """Gestor de órdenes para Trading212."""
    
    def __init__(self, api_client):
        """
        Inicializa el gestor de órdenes.
        
        Args:
            api_client: Cliente API de Trading212
        """
        self.api = api_client
        self.order_history = []
        self.active_positions = {}  # {symbol: {quantity, entry_price, entry_time}}
        
        # Inicializar con datos actuales si está habilitado
        if ENABLE_TRADING and not SIMULATION_MODE:
            self._refresh_positions()
    
    def execute_entry(self, symbol, data):
        """
        Ejecuta una orden de entrada (compra).
        
        Args:
            symbol: Símbolo YFinance
            data: DataFrame con datos actualizados
            
        Returns:
            bool: True si la orden se ejecutó con éxito
        """
        try:
            # Verificar si ya existe una posición para este símbolo
            if symbol in self.active_positions:
                logger.warning(f"Ya existe una posición activa para {symbol}")
                return False
            
            # Verificar límite de órdenes diarias
            if len(self.order_history) >= MAX_ORDERS_PER_DAY:
                logger.warning(f"Se alcanzó el límite diario de órdenes ({MAX_ORDERS_PER_DAY})")
                return False
            
            # Convertir símbolo de YFinance a ticker de Trading212
            if symbol in TICKER_MAPPING:
                trading212_ticker = TICKER_MAPPING[symbol]
            else:
                logger.error(f"No existe mapeo para el símbolo {symbol}")
                return False
            
            # Obtener precio actual
            current_price = data['Close'].iloc[-1]
            
            # Obtener disponibilidad de efectivo
            if ENABLE_TRADING and not SIMULATION_MODE:
                # Validaciones para modo real
                logger.warning(f"🚨 EJECUTANDO ORDEN DE COMPRA REAL para {symbol}")
                
                # Verificar conexión y estado de la cuenta
                account_info = self.api.get_account_info()
                if not account_info:
                    logger.error("No se pudo obtener información de la cuenta")
                    return False
                
                # Obtener información de efectivo
                cash_info = self.api.get_account_cash()
                if not cash_info:
                    logger.error("No se pudo obtener información de efectivo")
                    return False
                
                available_cash = cash_info.get('free', 0)
                
                # Verificar instrumentos disponibles
                instruments = self.api.get_instruments()
                target_instrument = next((inst for inst in instruments if inst.get('ticker') == trading212_ticker), None)
                
                if not target_instrument:
                    logger.error(f"No se encontró el instrumento para {symbol}")
                    return False
                
                # Validar mínimos y máximos de trading
                min_trade_qty = target_instrument.get('minTradeQuantity', 0.01)
                max_open_qty = target_instrument.get('maxOpenQuantity', 100)
                
                allocation = available_cash * (CAPITAL_ALLOCATION_PERCENT / 100)
                
                if allocation < MIN_ORDER_VALUE_USD:
                    logger.error(f"Fondos insuficientes. Disponible: ${allocation:.2f}")
                    return False
            else:
                # En modo simulación, usar un valor ficticio
                allocation = 10000 * (CAPITAL_ALLOCATION_PERCENT / 100)
                min_trade_qty = 0.01
                max_open_qty = 100
            
            # Calcular cantidad a comprar
            quantity = round(allocation / current_price, 6)
            
            # Validar cantidad
            if quantity < min_trade_qty:
                logger.warning(f"Cantidad {quantity} es menor que el mínimo {min_trade_qty}")
                return False
            
            if quantity > max_open_qty:
                logger.warning(f"Cantidad {quantity} excede el máximo {max_open_qty}")
                return False
            
            # Asegurar que cumple con el valor mínimo de orden
            if quantity * current_price < MIN_ORDER_VALUE_USD:
                logger.warning(f"Valor de orden insuficiente: ${quantity * current_price:.2f} < ${MIN_ORDER_VALUE_USD}")
                return False
            
            # Registrar la hora de la orden
            order_time = datetime.datetime.now()
            
            # Ejecutar orden
            if ENABLE_TRADING and not SIMULATION_MODE:
                # Usar mapeo correcto del ticker
                order_result = self.api.place_market_order(ticker=trading212_ticker, quantity=quantity)
                
                if not order_result:
                    logger.error(f"Error al ejecutar orden para {symbol}")
                    return False
                
                order_id = order_result.get('id')
                
                # Esperar confirmación de la orden
                confirmed = self._wait_for_order_completion(order_id)
                if not confirmed:
                    logger.error(f"La orden para {symbol} no se completó")
                    return False
                
                # Actualizar posiciones activas
                self._refresh_positions()
                
                # Registrar en el historial
                self.order_history.append({
                    'symbol': symbol,
                    'action': 'BUY',
                    'quantity': quantity,
                    'price': current_price,
                    'time': order_time,
                    'order_id': order_id
                })
            else:
                # Modo simulación - registrar la "orden" sin ejecutarla realmente
                logger.info(f"[SIMULACIÓN] Ejecutando compra de {quantity} {symbol} a ${current_price:.2f}")
                
                # Simular un ID de orden
                order_id = f"sim_{int(time.time())}_{symbol}"
                
                # Actualizar posiciones activas simuladas
                self.active_positions[symbol] = {
                    'quantity': quantity,
                    'entry_price': current_price,
                    'entry_time': order_time,
                    'order_id': order_id
                }
                
                # Registrar en el historial
                self.order_history.append({
                    'symbol': symbol,
                    'action': 'BUY',
                    'quantity': quantity,
                    'price': current_price,
                    'time': order_time,
                    'order_id': order_id,
                    'simulated': True
                })
            
            logger.info(f"Orden de compra ejecutada para {symbol}: {quantity} a ${current_price:.2f}")
            return True
            
        except Exception as e:
            logger.error(f"Error al ejecutar entrada para {symbol}: {e}")
            return False
    
    def execute_exit(self, symbol, data, reason=""):
        """
        Ejecuta una orden de salida (venta).
        
        Args:
            symbol: Símbolo YFinance
            data: DataFrame con datos actualizados
            reason: Razón de la salida
            
        Returns:
            bool: True si la orden se ejecutó con éxito
        """
        try:
            # Verificar si existe una posición para este símbolo
            if symbol not in self.active_positions:
                logger.warning(f"No existe posición activa para {symbol}")
                return False
            
            # Convertir símbolo de YFinance a ticker de Trading212
            if symbol in TICKER_MAPPING:
                trading212_ticker = TICKER_MAPPING[symbol]
            else:
                logger.error(f"No existe mapeo para el símbolo {symbol}")
                return False
            
            # Obtener precio actual
            current_price = data['Close'].iloc[-1]
            
            # Obtener cantidad a vender
            position = self.active_positions[symbol]
            quantity = position['quantity']
            
            # Registrar la hora de la orden
            order_time = datetime.datetime.now()
            
            # Calcular resultado
            entry_price = position['entry_price']
            profit_loss_pct = (current_price / entry_price - 1) * 100
            
            # Ejecutar orden
            if ENABLE_TRADING and not SIMULATION_MODE:
                # Usar mapeo correcto del ticker
                order_result = self.api.place_market_order(ticker=trading212_ticker, quantity=-quantity)
                
                if not order_result:
                    logger.error(f"Error al ejecutar orden de venta para {symbol}")
                    return False
                
                order_id = order_result.get('id')
                
                # Esperar confirmación de la orden
                confirmed = self._wait_for_order_completion(order_id)
                if not confirmed:
                    logger.error(f"La orden de venta para {symbol} no se completó")
                    return False
                
                # Actualizar posiciones activas
                self._refresh_positions()
                
                # Registrar en el historial
                self.order_history.append({
                    'symbol': symbol,
                    'action': 'SELL',
                    'quantity': quantity,
                    'price': current_price,
                    'time': order_time,
                    'order_id': order_id,
                    'reason': reason,
                    'profit_loss_pct': profit_loss_pct
                })
            else:
                # Modo simulación - registrar la "orden" sin ejecutarla realmente
                logger.info(f"[SIMULACIÓN] Ejecutando venta de {quantity} {symbol} a ${current_price:.2f}")
                
                # Simular un ID de orden
                order_id = f"sim_{int(time.time())}_{symbol}_exit"
                
                # Registrar en el historial
                self.order_history.append({
                    'symbol': symbol,
                    'action': 'SELL',
                    'quantity': quantity,
                    'price': current_price,
                    'time': order_time,
                    'order_id': order_id,
                    'reason': reason,
                    'profit_loss_pct': profit_loss_pct,
                    'simulated': True
                })
                
                # Eliminar de posiciones activas
                del self.active_positions[symbol]
            
            logger.info(f"Orden de venta ejecutada para {symbol}: {quantity} a ${current_price:.2f}, P/L: {profit_loss_pct:.2f}%, Razón: {reason}")
            return True
            
        except Exception as e:
            logger.error(f"Error al ejecutar salida para {symbol}: {e}")
            return False
    
    def _wait_for_order_completion(self, order_id, max_wait_seconds=60):
        """
        Espera a que una orden se complete o alcance un estado final.
        
        Args:
            order_id: ID de la orden
            max_wait_seconds: Tiempo máximo de espera en segundos
            
        Returns:
            bool: True si la orden se completó con éxito
        """
        # Estados finales
        final_states = ['FILLED', 'REJECTED', 'CANCELLED']
        start_time = time.time()
        
        while time.time() - start_time < max_wait_seconds:
            try:
                order_info = self.api.get_order(order_id)
                
                if not order_info:
                    logger.error(f"No se pudo obtener información de la orden {order_id}")
                    time.sleep(2)
                    continue
                
                status = order_info.get('status')
                
                if status == 'FILLED':
                    logger.info(f"Orden {order_id} completada con éxito")
                    return True
                
                if status in ['REJECTED', 'CANCELLED']:
                    logger.error(f"Orden {order_id} rechazada o cancelada: {status}")
                    return False
                
                # Si aún no está en un estado final, esperar y verificar nuevamente
                logger.info(f"Orden {order_id} en estado {status}, esperando...")
                time.sleep(2)
                
            except Exception as e:
                logger.error(f"Error al verificar orden {order_id}: {e}")
                time.sleep(2)
        
        logger.error(f"Tiempo de espera agotado para la orden {order_id}")
        return False
    
    def _refresh_positions(self):
        """Actualiza la lista de posiciones activas desde Trading212."""
        if not ENABLE_TRADING or SIMULATION_MODE:
            return
            
        try:
            portfolio = self.api.get_portfolio()
            
            if not portfolio:
                logger.error("No se pudo obtener el portafolio")
                return
            
            # Actualizar posiciones activas
            new_positions = {}
            
            for position in portfolio:
                ticker = position.get('ticker')
                
                # Convertir ticker de Trading212 a símbolo YFinance
                if ticker in REVERSE_TICKER_MAPPING:
                    symbol = REVERSE_TICKER_MAPPING[ticker]
                else:
                    # Si no hay mapeo, usar el ticker original
                    symbol = ticker
                
                quantity = position.get('quantity', 0)
                
                if quantity > 0:
                    new_positions[symbol] = {
                        'quantity': quantity,
                        'entry_price': position.get('averagePrice', 0),
                        'current_price': position.get('currentPrice', 0),
                        'pl_percent': position.get('ppl', 0)
                    }
            
            self.active_positions = new_positions
            logger.info(f"Posiciones actualizadas: {len(self.active_positions)} activas")
            
        except Exception as e:
            logger.error(f"Error al actualizar posiciones: {e}")
    
    def get_position_summary(self):
        """
        Obtiene un resumen de las posiciones activas.
        
        Returns:
            str: Resumen formateado de las posiciones
        """
        if not self.active_positions:
            return "No hay posiciones activas"
        
        summary = "POSICIONES ACTIVAS:\n"
        for symbol, position in self.active_positions.items():
            entry_time = position.get('entry_time', 'N/A')
            if isinstance(entry_time, datetime.datetime):
                time_str = entry_time.strftime('%Y-%m-%d %H:%M:%S')
            else:
                time_str = str(entry_time)
                
            summary += f"- {symbol}: {position['quantity']} @ ${position.get('entry_price', 0):.2f}, Entrada: {time_str}\n"
        
        return summary
    
    def reset(self):
        """
        Reinicia el gestor de órdenes, limpiando historial y posiciones activas.
        Útil para pruebas o reinicio del sistema.
        """
        logger.info("Reiniciando gestor de órdenes")
        self.order_history.clear()
        self.active_positions.clear()
        logger.info("Historial de órdenes y posiciones activas limpiados")
    
    def get_order_history_summary(self):
        """
        Obtiene un resumen del historial de órdenes.
        
        Returns:
            str: Resumen formateado del historial de órdenes
        """
        if not self.order_history:
            return "No hay historial de órdenes"
        
        summary = "HISTORIAL DE ÓRDENES:\n"
        for order in self.order_history:
            time_str = order['time'].strftime('%Y-%m-%d %H:%M:%S')
            action = order['action']
            symbol = order['symbol']
            quantity = order['quantity']
            price = order['price']
            
            summary_line = f"- {time_str}: {action} {quantity} {symbol} @ ${price:.2f}"
            
            # Añadir información de P/L para órdenes de venta
            if action == 'SELL' and 'profit_loss_pct' in order:
                pl = order['profit_loss_pct']
                reason = order.get('reason', 'N/A')
                summary_line += f", P/L: {pl:.2f}%, Razón: {reason}"
            
            # Marcar órdenes simuladas
            if order.get('simulated', False):
                summary_line += " [SIMULACIÓN]"
                
            summary += summary_line + "\n"
        
        return summary