"""
Funciones para obtener datos del mercado de valores usando yfinance.
"""
import time
import datetime
import pytz
import pandas as pd
import numpy as np
import yfinance as yf
from utils.logger import logger
from database.operations import get_last_data_from_db

def get_current_quote(symbol):
    """
    Obtiene datos de cotización en tiempo real para un símbolo.
    
    Args:
        symbol: Símbolo de la acción
        
    Returns:
        dict: Datos de cotización o None si hay error
    """
    try:
        logger.info(f"Solicitando cotización actual para {symbol}...")
        ticker = yf.Ticker(symbol)
        
        # Obtener último precio
        last_quote = ticker.history(period="1d")
        if last_quote.empty:
            logger.warning(f"No se pudieron obtener datos para {symbol}")
            return None
            
        # Obtener precio actual (último precio disponible)
        current_price = last_quote['Close'].iloc[-1]
        
        # Obtener cambio y porcentaje de cambio
        prev_close = last_quote['Open'].iloc[0]
        change = current_price - prev_close
        change_percent = (change / prev_close * 100) if prev_close > 0 else 0
        
        # Crear un diccionario similar al formato de Finnhub para compatibilidad
        quote_data = {
            'c': current_price,                     # Precio actual
            'd': change,                            # Cambio
            'dp': change_percent,                   # Porcentaje de cambio
            'h': last_quote['High'].iloc[-1],       # Máximo del día
            'l': last_quote['Low'].iloc[-1],        # Mínimo del día
            'o': last_quote['Open'].iloc[0],        # Apertura del día
            'pc': prev_close                        # Cierre anterior
        }
        
        logger.info(f"Cotización obtenida para {symbol} - Precio: ${current_price:.2f}")
        return quote_data
        
    except Exception as e:
        logger.error(f"Error al obtener cotización para {symbol}: {e}")
        return None

def get_yfinance_candles(symbol, period='1d', interval='5m', from_time=None):
    """
    Obtiene datos de velas usando yfinance.
    
    Args:
        symbol: Símbolo de la acción
        period: Período de tiempo ('1d', '5d', etc.)
        interval: Intervalo de tiempo entre velas ('5m', '1h', etc.)
        from_time: Hora de inicio opcional (objeto datetime)
        
    Returns:
        DataFrame con datos OHLCV
    """
    try:
        logger.info(f"Solicitando datos de yfinance para {symbol} con período {period} e intervalo {interval}")
        
        # Si se proporciona from_time, calcular período desde esa fecha
        if from_time:
            # Calcular período desde from_time hasta ahora
            now = datetime.datetime.now(pytz.UTC) if from_time.tzinfo else datetime.datetime.now()
            diff = now - from_time
            
            # Usar start y end en lugar de period
            start_date = from_time.strftime('%Y-%m-%d')
            df = yf.download(symbol, start=start_date, interval=interval)
        else:
            # Usar period como está definido
            df = yf.download(symbol, period=period, interval=interval)
        
        if df.empty:
            logger.warning(f"No se devolvieron datos de yfinance para {symbol}")
            return pd.DataFrame()
            
        # CORRECCIÓN: Convertir el DataFrame a formato simple (sin multi-índice)
        # Si las columnas son un MultiIndex (como ['Open']['AAPL']), convertirlas a formato simple
        if isinstance(df.columns, pd.MultiIndex):
            # Tomar el primer nivel de las columnas que corresponde a 'Open', 'High', etc.
            df.columns = df.columns.get_level_values(0)
        
        # Asegurarse de que el índice es datetime
        df.index = pd.to_datetime(df.index)
        
        # Manejar posibles NaN o infinitos
        df = df.replace([np.inf, -np.inf], np.nan)
        df = df.dropna()
        
        logger.info(f"Obtenidos {len(df)} registros para {symbol}")
        return df
        
    except Exception as e:
        logger.error(f"Error en la solicitud de datos de yfinance para {symbol}: {e}")
        return pd.DataFrame()

def get_stock_data(symbol, period='1d', interval='5m', db_connection=None, only_new=False):
    """
    Obtiene datos recientes de una acción, combinando datos históricos de la BD y nuevos de yfinance.
    
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
            logger.info(f"Obteniendo todos los datos para {symbol} de yfinance")
            return get_yfinance_candles(symbol, period, interval)
            
        # Intentar obtener datos históricos de la BD
        historical_data = get_last_data_from_db(db_connection, symbol)
        
        if historical_data is None or historical_data.empty:
            logger.info(f"No hay datos históricos para {symbol}. Obteniendo todo de yfinance")
            return get_yfinance_candles(symbol, period, interval)
            
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
            
        # Obtener nuevos datos desde la última fecha
        logger.info(f"Obteniendo nuevos datos para {symbol} desde {last_date}")
        new_data = get_yfinance_candles(symbol, interval=interval, from_time=last_date)
        
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