"""
Funciones para obtener datos del mercado de valores usando yfinance.
Versión mejorada con manejo de rate limit y caché.
"""
import time
import datetime
import pytz
import pandas as pd
import numpy as np
import yfinance as yf
import os
import pickle
import random
from utils.logger import logger
from database.operations import get_last_data_from_db

# Directorio para caché
CACHE_DIR = "data/yfinance_cache"
os.makedirs(CACHE_DIR, exist_ok=True)

# Configuración de límites y caché
CACHE_EXPIRY = 300  # 5 minutos
MAX_RETRIES = 5
BASE_DELAY = 2.0
JITTER = 0.5
RATE_LIMIT_COOLDOWN = 60  # 1 minuto

# Estado global para manejo de límites
_last_requests = []
_in_cooldown_until = 0
_cache_hits = 0
_cache_misses = 0
_error_count = 0

def get_from_cache(symbol, period, interval):
    """
    Intenta obtener datos de la caché.
    
    Args:
        symbol: Símbolo de la acción
        period: Período de tiempo ('1d', '5d', etc.)
        interval: Intervalo entre velas ('5m', '1h', etc.)
        
    Returns:
        DataFrame con datos o None si no está en caché o ha expirado
    """
    global _cache_hits
    
    # Generar clave de caché
    cache_key = f"{symbol}_{period}_{interval}"
    cache_file = os.path.join(CACHE_DIR, f"{cache_key}.pkl")
    
    if os.path.exists(cache_file):
        try:
            file_mod_time = os.path.getmtime(cache_file)
            if time.time() - file_mod_time < CACHE_EXPIRY:
                with open(cache_file, 'rb') as f:
                    cached_data = pickle.load(f)
                logger.debug(f"Datos recuperados de caché para {symbol}")
                _cache_hits += 1
                return cached_data
            else:
                logger.debug(f"Caché expirada para {symbol}")
        except Exception as e:
            logger.warning(f"Error al leer caché para {symbol}: {e}")
    
    return None

def save_to_cache(symbol, period, interval, data):
    """
    Guarda datos en la caché.
    
    Args:
        symbol: Símbolo de la acción
        period: Período de tiempo ('1d', '5d', etc.)
        interval: Intervalo entre velas ('5m', '1h', etc.)
        data: DataFrame a guardar
        
    Returns:
        bool: True si se guardó correctamente
    """
    if data is None or data.empty:
        return False
        
    try:
        # Generar clave de caché
        cache_key = f"{symbol}_{period}_{interval}"
        cache_file = os.path.join(CACHE_DIR, f"{cache_key}.pkl")
        
        with open(cache_file, 'wb') as f:
            pickle.dump(data, f)
            
        return True
    except Exception as e:
        logger.warning(f"Error al guardar caché para {symbol}: {e}")
        return False

def can_make_request():
    """
    Verifica si podemos hacer una nueva solicitud según los límites de tasa.
    
    Returns:
        bool: True si podemos hacer una solicitud
    """
    global _last_requests, _in_cooldown_until
    
    # Si estamos en período de enfriamiento, no permitir solicitudes
    if time.time() < _in_cooldown_until:
        remain_time = _in_cooldown_until - time.time()
        logger.warning(f"En período de enfriamiento. {remain_time:.1f} segundos restantes.")
        return False
    
    # Limpiar solicitudes antiguas (más de 60 segundos)
    now = time.time()
    _last_requests = [ts for ts in _last_requests if now - ts < 60]
    
    # Permitir máximo 5 solicitudes por minuto
    return len(_last_requests) < 5

