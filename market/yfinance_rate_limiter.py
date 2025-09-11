"""
Optimizador de solicitudes a yfinance con manejo avanzado de límites de tasa.
Este módulo mejora la obtención de datos históricos minimizando las solicitudes a la API
y gestionando de forma inteligente los límites de tasa.
"""
import os
import time
import datetime
import random
import logging
import pandas as pd
import numpy as np
import yfinance as yf
from threading import Lock, Timer, Thread
from queue import PriorityQueue, Empty
import pickle
import sqlite3
from typing import Dict, List, Tuple, Optional, Union, Callable

# Configurar logger
logger = logging.getLogger('stock_alerts.yfinance_manager')

class YFinanceRateLimiter:
    """
    Gestor de límites de tasa para yfinance con caché de datos y reintentos inteligentes.
    """
    
    def __init__(self, 
                 cache_dir: str = "data/cache", 
                 cache_expiry: int = 300,  # 5 minutos en segundos
                 max_retries: int = 5,
                 base_delay: float = 2.0,
                 jitter: float = 0.5,
                 rate_limit_window: int = 60,  # Ventana de 60 segundos
                 max_requests_per_window: int = 5,  # Máximo 5 solicitudes por ventana
                 db_connection: Optional[sqlite3.Connection] = None):
        """
        Inicializa el gestor de límites de tasa.
        
        Args:
            cache_dir: Directorio para almacenar caché de datos
            cache_expiry: Tiempo de expiración de caché en segundos
            max_retries: Número máximo de reintentos ante fallos
            base_delay: Retraso base en segundos entre reintentos
            jitter: Variación aleatoria máxima para espaciar solicitudes
            rate_limit_window: Ventana de tiempo para el límite de tasa en segundos
            max_requests_per_window: Máximo de solicitudes permitidas en la ventana
            db_connection: Conexión opcional a la base de datos
        """
        self.cache_dir = cache_dir
        self.cache_expiry = cache_expiry
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.jitter = jitter
        self.rate_limit_window = rate_limit_window
        self.max_requests_per_window = max_requests_per_window
        
        self.request_timestamps = []
        self.request_lock = Lock()
        self.request_queue = PriorityQueue()
        self.active_requests = set()
        self.cooldown_until = 0
        self.db_connection = db_connection
        self.cache_hit_count = 0
        self.cache_miss_count = 0
        self.error_count = 0
        
        # Asegurar que el directorio de caché exista
        os.makedirs(cache_dir, exist_ok=True)
        
        # Iniciar el procesador de cola en un hilo separado
        self.running = True
        self.queue_processor = Thread(target=self._process_queue, daemon=True)
        self.queue_processor.start()
        
        logger.info(f"YFinanceRateLimiter inicializado con ventana de {rate_limit_window}s y máximo {max_requests_per_window} solicitudes")
    
    def get_candles(self, 
                   symbol: str, 
                   period: str = '1d', 
                   interval: str = '5m',
                   from_time: Optional[datetime.datetime] = None,
                   priority: int = 5,
                   callback: Optional[Callable] = None) -> Optional[pd.DataFrame]:
        """
        Obtiene datos de velas para un símbolo respetando los límites de tasa.
        
        Args:
            symbol: Símbolo de la acción
            period: Período de tiempo ('1d', '5d', etc.)
            interval: Intervalo entre velas ('5m', '1h', etc.)
            from_time: Hora de inicio opcional (objeto datetime)
            priority: Prioridad de la solicitud (1-10, donde 1 es la más alta)
            callback: Función a llamar con los resultados cuando estén disponibles
            
        Returns:
            DataFrame con datos OHLCV o None si hay error y no hay callback
        """
        # Intentar obtener de caché primero
        cached_data = self._get_from_cache(symbol, period, interval, from_time)
        if cached_data is not None:
            self.cache_hit_count += 1
            logger.debug(f"Cache hit para {symbol} - usando datos en caché")
            
            if callback:
                callback(cached_data)
            return cached_data
        
        self.cache_miss_count += 1
        
        # Si se proporcionó un callback, encolar la solicitud y retornar
        if callback:
            self._queue_request(symbol, period, interval, from_time, priority, callback)
            return None
        
        # Si no hay callback, ejecutar de forma síncrona y bloquear hasta tener resultado
        result_container = []
        event = Lock()
        event.acquire()
        
        def sync_callback(data):
            result_container.append(data)
            event.release()
        
        self._queue_request(symbol, period, interval, from_time, priority, sync_callback)
        event.acquire()  # Esperar a que se complete la solicitud
        event.release()  # Liberar el lock
        
        return result_container[0] if result_container else None
    
    def _get_from_cache(self, 
                       symbol: str, 
                       period: str, 
                       interval: str,
                       from_time: Optional[datetime.datetime]) -> Optional[pd.DataFrame]:
        """
        Intenta obtener datos de la caché.
        
        Args:
            symbol: Símbolo de la acción
            period: Período de tiempo ('1d', '5d', etc.)
            interval: Intervalo entre velas ('5m', '1h', etc.)
            from_time: Hora de inicio opcional (objeto datetime)
            
        Returns:
            DataFrame con datos o None si no está en caché o ha expirado
        """
        # Intentar primero obtener de base de datos si tenemos conexión
        if self.db_connection and from_time is None:
            try:
                from database.operations import get_last_data_from_db
                db_data = get_last_data_from_db(self.db_connection, symbol, limit=200)
                
                if db_data is not None and not db_data.empty:
                    last_data_time = db_data.index[-1]
                    current_time = pd.Timestamp.now(tz=last_data_time.tz)
                    data_age = (current_time - last_data_time).total_seconds()
                    
                    if data_age < self.cache_expiry:
                        logger.debug(f"Usando datos de BD para {symbol} (de hace {data_age:.1f} segundos)")
                        return db_data
            except Exception as e:
                logger.warning(f"Error al obtener datos de BD para {symbol}: {e}")
        
        # Si no se pudo obtener de BD, intentar con caché en disco
        cache_key = self._get_cache_key(symbol, period, interval, from_time)
        cache_file = os.path.join(self.cache_dir, f"{cache_key}.pkl")
        
        if os.path.exists(cache_file):
            try:
                file_mod_time = os.path.getmtime(cache_file)
                if time.time() - file_mod_time < self.cache_expiry:
                    with open(cache_file, 'rb') as f:
                        cached_data = pickle.load(f)
                    logger.debug(f"Datos recuperados de caché en disco para {symbol}")
                    return cached_data
                else:
                    logger.debug(f"Caché expirada para {symbol} (edad: {time.time() - file_mod_time:.1f}s)")
            except Exception as e:
                logger.warning(f"Error al leer caché para {symbol}: {e}")
        
        return None
    
    def _save_to_cache(self, 
                      symbol: str, 
                      period: str, 
                      interval: str,
                      from_time: Optional[datetime.datetime],
                      data: pd.DataFrame) -> bool:
        """
        Guarda datos en la caché.
        
        Args:
            symbol: Símbolo de la acción
            period: Período de tiempo ('1d', '5d', etc.)
            interval: Intervalo entre velas ('5m', '1h', etc.)
            from_time: Hora de inicio opcional (objeto datetime)
            data: DataFrame a guardar
            
        Returns:
            bool: True si se guardó correctamente
        """
        if data is None or data.empty:
            return False
            
        try:
            # Guardar en BD si hay conexión
            if self.db_connection:
                try:
                    from database.operations import save_historical_data
                    save_historical_data(self.db_connection, symbol, data)
                except Exception as e:
                    logger.warning(f"Error al guardar datos de {symbol} en BD: {e}")
            
            # Guardar también en disco como respaldo
            cache_key = self._get_cache_key(symbol, period, interval, from_time)
            cache_file = os.path.join(self.cache_dir, f"{cache_key}.pkl")
            
            with open(cache_file, 'wb') as f:
                pickle.dump(data, f)
                
            return True
        except Exception as e:
            logger.warning(f"Error al guardar caché para {symbol}: {e}")
            return False
    
    def _get_cache_key(self, 
                      symbol: str, 
                      period: str, 
                      interval: str,
                      from_time: Optional[datetime.datetime]) -> str:
        """
        Genera una clave única para la caché.
        
        Args:
            symbol: Símbolo de la acción
            period: Período de tiempo ('1d', '5d', etc.)
            interval: Intervalo entre velas ('5m', '1h', etc.)
            from_time: Hora de inicio opcional (objeto datetime)
            
        Returns:
            str: Clave única para la caché
        """
        if from_time:
            from_time_str = from_time.strftime('%Y%m%d%H%M')
            return f"{symbol}_{period}_{interval}_{from_time_str}"
        else:
            return f"{symbol}_{period}_{interval}"
    
    def _queue_request(self, 
                      symbol: str, 
                      period: str, 
                      interval: str,
                      from_time: Optional[datetime.datetime],
                      priority: int,
                      callback: Callable) -> None:
        """
        Añade una solicitud a la cola con la prioridad especificada.
        
        Args:
            symbol: Símbolo de la acción
            period: Período de tiempo ('1d', '5d', etc.)
            interval: Intervalo entre velas ('5m', '1h', etc.)
            from_time: Hora de inicio opcional (objeto datetime)
            priority: Prioridad de la solicitud (1-10, donde 1 es la más alta)
            callback: Función a llamar con los resultados
        """
        # Generar un ID único para la solicitud
        request_id = f"{symbol}_{time.time()}_{random.randint(1000, 9999)}"
        
        # Añadir a la cola con prioridad
        self.request_queue.put((priority, request_id, {
            'symbol': symbol,
            'period': period,
            'interval': interval,
            'from_time': from_time,
            'callback': callback,
            'timestamp': time.time()
        }))
        
        logger.debug(f"Solicitud para {symbol} encolada con prioridad {priority}")
    
    def _process_queue(self) -> None:
        """
        Procesa la cola de solicitudes respetando los límites de tasa.
        Se ejecuta en un hilo separado.
        """
        while self.running:
            try:
                # Verificar si estamos en período de enfriamiento por límite de tasa
                if time.time() < self.cooldown_until:
                    sleep_time = self.cooldown_until - time.time() + 1
                    logger.debug(f"En enfriamiento por límite de tasa. Esperando {sleep_time:.1f}s")
                    time.sleep(sleep_time)
                    continue
                
                # Verificar si podemos hacer una nueva solicitud
                if not self._can_make_request():
                    # Esperar tiempo adaptativo basado en el número de solicitudes recientes
                    wait_time = self._calculate_wait_time()
                    logger.debug(f"Esperando {wait_time:.1f}s para respetar límites de tasa")
                    time.sleep(wait_time)
                    continue
                
                # Obtener la siguiente solicitud con mayor prioridad
                try:
                    _, request_id, request = self.request_queue.get(block=True, timeout=1)
                except Empty:
                    # No hay solicitudes, esperar un poco
                    time.sleep(0.5)
                    continue
                
                # Marcar como activa
                self.active_requests.add(request_id)
                
                # Extraer parámetros
                symbol = request['symbol']
                period = request['period']
                interval = request['interval']
                from_time = request['from_time']
                callback = request['callback']
                
                # Verificar caché nuevamente (podría haberse actualizado mientras esperaba)
                cached_data = self._get_from_cache(symbol, period, interval, from_time)
                if cached_data is not None:
                    logger.debug(f"Cache hit para {symbol} después de espera en cola")
                    self.cache_hit_count += 1
                    callback(cached_data)
                    self.active_requests.remove(request_id)
                    self.request_queue.task_done()
                    continue
                
                # Hacer la solicitud con reintentos
                logger.debug(f"Ejecutando solicitud para {symbol}")
                result = self._execute_request_with_retries(symbol, period, interval, from_time)
                
                # Registrar la solicitud para control de tasa
                with self.request_lock:
                    now = time.time()
                    self.request_timestamps.append(now)
                    # Limpiar timestamps antiguos
                    self.request_timestamps = [ts for ts in self.request_timestamps 
                                              if now - ts < self.rate_limit_window]
                
                if result is not None and not result.empty:
                    # Guardar en caché
                    self._save_to_cache(symbol, period, interval, from_time, result)
                
                # Llamar al callback con el resultado (incluso si es None)
                callback(result)
                
                # Marcar como completada
                self.active_requests.remove(request_id)
                self.request_queue.task_done()
                
                # Añadir un pequeño retraso aleatorio entre solicitudes
                jitter_delay = random.uniform(0, self.jitter)
                time.sleep(jitter_delay)
                
            except Exception as e:
                logger.error(f"Error en el procesador de cola: {e}")
                time.sleep(1)  # Esperar un poco antes de reintentar
    
    def _can_make_request(self) -> bool:
        """
        Verifica si podemos hacer una nueva solicitud según los límites de tasa.
        
        Returns:
            bool: True si podemos hacer una solicitud
        """
        with self.request_lock:
            now = time.time()
            # Limpiar timestamps antiguos
            self.request_timestamps = [ts for ts in self.request_timestamps 
                                      if now - ts < self.rate_limit_window]
            
            # Verificar si estamos dentro de los límites
            return len(self.request_timestamps) < self.max_requests_per_window
    
    def _calculate_wait_time(self) -> float:
        """
        Calcula el tiempo de espera adaptativo basado en la carga actual.
        
        Returns:
            float: Tiempo de espera en segundos
        """
        with self.request_lock:
            now = time.time()
            if not self.request_timestamps:
                return 0.5
            
            # Si hemos alcanzado el máximo, esperar hasta que expire la solicitud más antigua
            if len(self.request_timestamps) >= self.max_requests_per_window:
                oldest = min(self.request_timestamps)
                wait_time = max(0.5, oldest + self.rate_limit_window - now)
                return wait_time
            
            # Si estamos cerca del límite, aumentar tiempo de espera proporcionalmente
            usage_ratio = len(self.request_timestamps) / self.max_requests_per_window
            return 0.5 + (usage_ratio * self.base_delay)
    
    def _execute_request_with_retries(self,
                                     symbol: str, 
                                     period: str, 
                                     interval: str,
                                     from_time: Optional[datetime.datetime]) -> Optional[pd.DataFrame]:
        """
        Ejecuta una solicitud a yfinance con reintentos exponenciales.
        
        Args:
            symbol: Símbolo de la acción
            period: Período de tiempo ('1d', '5d', etc.)
            interval: Intervalo entre velas ('5m', '1h', etc.)
            from_time: Hora de inicio opcional (objeto datetime)
            
        Returns:
            DataFrame con datos o None si todos los reintentos fallan
        """
        retry_count = 0
        last_error = None
        
        while retry_count < self.max_retries:
            try:
                # Descargar datos históricos
                if from_time:
                    # Calcular fecha desde from_time
                    now = datetime.datetime.now(pytz.UTC) if hasattr(from_time, 'tzinfo') else datetime.datetime.now()
                    start_date = from_time.strftime('%Y-%m-%d')
                    end_date = now.strftime('%Y-%m-%d')
                    
                    logger.debug(f"Descargando datos de {symbol} desde {start_date} hasta {end_date}")
                    df = yf.download(symbol, start=start_date, end=end_date, interval=interval, prepost=True)
                else:
                    logger.debug(f"Descargando datos de {symbol} para período {period}")
                    df = yf.download(symbol, period=period, interval=interval, prepost=True)
                
                # Procesar resultado
                if df.empty:
                    logger.warning(f"yfinance devolvió DataFrame vacío para {symbol}")
                    retry_count += 1
                    time.sleep(self.base_delay * (2 ** retry_count))
                    continue
                
                # Si las columnas son un MultiIndex, convertirlas
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                
                # Asegurar que el índice es datetime
                df.index = pd.to_datetime(df.index)
                
                # Manejar posibles NaN o infinitos
                df = df.replace([np.inf, -np.inf], np.nan)
                df = df.dropna()
                
                logger.debug(f"Datos obtenidos para {symbol}: {len(df)} registros")
                return df
                
            except Exception as e:
                last_error = e
                self.error_count += 1
                
                # Detectar específicamente error de límite de tasa
                if "Too Many Requests" in str(e) or "Rate limit" in str(e):
                    logger.warning(f"¡Límite de tasa alcanzado para {symbol}! Enfriando sistema...")
                    
                    # Enfriamiento progresivo más largo
                    cooldown_time = min(30 * (2 ** retry_count), 900)  # Máximo 15 minutos
                    self.cooldown_until = time.time() + cooldown_time
                    
                    logger.warning(f"Enfriamiento de {cooldown_time} segundos iniciado")
                    time.sleep(min(3, cooldown_time))  # Esperar un poco aquí, pero no todo el tiempo
                else:
                    logger.warning(f"Error al obtener datos para {symbol}: {e}")
                
                # Espera exponencial entre reintentos
                retry_delay = self.base_delay * (2 ** retry_count)
                time.sleep(retry_delay)
                
                retry_count += 1
        
        # Si llegamos aquí, todos los reintentos fallaron
        logger.error(f"Todos los reintentos fallaron para {symbol}. Último error: {last_error}")
        return None
    
    def get_queue_stats(self) -> Dict:
        """
        Obtiene estadísticas de la cola.
        
        Returns:
            Dict: Estadísticas de uso
        """
        return {
            'queue_size': self.request_queue.qsize(),
            'active_requests': len(self.active_requests),
            'recent_requests': len(self.request_timestamps),
            'cache_hits': self.cache_hit_count,
            'cache_misses': self.cache_miss_count,
            'error_count': self.error_count,
            'in_cooldown': time.time() < self.cooldown_until,
            'cooldown_remaining': max(0, self.cooldown_until - time.time())
        }
    
    def stop(self) -> None:
        """Detiene el procesador de cola."""
        self.running = False
        if self.queue_processor.is_alive():
            self.queue_processor.join(timeout=5)
            logger.info("Procesador de cola detenido")

