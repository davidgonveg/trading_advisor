"""
Gestor de órdenes mejorado para Trading212.
Maneja la ejecución de órdenes de compra y venta con mejor manejo de errores.
"""
import time
import datetime
import pandas as pd
from utils.logger import logger
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
        self.daily_order_count = 0
        self.last_order_reset = datetime.datetime.now().date()
        
        # Inicializar con datos actuales si está habilitado
        if ENABLE_TRADING and not SIMULATION_MODE:
            self._refresh_positions()
    
    def execute_entry(self, symbol, data):
        """
        Ejecuta una orden de entrada (compra).
        
        Args:
            symbol: Símbolo de la acción en formato YFinance
            data: DataFrame con datos actualizados
            
        Returns:
            bool: True si la orden se ejecutó con éxito
        """
        try:
            # Verificar si ya hay una posición activa para este símbolo
            if symbol in self.active_positions:
                logger.info(f"Ya existe una posición activa para {symbol}")
                return False
            
            # Verificar límite diario de órdenes
            if self._check_daily_order_limit():
                logger.warning(f"Límite diario de órdenes alcanzado ({MAX_ORDERS_PER_DAY})")
                return False
                
            # Convertir símbolo de YFinance a ticker de Trading212
            trading212_ticker = TICKER_MAPPING.get(symbol, symbol)
            logger.info(f"Símbolo convertido: {symbol} -> {trading212_ticker}")
            
            # Obtener precio actual
            if data is None or data.empty:
                logger.error(f"Datos vacíos para {symbol}")
                return False
                
            try:
                current_price = float(data['Close'].iloc[-1])
                logger.info(f"Precio actual de {symbol}: ${current_price:.2f}")
            except (KeyError, IndexError, ValueError) as e:
                logger.error(f"Error al obtener precio actual de {symbol}: {e}")
                return False
            
            # Obtener información de efectivo
            cash_info = self.api.get_account_cash()
            if not cash_info:
                logger.error("No se pudo obtener información de efectivo")
                return False
            
            available_cash = cash_info.get('free', 0)
            logger.info(f"Efectivo disponible: ${available_cash:.2f}")
            
            # Verificar instrumento y límites
            try:
                # Obtener todos los instrumentos
                instruments = self.api.get_instruments()
                
                if not instruments:
                    logger.error("No se pudieron obtener instrumentos")
                    return False
                
                # Buscar el instrumento por ticker
                instrument_found = False
                min_quantity = 0.01
                max_quantity = 1000
                
                for instrument in instruments:
                    if instrument.get('ticker') == trading212_ticker:
                        instrument_found = True
                        min_quantity = instrument.get('minTradeQuantity', 0.01)
                        max_quantity = instrument.get('maxOpenQuantity', 1000)
                        logger.info(f"Instrumento encontrado: {instrument.get('name')} - Min: {min_quantity}, Max: {max_quantity}")
                        break
                
                if not instrument_found:
                    logger.error(f"No se encontró el instrumento {trading212_ticker}")
                    return False
            except Exception as e:
                logger.error(f"Error al verificar instrumento {trading212_ticker}: {e}")
                # Usar valores por defecto si hay error
                min_quantity = 0.01
                max_quantity = 1000
            
            # Calcular cantidad a comprar basada en el capital disponible
            allocation = available_cash * (CAPITAL_ALLOCATION_PERCENT / 100)
            quantity = allocation / current_price
            
            # Ajustar a los límites
            quantity = max(min_quantity, min(quantity, max_quantity))
            
            # Redondear a 2 decimales (o 4 para acciones de menor valor)
            if current_price < 50:
                quantity = round(quantity, 4)
            else:
                quantity = round(quantity, 2)
            
            # Validación de valor mínimo
            order_value = quantity * current_price
            if order_value < MIN_ORDER_VALUE_USD:
                logger.warning(f"Valor de orden insuficiente: ${order_value:.2f} < ${MIN_ORDER_VALUE_USD}")
                
                # Ajustar cantidad para cumplir con el valor mínimo
                if current_price > 0:
                    adjusted_quantity = MIN_ORDER_VALUE_USD / current_price
                    adjusted_quantity = max(min_quantity, min(adjusted_quantity, max_quantity))
                    
                    if adjusted_quantity > 0:
                        quantity = adjusted_quantity
                        if current_price < 50:
                            quantity = round(quantity, 4)
                        else:
                            quantity = round(quantity, 2)
                        
                        logger.info(f"Cantidad ajustada para valor mínimo: {quantity}")
                    else:
                        logger.error(f"No se puede ajustar la cantidad para cumplir con el valor mínimo")
                        return False
                else:
                    logger.error("Precio actual es cero o negativo")
                    return False
            
            # Registrar la hora de la orden
            order_time = datetime.datetime.now()
            
            # Modo simulación vs modo real
            if SIMULATION_MODE:
                logger.info(f"[SIMULACIÓN] Comprando {quantity} unidades de {symbol} a ${current_price:.2f}")
                
                # Simular una orden exitosa
                order_id = int(time.time())  # ID ficticio
                
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
                
                # Actualizar posiciones activas
                self.active_positions[symbol] = {
                    'quantity': quantity,
                    'entry_price': current_price,
                    'entry_time': order_time,
                    'simulated': True
                }
                
                # Incrementar contador de órdenes diarias
                self._increment_daily_order_count()
                
                logger.info(f"[SIMULACIÓN] Orden de compra simulada para {symbol}: {quantity} a ${current_price:.2f}")
                return True
            else:
                # Modo real: ejecutar la orden a través de la API
                logger.info(f"Ejecutando compra de {quantity} {trading212_ticker} a ${current_price:.2f}")
                
                order_result = self.api.place_market_order(ticker=trading212_ticker, quantity=quantity)
                
                if not order_result:
                    logger.error(f"Error al ejecutar orden de compra para {symbol}")
                    return False
                
                order_id = order_result.get('id')
                
                # Esperar a que la orden se complete
                if not self._wait_for_order_completion(order_id):
                    logger.warning(f"La orden {order_id} no se completó en el tiempo esperado")
                
                # Registrar en el historial
                self.order_history.append({
                    'symbol': symbol,
                    'action': 'BUY',
                    'quantity': quantity,
                    'price': current_price,
                    'time': order_time,
                    'order_id': order_id,
                    'simulated': False
                })
                
                # Actualizar posiciones activas
                self.active_positions[symbol] = {
                    'quantity': quantity,
                    'entry_price': current_price,
                    'entry_time': order_time,
                    'simulated': False
                }
                
                # Incrementar contador de órdenes diarias
                self._increment_daily_order_count()
                
                logger.info(f"Orden de compra ejecutada para {symbol}: {quantity} a ${current_price:.2f}")
                return True
                
        except Exception as e:
            logger.error(f"Error al ejecutar entrada para {symbol}: {e}")
            import traceback
            logger.error(traceback.format_exc())
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
            
            # Verificar límite diario de órdenes
            if self._check_daily_order_limit():
                logger.warning(f"Límite diario de órdenes alcanzado ({MAX_ORDERS_PER_DAY})")
                return False
            
            # Convertir símbolo de YFinance a ticker de Trading212
            trading212_ticker = TICKER_MAPPING.get(symbol, symbol)
            
            # Obtener precio actual
            try:
                current_price = float(data['Close'].iloc[-1])
                logger.info(f"Precio actual de {symbol}: ${current_price:.2f}")
            except (KeyError, IndexError, ValueError) as e:
                logger.error(f"Error al obtener precio actual de {symbol}: {e}")
                return False
            
            # Obtener cantidad a vender
            position = self.active_positions[symbol]
            quantity = position['quantity']
            
            # Asegurar que la cantidad sea positiva
            if quantity <= 0:
                logger.error(f"Cantidad a vender inválida para {symbol}: {quantity}")
                return False
            
            # Registrar la hora de la orden
            order_time = datetime.datetime.now()
            
            # Calcular resultado
            entry_price = position['entry_price']
            profit_loss_pct = (current_price / entry_price - 1) * 100
            
            # Modo simulación vs modo real
            if position.get('simulated', False) or SIMULATION_MODE:
                logger.info(f"[SIMULACIÓN] Vendiendo {quantity} unidades de {symbol} a ${current_price:.2f}")
                
                # Simular una orden exitosa
                order_id = int(time.time())  # ID ficticio
                
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
                
                # Incrementar contador de órdenes diarias
                self._increment_daily_order_count()
                
                logger.info(f"[SIMULACIÓN] Orden de venta simulada para {symbol}: {quantity} a ${current_price:.2f}, P/L: {profit_loss_pct:.2f}%, Razón: {reason}")
                return True
            else:
                # Modo real: ejecutar la orden a través de la API
                logger.info(f"Ejecutando venta de {quantity} {trading212_ticker} a ${current_price:.2f}")
                
                # En Trading212 las ventas se realizan con cantidad negativa
                sell_quantity = -abs(quantity)
                
                order_result = self.api.place_market_order(ticker=trading212_ticker, quantity=sell_quantity)
                
                if not order_result:
                    logger.error(f"Error al ejecutar orden de venta para {symbol}")
                    return False
                
                order_id = order_result.get('id')
                
                # Esperar a que la orden se complete
                if not self._wait_for_order_completion(order_id):
                    logger.warning(f"La orden {order_id} no se completó en el tiempo esperado")
                
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
                    'simulated': False
                })
                
                # Eliminar de posiciones activas
                del self.active_positions[symbol]
                
                # Incrementar contador de órdenes diarias
                self._increment_daily_order_count()
                
                logger.info(f"Orden de venta ejecutada para {symbol}: {quantity} a ${current_price:.2f}, P/L: {profit_loss_pct:.2f}%, Razón: {reason}")
                return True
            
        except Exception as e:
            logger.error(f"Error al ejecutar salida para {symbol}: {e}")
            import traceback
            logger.error(traceback.format_exc())
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
                        'entry_time': datetime.datetime.now(),  # No hay timestamp en API, usar actual
                        'pl_percent': position.get('ppl', 0),
                        'simulated': False
                    }
            
            self.active_positions = new_positions
            logger.info(f"Posiciones actualizadas: {len(self.active_positions)} activas")
            
        except Exception as e:
            logger.error(f"Error al actualizar posiciones: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    def _increment_daily_order_count(self):
        """Incrementa el contador diario de órdenes."""
        # Verificar si es un nuevo día
        today = datetime.datetime.now().date()
        if today > self.last_order_reset:
            self.daily_order_count = 0
            self.last_order_reset = today
            logger.info(f"Reseteo del contador diario de órdenes para {today}")
        
        # Incrementar contador
        self.daily_order_count += 1
        logger.info(f"Contador diario de órdenes: {self.daily_order_count}/{MAX_ORDERS_PER_DAY}")
    
    def _check_daily_order_limit(self):
        """
        Verifica si se ha alcanzado el límite diario de órdenes.
        
        Returns:
            bool: True si se ha alcanzado el límite
        """
        # Verificar si es un nuevo día
        today = datetime.datetime.now().date()
        if today > self.last_order_reset:
            self.daily_order_count = 0
            self.last_order_reset = today
        
        # Verificar límite
        return self.daily_order_count >= MAX_ORDERS_PER_DAY
    
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
            
            sim_tag = " [SIMULACIÓN]" if position.get('simulated', False) else ""
            pl_str = f", P/L: {position.get('pl_percent', 0):.2f}%" if 'pl_percent' in position else ""
                
            summary += f"- {symbol}: {position['quantity']} @ ${position.get('entry_price', 0):.2f}, Entrada: {time_str}{pl_str}{sim_tag}\n"
        
        # Añadir contador de órdenes diarias
        summary += f"\nÓrdenes hoy: {self.daily_order_count}/{MAX_ORDERS_PER_DAY}"
        
        return summary
    
    def reset(self):
        """
        Reinicia el gestor de órdenes, limpiando historial y posiciones activas.
        Útil para pruebas o reinicio del sistema.
        """
        logger.info("Reiniciando gestor de órdenes")
        self.order_history.clear()
        self.active_positions.clear()
        self.daily_order_count = 0
        self.last_order_reset = datetime.datetime.now().date()
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