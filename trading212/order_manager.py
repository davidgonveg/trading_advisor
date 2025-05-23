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
        try:
            # Convertir símbolo de YFinance a ticker de Trading212
            trading212_ticker = TICKER_MAPPING.get(symbol, symbol)
            logger.info(f"Símbolo convertido: {symbol} -> {trading212_ticker}")
            
            # Verificar que el instrumento existe
            instrument = self.api.check_instrument(trading212_ticker)
            if not instrument:
                logger.error(f"No se encontró el instrumento {trading212_ticker}")
                return False
                
            # Obtener límites de operación
            min_quantity = instrument.get('minTradeQuantity', 0.01)
            max_quantity = instrument.get('maxOpenQuantity', 1000000)
            
            # Obtener precio actual
            current_price = data['Close'].iloc[-1]
            
            # Obtener información de efectivo
            cash_info = self.api.get_account_cash()
            if not cash_info:
                logger.error("No se pudo obtener información de efectivo")
                return False
            
            available_cash = cash_info.get('free', 0)
            
            # Calcular cantidad a comprar
            allocation = available_cash * (CAPITAL_ALLOCATION_PERCENT / 100)
            quantity = min(max(min_quantity, round(allocation / current_price, 2)), max_quantity)
            
            # Validación mínima
            if quantity * current_price < MIN_ORDER_VALUE_USD:
                logger.warning(f"Valor de orden insuficiente: ${quantity * current_price:.2f} < ${MIN_ORDER_VALUE_USD}")
                return False
            
            # Ejecutar orden
            logger.info(f"Ejecutando compra de {quantity} {trading212_ticker} a ${current_price:.2f}")
            order_result = self.api.place_market_order(ticker=trading212_ticker, quantity=quantity)
            
            # Resto del código igual...
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
            
            # Convertir símbolo de YFinance a ticker de Trading212
            trading212_ticker = TICKER_MAPPING.get(symbol, symbol)
            
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
            logger.info(f"Ejecutando venta de {quantity} {symbol} a ${current_price:.2f}")
            order_result = self.api.place_market_order(ticker=trading212_ticker, quantity=-quantity)
            
            if not order_result:
                logger.error(f"Error al ejecutar orden de venta para {symbol}")
                return False
            
            order_id = order_result.get('id')
            
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