# Variable global para facilitar uso como singleton
_rate_limiter = None

def initialize(cache_dir="data/cache", 
               max_requests_per_minute=5, 
               db_connection=None) -> YFinanceRateLimiter:
    """
    Inicializa el gestor de límites de tasa como singleton.
    
    Args:
        cache_dir: Directorio para caché
        max_requests_per_minute: Máximo de solicitudes por minuto
        db_connection: Conexión opcional a la base de datos
        
    Returns:
        YFinanceRateLimiter: Instancia del gestor
    """
    global _rate_limiter
    
    if _rate_limiter is None:
        _rate_limiter = YFinanceRateLimiter(
            cache_dir=cache_dir,
            rate_limit_window=60,
            max_requests_per_window=max_requests_per_minute,
            db_connection=db_connection
        )
    
    return _rate_limiter

def get_stock_data(symbol, period='1d', interval='5m', db_connection=None, only_new=False):
    """
    Obtiene datos de forma optimizada utilizando el gestor de límites.
    Función compatible con la interfaz original para facilitar la integración.
    
    Args:
        symbol: Símbolo de la acción
        period: Período de tiempo ('1d', '5d', etc.)
        interval: Intervalo entre velas ('5m', '1h', etc.)
        db_connection: Conexión opcional a la base de datos
        only_new: Si es True, intenta obtener solo datos nuevos
        
    Returns:
        DataFrame con datos de la acción o None
    """
    global _rate_limiter
    
    # Inicializar el gestor si no existe
    if _rate_limiter is None:
        _rate_limiter = initialize(db_connection=db_connection)
    
    # Si tenemos DB connection y only_new es True, determinar última fecha
    from_time = None
    if db_connection and only_new:
        try:
            from database.operations import get_last_data_from_db
            historical_data = get_last_data_from_db(db_connection, symbol)
            
            if historical_data is not None and not historical_data.empty:
                # Obtener la última fecha registrada
                last_date = historical_data.index[-1]
                
                # Si last_date no tiene zona horaria, añadirla
                if last_date.tzinfo is None:
                    import pytz
                    last_date = pytz.UTC.localize(last_date)
                    
                from_time = last_date
                logger.info(f"Obteniendo nuevos datos para {symbol} desde {from_time}")
        except Exception as e:
            logger.warning(f"Error al determinar última fecha para {symbol}: {e}")
    
    # Obtener datos usando el gestor de límites
    return _rate_limiter.get_candles(symbol, period, interval, from_time)

def get_queue_stats():
    """
    Obtiene estadísticas del gestor de límites de tasa.
    
    Returns:
        Dict: Estadísticas de uso o None si no está inicializado
    """
    global _rate_limiter
    
    if _rate_limiter is None:
        return None
    
    return _rate_limiter.get_queue_stats()

def stop():
    """Detiene el gestor de límites de tasa."""
    global _rate_limiter
    
    if _rate_limiter is not None:
        _rate_limiter.stop()
        _rate_limiter = None
        logger.info("Gestor de límites de tasa detenido")

# El siguiente código se ejecuta cuando se importa este módulo
import atexit

# Registrar función para detener el gestor al salir
atexit.register(stop)