def get_current_quote(symbol):
    """
    Obtiene datos de cotización en tiempo real para un símbolo.
    
    Args:
        symbol: Símbolo de la acción
        
    Returns:
        dict: Datos de cotización o None si hay error
    """
    try:
        # Verificar caché primero
        cached_data = get_from_cache(symbol, "1d", "1m")
        if cached_data is not None and not cached_data.empty:
            # Usar el último precio disponible
            current_price = cached_data['Close'].iloc[-1]
            prev_close = cached_data['Open'].iloc[0]
            change = current_price - prev_close
            change_percent = (change / prev_close * 100) if prev_close > 0 else 0
            
            # Crear un diccionario similar al formato de Finnhub
            quote_data = {
                'c': current_price,                        # Precio actual
                'd': change,                               # Cambio
                'dp': change_percent,                      # Porcentaje de cambio
                'h': cached_data['High'].max(),            # Máximo del día
                'l': cached_data['Low'].min(),             # Mínimo del día
                'o': cached_data['Open'].iloc[0],          # Apertura del día
                'pc': prev_close                           # Cierre anterior
            }
            
            logger.info(f"Cotización obtenida de caché para {symbol} - Precio: ${current_price:.2f}")
            return quote_data
        
        # Si no está en caché, obtener datos
        logger.info(f"Solicitando cotización actual para {symbol}...")
        
        # Verificar límites de tasa
        if not can_make_request():
            logger.warning(f"No se puede solicitar cotización de {symbol} por límites de tasa")
            return None
            
        # Registrar esta solicitud
        _last_requests.append(time.time())
        
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
        
        # Crear un diccionario similar al formato de Finnhub
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
    Obtiene datos de velas usando yfinance con mejor manejo de límites y caché.
    
    Args:
        symbol: Símbolo de la acción
        period: Período de tiempo ('1d', '5d', etc.)
        interval: Intervalo de tiempo entre velas ('5m', '1h', etc.)
        from_time: Hora de inicio opcional (objeto datetime)
        
    Returns:
        DataFrame con datos OHLCV
    """
    global _last_requests, _in_cooldown_until, _cache_misses, _error_count
    
    try:
        logger.info(f"Solicitando datos de yfinance para {symbol} con período {period} e intervalo {interval}")
        
        # Verificar caché primero
        cached_data = get_from_cache(symbol, period, interval)
        if cached_data is not None:
            return cached_data
            
        _cache_misses += 1
        
        # Verificar si podemos hacer una solicitud
        if not can_make_request():
            logger.warning(f"Límites de tasa alcanzados. No se pueden obtener datos para {symbol} en este momento.")
            return pd.DataFrame()
            
        # Si se proporciona from_time, calcular período desde esa fecha
        if from_time:
            # Calcular período desde from_time hasta ahora
            now = datetime.datetime.now(pytz.UTC) if from_time.tzinfo else datetime.datetime.now()
            
            # Usar start y end en lugar de period
            start_date = from_time.strftime('%Y-%m-%d')
            
            # Añadir un retraso aleatorio para evitar sincronización
            time.sleep(random.uniform(0.1, 0.5))
            
            # Registrar esta solicitud
            _last_requests.append(time.time())
            
            # Retry loop
            for retry in range(MAX_RETRIES):
                try:
                    df = yf.download(symbol, start=start_date, interval=interval, prepost=True)
                    break
                except Exception as e:
                    # Detectar error de límite de tasa
                    if "Too Many Requests" in str(e) or "Rate limit" in str(e):
                        _error_count += 1
                        cooldown_time = BASE_DELAY * (2 ** retry)
                        logger.warning(f"¡Límite de tasa alcanzado! Enfriando por {cooldown_time} segundos...")
                        _in_cooldown_until = time.time() + cooldown_time
                        time.sleep(min(3, cooldown_time))  # Esperar un poco y dejar que otras partes del código manejen el resto
                        
                        if retry == MAX_RETRIES - 1:
                            logger.error(f"Máximo de reintentos alcanzado para {symbol}")
                            return pd.DataFrame()
                    else:
                        logger.error(f"Error en la solicitud de datos: {e}")
                        time.sleep(BASE_DELAY * (2 ** retry))
                        
                        if retry == MAX_RETRIES - 1:
                            _error_count += 1
                            return pd.DataFrame()
        else:
            # Usar period como está definido
            # Añadir un retraso aleatorio para evitar sincronización
            time.sleep(random.uniform(0.1, 0.5))
            
            # Registrar esta solicitud
            _last_requests.append(time.time())
            
            # Retry loop
            for retry in range(MAX_RETRIES):
                try:
                    df = yf.download(symbol, period=period, interval=interval, prepost=True)
                    break
                except Exception as e:
                    # Detectar error de límite de tasa
                    if "Too Many Requests" in str(e) or "Rate limit" in str(e):
                        _error_count += 1
                        cooldown_time = BASE_DELAY * (2 ** retry)
                        logger.warning(f"¡Límite de tasa alcanzado! Enfriando por {cooldown_time} segundos...")
                        _in_cooldown_until = time.time() + cooldown_time
                        time.sleep(min(3, cooldown_time))
                        
                        if retry == MAX_RETRIES - 1:
                            logger.error(f"Máximo de reintentos alcanzado para {symbol}")
                            return pd.DataFrame()
                    else:
                        logger.error(f"Error en la solicitud de datos: {e}")
                        time.sleep(BASE_DELAY * (2 ** retry))
                        
                        if retry == MAX_RETRIES - 1:
                            _error_count += 1
                            return pd.DataFrame()
        
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
        
        # Guardar en caché
        save_to_cache(symbol, period, interval, df)
        
        logger.info(f"Obtenidos {len(df)} registros para {symbol}")
        return df
        
    except Exception as e:
        _error_count += 1
        logger.error(f"Error en la solicitud de datos de yfinance para {symbol}: {e}")
        return pd.DataFrame()

def get_stock_data(symbol, period='1d', interval='5m', db_connection=None, only_new=False):
    """
    Obtiene datos recientes de una acción, combinando datos históricos de la BD y nuevos de yfinance.
    Versión mejorada con manejo de límites de tasa.
    
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

def get_rate_limit_stats():
    """
    Devuelve estadísticas del sistema de limitación de tasa.
    
    Returns:
        dict: Estadísticas de uso
    """
    global _last_requests, _in_cooldown_until, _cache_hits, _cache_misses, _error_count
    
    now = time.time()
    recent_requests = [ts for ts in _last_requests if now - ts < 60]
    
    return {
        'recent_requests': len(recent_requests),
        'in_cooldown': now < _in_cooldown_until,
        'cooldown_remaining': max(0, _in_cooldown_until - now),
        'cache_hits': _cache_hits,
        'cache_misses': _cache_misses,
        'error_count': _error_count
    }