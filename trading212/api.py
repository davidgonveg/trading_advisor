"""
Cliente API para Trading212.
Maneja la autenticación y las llamadas a la API de Trading212.
"""
import requests
import json
import time
from urllib.parse import urljoin
from utils.logger import logger

class Trading212API:
    """Cliente para la API de Trading212."""
    
    def __init__(self, api_key, base_url="https://demo.trading212.com"):
        """
        Inicializa el cliente API.
        
        Args:
            api_key: Clave API para autenticación
            base_url: URL base del entorno (demo o live)
        """
        self.api_key = api_key
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': api_key,
            'Content-Type': 'application/json'
        })
        
    def _make_request(self, method, endpoint, data=None, params=None, retry_count=3, retry_delay=1):
        """
        Realiza una solicitud a la API con reintentos.
        
        Args:
            method: Método HTTP (GET, POST, etc.)
            endpoint: Endpoint de la API
            data: Datos para solicitudes POST/PUT
            params: Parámetros de consulta
            retry_count: Número de reintentos
            retry_delay: Tiempo entre reintentos
            
        Returns:
            dict: Respuesta JSON o None si hay error
        """
        url = urljoin(self.base_url, endpoint)
        
        for i in range(retry_count):
            try:
                if method == 'GET':
                    response = self.session.get(url, params=params, timeout=10)
                elif method == 'POST':
                    response = self.session.post(url, json=data, timeout=10)
                elif method == 'DELETE':
                    response = self.session.delete(url, timeout=10)
                else:
                    logger.error(f"Método no soportado: {method}")
                    return None
                
                # Verificar límites de tasa
                if response.status_code == 429:
                    retry_after = int(response.headers.get('Retry-After', retry_delay))
                    logger.warning(f"Límite de tasa alcanzado. Esperando {retry_after} segundos")
                    time.sleep(retry_after)
                    continue
                
                # Verificar respuesta exitosa
                if response.status_code == 200:
                    return response.json() if response.content else {}
                
                # Manejar errores
                logger.error(f"Error API {response.status_code}: {response.text}")
                
                # Si hay un error de autenticación, no reintentar
                if response.status_code in (401, 403):
                    return None
                    
                # Para otros errores, reintentar
                time.sleep(retry_delay)
                
            except Exception as e:
                logger.error(f"Error de conexión: {e}")
                time.sleep(retry_delay)
        
        logger.error(f"Fallaron todos los intentos para {endpoint}")
        return None
    
    def get_account_info(self):
        """Obtiene información de la cuenta."""
        return self._make_request('GET', '/api/v0/equity/account/info')
    
    def get_account_cash(self):
        """Obtiene información del efectivo de la cuenta."""
        return self._make_request('GET', '/api/v0/equity/account/cash')
    
    def get_instruments(self):
        """Obtiene lista de instrumentos disponibles."""
        return self._make_request('GET', '/api/v0/equity/metadata/instruments')
    
    def get_portfolio(self):
        """Obtiene todas las posiciones abiertas."""
        return self._make_request('GET', '/api/v0/equity/portfolio')
    
    def get_position(self, ticker):
        """
        Obtiene una posición específica por ticker.
        
        Args:
            ticker: Identificador único del instrumento
            
        Returns:
            dict: Datos de la posición o None si no existe
        """
        data = {"ticker": ticker}
        return self._make_request('POST', '/api/v0/equity/portfolio/ticker', data=data)
    
    def place_market_order(self, ticker, quantity):
        """
        Coloca una orden de mercado.
        
        Args:
            ticker: Identificador único del instrumento
            quantity: Cantidad a comprar/vender (negativo para vender)
            
        Returns:
            dict: Detalles de la orden o None si hay error
        """
        data = {
            "ticker": ticker,
            "quantity": quantity
        }
        return self._make_request('POST', '/api/v0/equity/orders/market', data=data)
    
    def place_limit_order(self, ticker, quantity, limit_price, time_validity="DAY"):
        """
        Coloca una orden límite.
        
        Args:
            ticker: Identificador único del instrumento
            quantity: Cantidad a comprar/vender (negativo para vender)
            limit_price: Precio límite
            time_validity: Validez de la orden ('DAY' o 'GOOD_TILL_CANCEL')
            
        Returns:
            dict: Detalles de la orden o None si hay error
        """
        data = {
            "ticker": ticker,
            "quantity": quantity,
            "limitPrice": limit_price,
            "timeValidity": time_validity
        }
        return self._make_request('POST', '/api/v0/equity/orders/limit', data=data)
    
    def place_stop_order(self, ticker, quantity, stop_price, time_validity="DAY"):
        """
        Coloca una orden stop.
        
        Args:
            ticker: Identificador único del instrumento
            quantity: Cantidad a comprar/vender (negativo para vender)
            stop_price: Precio stop
            time_validity: Validez de la orden ('DAY' o 'GOOD_TILL_CANCEL')
            
        Returns:
            dict: Detalles de la orden o None si hay error
        """
        data = {
            "ticker": ticker,
            "quantity": quantity,
            "stopPrice": stop_price,
            "timeValidity": time_validity
        }
        return self._make_request('POST', '/api/v0/equity/orders/stop', data=data)
    
    def cancel_order(self, order_id):
        """
        Cancela una orden existente.
        
        Args:
            order_id: ID de la orden
            
        Returns:
            bool: True si la cancelación fue exitosa
        """
        result = self._make_request('DELETE', f'/api/v0/equity/orders/{order_id}')
        return result is not None
    
    def get_orders(self):
        """Obtiene todas las órdenes activas."""
        return self._make_request('GET', '/api/v0/equity/orders')
    
    def get_order(self, order_id):
        """
        Obtiene detalles de una orden específica.
        
        Args:
            order_id: ID de la orden
            
        Returns:
            dict: Detalles de la orden o None si no existe
        """
        return self._make_request('GET', f'/api/v0/equity/orders/{order_id}')