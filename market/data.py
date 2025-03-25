"""
Funciones para obtener datos del mercado de valores.
"""
import time
import requests
import datetime
import pytz
import pandas as pd
import numpy as np
import json
from utils.logger import logger
from database.operations import get_last_data_from_db
from config import FINNHUB_API_KEY

def get_current_quote(symbol):
    """
    Obtiene datos de cotización en tiempo real para un símbolo.
    
    Args:
        symbol: Símbolo de la acción
        
    Returns:
        dict: Datos de cotización o None si hay error
    """
    try:
        url = f"https://finnhub.io/api/v1/quote"
        params = {
            'symbol': symbol,
            'token': FINNHUB_API_KEY
        }
        
        logger.info(f"Solicitando cotización actual para {symbol}...")
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            # Verificar que los datos no estén vacíos
            if 'c' in data and data['c'] > 0:
                logger.info(f"Cotización obtenida para {symbol} - Precio: ${data['c']}")
                return data
            else:
                logger.warning(f"Datos incompletos para {symbol}: {data}")
                return None
        else:
            logger.error(f"Error al obtener cotización: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        logger.error(f"Error al conectar con Finnhub: {e}")
        return None

def get_finnhub_candles(symbol, period='1d', interval='5m', from_time=None):
    """
    Obtiene datos de velas de la API de Finnhub.
    
    Args:
        symbol: Símbolo de la acción
        period: Período de tiempo ('1d', '5d', etc.)
        interval: Intervalo de tiempo entre velas ('5m', '1h', etc.)
        from_time: Hora de inicio opcional (objeto datetime)
        
    Returns:
        DataFrame con datos OHLCV
    """
    try:
        # Convertir periodo a segundos
        if period.endswith('d'):
            days = int(period[:-1])
            period_seconds = days * 86400
        elif period.endswith('h'):
            hours = int(period[:-1])
            period_seconds = hours * 3600
        else:
            # Por defecto 1 día si el formato es desconocido
            period_seconds = 86400
        
        # Convertir intervalo a segundos
        if interval.endswith('m'):
            interval_seconds = int(interval[:-1]) * 60
        elif interval.endswith('h'):
            interval_seconds = int(interval[:-1]) * 3600
        else:
            # Por defecto 5 minutos si el formato es desconocido
            interval_seconds = 300
        
        # Calcular tiempos de inicio y fin
        end_time = int(time.time())
        if from_time:
            # Convertir from_time a timestamp UNIX
            start_time = int(from_time.timestamp())
        else:
            start_time = end_time - period_seconds
        
        # Crear la URL de la API de Finnhub
        url = "https://finnhub.io/api/v1/stock/candle"
        
        # Mapear intervalos al formato de resolución de Finnhub
        resolution_map = {
            '1m': '1',
            '5m': '5',
            '15m': '15',
            '30m': '30',
            '1h': '60',
            '1d': 'D',
            '1w': 'W'
        }
        
        resolution = resolution_map.get(interval, '5')  # Por defecto 5m si no se encuentra
        
        params = {
            'symbol': symbol,
            'resolution': resolution,
            'from': start_time,
            'to': end_time,
            'token': FINNHUB_API_KEY
        }
        
        logger.info(f"Solicitando datos de Finnhub para {symbol} con resolución {resolution}")
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code != 200:
            logger.error(f"Error de la API de Finnhub: {response.status_code} - {response.text}")
            return pd.DataFrame()
        
        data = response.json()
        
        # Guardar datos crudos para depuración
        with open(f"data/raw_{symbol}_{resolution}.json", "w") as f:
            json.dump(data, f, indent=4)
        
        # Comprobar si los datos son válidos
        if data.get('s') == 'no_data' or 'c' not in data:
            logger.warning(f"No se devolvieron datos de Finnhub para {symbol}")
            return pd.DataFrame()
        
        # Crear DataFrame a partir de los datos de Finnhub
        df = pd.DataFrame({
            'Open': data['o'],
            'High': data['h'],
            'Low': data['l'],
            'Close': data['c'],
            'Volume': data['v']
        }, index=pd.to_datetime(data['t'], unit='s'))
        
        # Convertir índice a datetime y ordenar
        df.index = pd.to_datetime(df.index)
        df = df.sort_index()
        
        # Asegurarse de que no hay NaN o infinitos en el DataFrame
        df = df.replace([np.inf, -np.inf], np.nan)
        df = df.dropna()
        
        logger.info(f"Obtenidos {len(df)} registros para {symbol}")
        return df
        
    except Exception as e:
        logger.error(f"Error en la solicitud de datos de velas de Finnhub para {symbol}: {e}")
        return pd.DataFrame()

def get_stock_data(symbol, period='1d', interval='5m', db_connection=None, only_new=False):
    """
    Obtiene datos recientes de una acción con el intervalo especificado usando Finnhub.
    Si hay una conexión a la base de datos, intenta obtener solo datos nuevos.
    Maneja casos de gaps en los datos.
    
    Args:
        symbol: Símbolo de la acción (p. ej., 'AAPL')
        period: Período de datos ('1d', '5d', etc.)
        interval: Intervalo de tiempo entre puntos de datos ('5m', '1h', etc.)
        db_connection: Conexión opcional a la base de datos
        only_new: Si es True, intenta obtener solo datos nuevos
        
    Returns:
        DataFrame con datos de la acción
    """
    try:
        # Si no queremos usar datos históricos o no hay conexión a la BD
        if not db_connection or not only_new:
            logger.info(f"Obteniendo todos los datos para {symbol} de la API de Finnhub")
            return get_finnhub_candles(symbol, period, interval)
            
        # Intentar obtener datos históricos de la BD
        historical_data = get_last_data_from_db(db_connection, symbol)
        
        if historical_data is None or historical_data.empty:
            logger.info(f"No hay datos históricos para {symbol}. Obteniendo todo de la API de Finnhub")
            return get_finnhub_candles(symbol, period, interval)
            
        # Obtener la última fecha registrada
        last_date = historical_data.index[-1]
        
        # Calcular desde cuándo necesitamos nuevos datos
        import datetime
        import pytz
        
        # Asegurarse de que la fecha está en zona horaria UTC
        if last_date.tzinfo is None:
            last_date = pytz.UTC.localize(last_date)
            
        # Calcular el período necesario
        now = datetime.datetime.now(pytz.UTC)
        difference = now - last_date
        
        # Si la diferencia es muy pequeña, no necesitamos nuevos datos
        if difference.total_seconds() < 300:  # menos de 5 minutos
            logger.info(f"Datos ya actualizados para {symbol}. Usando solo datos históricos")
            return historical_data
            
        # Comprobar si hay un gap grande en los datos (más de 1 día)
        large_gap = difference.total_seconds() > 86400  # más de 24 horas
        
        # Ajustar el período según la diferencia
        days_difference = max(1, difference.days + 1)  # Mínimo 1 día
        
        # Si hay un gap grande o estamos en un nuevo día, solicitar datos completos
        if large_gap or last_date.date() < now.date():
            logger.info(f"Posible gap en datos para {symbol}. Obteniendo período completo")
            # Obtener un período más largo para cubrir el gap
            request_period = period if large_gap else f"{days_difference}d"
            new_data = get_finnhub_candles(symbol, request_period, interval)
        else:
            # Obtener solo los nuevos datos desde la última fecha
            logger.info(f"Obteniendo nuevos datos para {symbol} desde {last_date}")
            new_data = get_finnhub_candles(symbol, f"{days_difference}d", interval, from_time=last_date)
        
        # Filtrar solo datos posteriores a la última fecha
        if not new_data.empty:
            # Añadir un pequeño margen para evitar duplicados exactos (5 segundos)
            margin = datetime.timedelta(seconds=5)
            new_data = new_data[new_data.index > (last_date - margin)]
        
        if new_data.empty:
            logger.info(f"No hay nuevos datos para {symbol}")
            return historical_data
            
        # Combinar datos históricos con nuevos datos
        combined_data = pd.concat([historical_data, new_data])
        
        # Eliminar posibles duplicados
        combined_data = combined_data[~combined_data.index.duplicated(keep='last')]
        
        # Ordenar por fecha (importante para análisis técnico)
        combined_data = combined_data.sort_index()
        
        logger.info(f"Datos combinados para {symbol}: {len(historical_data)} históricos + {len(new_data)} nuevos")
        
        return combined_data
        
    except Exception as e:
        logger.error(f"Error al obtener datos para {symbol}: {e}")
        # Si hay un error, intentar devolver solo los datos históricos si existen
        if db_connection and only_new:
            historical_data = get_last_data_from_db(db_connection, symbol)
            if historical_data is not None and not historical_data.empty:
                logger.info(f"Usando solo datos históricos para {symbol} debido a error")
                return historical_data
        return None