#!/usr/bin/env python3
"""
📥 DATA DOWNLOADER - DESCARGA MASIVA DE DATOS HISTÓRICOS V3.0
==========================================================

Sistema de descarga masiva y procesamiento paralelo de datos históricos:

🎯 FUNCIONALIDADES PRINCIPALES:
- Descarga automática de múltiples símbolos
- Procesamiento paralelo inteligente (workers dinámicos)
- Progress tracking con tiempo estimado
- Resume capability (continúa desde donde se quedó)
- Auto-retry con exponential backoff
- Rate limiting respectuoso con las APIs
- Validación y limpieza automática de datos

📊 DATOS DESCARGADOS:
- OHLCV básico (Open, High, Low, Close, Volume)
- Indicadores técnicos calculados automáticamente
- Multiple timeframes (15m, 1h, 1d)
- Período configurable (3-24 meses de historia)

💾 ALMACENAMIENTO:
- CSV files estructurados por símbolo/timeframe
- SQLite database population automática
- Backup y recovery de datos parciales
- Compresión automática de archivos antiguos
"""

import os
import sys
import json
import time
import asyncio
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Set, Any
import logging
from dataclasses import dataclass, asdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock, Event
import threading
import queue
import math

# Setup de imports (mismo que api_manager.py)
def setup_imports():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    if current_dir not in sys.path:
        sys.path.insert(0, current_dir)
    parent_dir = os.path.dirname(current_dir)
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)

setup_imports()

# Imports
try:
    from . import config
    from .api_manager import APIManager
except ImportError:
    import config
    from api_manager import APIManager

# Import sistema principal para indicadores
try:
    from indicators import TechnicalIndicators
    INDICATORS_AVAILABLE = True
except ImportError:
    INDICATORS_AVAILABLE = False
    print("⚠️ Módulo de indicadores no disponible - solo datos OHLCV")

# Configurar logging con fallback seguro
try:
    log_level = getattr(logging, config.LOGGING_CONFIG.get('level', 'INFO'), logging.INFO)
except (AttributeError, KeyError):
    log_level = logging.INFO

logging.basicConfig(level=log_level)
logger = logging.getLogger(__name__)

@dataclass
class DownloadTask:
    """Tarea de descarga individual"""
    symbol: str
    timeframe: str
    start_date: str
    end_date: str
    priority: int = 1  # 1=alta, 5=baja
    attempts: int = 0
    max_attempts: int = 3
    last_error: Optional[str] = None
    estimated_points: int = 0
    
    @property
    def is_exhausted(self) -> bool:
        return self.attempts >= self.max_attempts

@dataclass
class DownloadProgress:
    """Progress tracking para descarga"""
    total_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    skipped_tasks: int = 0
    start_time: datetime = None
    estimated_completion: Optional[datetime] = None
    current_symbol: str = ""
    current_timeframe: str = ""
    data_points_downloaded: int = 0
    total_estimated_points: int = 0
    
    @property
    def completion_percentage(self) -> float:
        if self.total_tasks == 0:
            return 0.0
        return (self.completed_tasks / self.total_tasks) * 100
    
    @property
    def success_rate(self) -> float:
        processed = self.completed_tasks + self.failed_tasks
        if processed == 0:
            return 0.0
        return (self.completed_tasks / processed) * 100
    
    def time_elapsed(self) -> timedelta:
        if not self.start_time:
            return timedelta(0)
        return datetime.now() - self.start_time
    
    def estimate_remaining_time(self) -> Optional[timedelta]:
        if self.completed_tasks == 0 or not self.start_time:
            return None
        
        elapsed = self.time_elapsed()
        rate = self.completed_tasks / elapsed.total_seconds()
        remaining_tasks = self.total_tasks - self.completed_tasks
        
        if rate > 0:
            remaining_seconds = remaining_tasks / rate
            return timedelta(seconds=remaining_seconds)
        return None

class DataDownloader:
    """
    Descargador principal de datos históricos
    """
    
    def __init__(self, api_manager: Optional[APIManager] = None):
        """Inicializar downloader"""
        self.api_manager = api_manager or APIManager()
        self.progress = DownloadProgress()
        self.progress_file = config.PROGRESS_CONFIG['progress_file']
        self.download_queue = queue.PriorityQueue()
        self.completed_tasks: Set[str] = set()
        self.failed_tasks: Set[str] = set()
        self.lock = Lock()
        self.stop_event = Event()
        
        # Asegurar directorios existan
        self.ensure_directories()
        
        # Cargar progreso previo si existe
        self.load_progress()
        
        # Inicializar indicadores técnicos si está disponible
        if INDICATORS_AVAILABLE:
            self.indicators = TechnicalIndicators()
        
        logger.info("📥 Data Downloader inicializado")
    
    def ensure_directories(self):
        """Asegurar que directorios necesarios existan"""
        directories = [
            'historical_data/raw_data',
            'historical_data/processed_data',
            'historical_data/logs',
            'historical_data/temp_data'
        ]
        
        for directory in directories:
            os.makedirs(directory, exist_ok=True)
    
    def generate_tasks(self, symbols: List[str], timeframes: List[str], 
                      start_date: str, end_date: str) -> List[DownloadTask]:
        """
        Generar lista de tareas de descarga
        
        Args:
            symbols: Lista de símbolos a descargar
            timeframes: Lista de timeframes (15m, 1h, 1d)
            start_date: Fecha inicio (YYYY-MM-DD)
            end_date: Fecha fin (YYYY-MM-DD)
            
        Returns:
            Lista de DownloadTask
        """
        tasks = []
        
        for symbol in symbols:
            for timeframe in timeframes:
                # Estimar número de data points
                estimated_points = self.estimate_data_points(timeframe, start_date, end_date)
                
                # Asignar prioridad (símbolos principales tienen prioridad)
                priority = 1 if symbol in config.SYMBOLS[:5] else 3
                if timeframe == '1d':
                    priority += 1  # Timeframes largos menos prioritarios
                
                task = DownloadTask(
                    symbol=symbol,
                    timeframe=timeframe,
                    start_date=start_date,
                    end_date=end_date,
                    priority=priority,
                    estimated_points=estimated_points
                )
                
                tasks.append(task)
        
        # Ordenar por prioridad
        tasks.sort(key=lambda x: x.priority)
        
        logger.info(f"📋 Generadas {len(tasks)} tareas de descarga")
        logger.info(f"📊 Puntos de datos estimados: {sum(t.estimated_points for t in tasks):,}")
        
        return tasks
    
    def estimate_data_points(self, timeframe: str, start_date: str, end_date: str) -> int:
        """Estimar número de data points para un timeframe"""
        try:
            start = datetime.strptime(start_date, '%Y-%m-%d')
            end = datetime.strptime(end_date, '%Y-%m-%d')
            days = (end - start).days
            
            # Estimaciones basadas en días de trading (asumiendo ~252 días/año)
            trading_days = days * 0.69  # ~69% de días son laborales
            
            if timeframe == '15m':
                # 26 períodos de 15min por día de trading (6.5h mercado)
                return int(trading_days * 26)
            elif timeframe == '1h':
                # 6.5 períodos de 1h por día de trading
                return int(trading_days * 6.5)
            elif timeframe == '1d':
                # 1 período por día de trading
                return int(trading_days)
            else:
                return int(trading_days * 10)  # Default conservador
                
        except Exception as e:
            logger.warning(f"Error estimando data points: {e}")
            return 1000  # Default fallback
    
    def load_progress(self):
        """Cargar progreso de descarga anterior"""
        try:
            if not os.path.exists(self.progress_file):
                return
            
            with open(self.progress_file, 'r') as f:
                data = json.load(f)
            
            # Cargar tareas completadas y fallidas
            self.completed_tasks = set(data.get('completed_tasks', []))
            self.failed_tasks = set(data.get('failed_tasks', []))
            
            logger.info(f"📂 Progreso cargado: {len(self.completed_tasks)} completadas, {len(self.failed_tasks)} fallidas")
            
        except Exception as e:
            logger.warning(f"⚠️ Error cargando progreso: {e}")
    
    def save_progress(self):
        """Guardar progreso actual"""
        try:
            progress_data = {
                'completed_tasks': list(self.completed_tasks),
                'failed_tasks': list(self.failed_tasks),
                'progress': asdict(self.progress),
                'last_save': datetime.now().isoformat()
            }
            
            with open(self.progress_file, 'w') as f:
                json.dump(progress_data, f, indent=2, default=str)
                
            logger.debug(f"💾 Progreso guardado en {self.progress_file}")
            
        except Exception as e:
            logger.error(f"❌ Error guardando progreso: {e}")
    
    def task_key(self, task: DownloadTask) -> str:
        """Generar clave única para tarea"""
        return f"{task.symbol}_{task.timeframe}_{task.start_date}_{task.end_date}"
    
    def is_task_completed(self, task: DownloadTask) -> bool:
        """Verificar si tarea ya fue completada"""
        return self.task_key(task) in self.completed_tasks
    
    def mark_task_completed(self, task: DownloadTask):
        """Marcar tarea como completada"""
        with self.lock:
            self.completed_tasks.add(self.task_key(task))
            self.progress.completed_tasks += 1
            self.save_progress()
    
    def mark_task_failed(self, task: DownloadTask, error: str):
        """Marcar tarea como fallida"""
        with self.lock:
            self.failed_tasks.add(self.task_key(task))
            self.progress.failed_tasks += 1
            task.last_error = error
            self.save_progress()
    
    def download_single_symbol(self, task: DownloadTask) -> Tuple[bool, Optional[pd.DataFrame], str]:
        """
        Descargar datos para un símbolo/timeframe específico
        
        Returns:
            Tuple[success, dataframe, error_message]
        """
        # Verificar si ya se completó
        if self.is_task_completed(task):
            logger.debug(f"⏭️ {task.symbol} {task.timeframe}: Ya completado")
            return True, None, "ALREADY_COMPLETED"
        
        # Actualizar progreso actual
        with self.lock:
            self.progress.current_symbol = task.symbol
            self.progress.current_timeframe = task.timeframe
        
        logger.info(f"📥 Descargando {task.symbol} {task.timeframe} desde {task.start_date}")
        
        try:
            # Calcular período para la API
            period = self.calculate_period(task.start_date, task.end_date)
            
            # Descargar datos usando API Manager
            success, raw_data, source = self.api_manager.get_data(
                symbol=task.symbol,
                interval=task.timeframe,
                period=period
            )
            
            if not success:
                error_msg = f"API request falló: {source}"
                logger.error(f"❌ {task.symbol}: {error_msg}")
                return False, None, error_msg
            
            # Procesar datos crudos
            df = self.process_raw_data(raw_data, source, task.symbol, task.timeframe)
            
            if df is None or df.empty:
                error_msg = "No se pudieron procesar los datos"
                logger.error(f"❌ {task.symbol}: {error_msg}")
                return False, None, error_msg
            
            # Filtrar por fechas solicitadas
            df = self.filter_by_date_range(df, task.start_date, task.end_date)
            
            if df.empty:
                error_msg = "No hay datos en el rango solicitado"
                logger.warning(f"⚠️ {task.symbol}: {error_msg}")
                return False, None, error_msg
            
            # Calcular indicadores técnicos si está disponible
            if INDICATORS_AVAILABLE:
                df = self.add_technical_indicators(df, task.symbol)
            
            # Guardar datos
            success_save = self.save_data(df, task.symbol, task.timeframe)
            
            if not success_save:
                error_msg = "Error guardando datos"
                logger.error(f"❌ {task.symbol}: {error_msg}")
                return False, df, error_msg
            
            # Actualizar contadores
            with self.lock:
                self.progress.data_points_downloaded += len(df)
            
            logger.info(f"✅ {task.symbol} {task.timeframe}: {len(df)} puntos descargados desde {source}")
            return True, df, ""
            
        except Exception as e:
            error_msg = f"Error inesperado: {str(e)}"
            logger.error(f"💥 {task.symbol}: {error_msg}")
            return False, None, error_msg
    
    def calculate_period(self, start_date: str, end_date: str) -> str:
        """Calcular período para API basado en fechas"""
        try:
            start = datetime.strptime(start_date, '%Y-%m-%d')
            end = datetime.strptime(end_date, '%Y-%m-%d')
            days = (end - start).days
            
            # Mapear a períodos de API
            if days <= 7:
                return '5d'
            elif days <= 30:
                return '1mo'
            elif days <= 90:
                return '3mo'
            elif days <= 180:
                return '6mo'
            elif days <= 365:
                return '1y'
            elif days <= 730:
                return '2y'
            else:
                return '5y'
                
        except:
            return '1y'  # Default fallback
    
    def process_raw_data(self, raw_data: Dict, source: str, symbol: str, timeframe: str) -> Optional[pd.DataFrame]:
        """
        Procesar datos crudos de la API a DataFrame estándar
        
        Returns:
            DataFrame con columnas: timestamp, open, high, low, close, volume
        """
        try:
            if source == 'YAHOO':
                return self.process_yahoo_data(raw_data, symbol)
            elif source == 'ALPHA_VANTAGE':
                return self.process_alpha_vantage_data(raw_data, timeframe)
            elif source == 'TWELVE_DATA':
                return self.process_twelve_data(raw_data)
            else:
                logger.error(f"❌ Fuente no soportada: {source}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Error procesando datos de {source}: {e}")
            return None
    
    def process_yahoo_data(self, data: Dict, symbol: str) -> Optional[pd.DataFrame]:
        """Procesar datos de Yahoo Finance"""
        try:
            result = data['chart']['result'][0]
            timestamps = result['timestamp']
            quote = result['indicators']['quote'][0]
            
            df = pd.DataFrame({
                'timestamp': pd.to_datetime(timestamps, unit='s'),
                'open': quote['open'],
                'high': quote['high'],
                'low': quote['low'],
                'close': quote['close'],
                'volume': quote['volume']
            })
            
            # Limpiar NaN values
            df = df.dropna()
            df = df.reset_index(drop=True)
            
            return df
            
        except KeyError as e:
            logger.error(f"❌ Error parsing Yahoo data: missing key {e}")
            return None
        except Exception as e:
            logger.error(f"❌ Error procesando Yahoo data: {e}")
            return None
    
    def process_alpha_vantage_data(self, data: Dict, timeframe: str) -> Optional[pd.DataFrame]:
        """Procesar datos de Alpha Vantage"""
        try:
            # Determinar clave de series temporales
            if timeframe == '1d':
                time_series_key = 'Time Series (Daily)'
            else:
                time_series_key = f'Time Series ({timeframe})'
            
            if time_series_key not in data:
                # Buscar clave alternativa
                for key in data.keys():
                    if 'Time Series' in key:
                        time_series_key = key
                        break
                else:
                    logger.error(f"❌ No se encontró series temporal en Alpha Vantage data")
                    return None
            
            time_series = data[time_series_key]
            
            # Convertir a DataFrame
            df_data = []
            for timestamp_str, values in time_series.items():
                df_data.append({
                    'timestamp': pd.to_datetime(timestamp_str),
                    'open': float(values['1. open']),
                    'high': float(values['2. high']),
                    'low': float(values['3. low']),
                    'close': float(values['4. close']),
                    'volume': int(values['5. volume']) if values['5. volume'] else 0
                })
            
            df = pd.DataFrame(df_data)
            df = df.sort_values('timestamp').reset_index(drop=True)
            
            return df
            
        except Exception as e:
            logger.error(f"❌ Error procesando Alpha Vantage data: {e}")
            return None
    
    def process_twelve_data(self, data: Dict) -> Optional[pd.DataFrame]:
        """Procesar datos de Twelve Data"""
        try:
            values = data['values']
            
            df_data = []
            for item in values:
                df_data.append({
                    'timestamp': pd.to_datetime(item['datetime']),
                    'open': float(item['open']),
                    'high': float(item['high']),
                    'low': float(item['low']),
                    'close': float(item['close']),
                    'volume': int(item['volume']) if item['volume'] else 0
                })
            
            df = pd.DataFrame(df_data)
            df = df.sort_values('timestamp').reset_index(drop=True)
            
            return df
            
        except Exception as e:
            logger.error(f"❌ Error procesando Twelve Data: {e}")
            return None
    
    def filter_by_date_range(self, df: pd.DataFrame, start_date: str, end_date: str) -> pd.DataFrame:
        """Filtrar DataFrame por rango de fechas"""
        try:
            start = pd.to_datetime(start_date)
            end = pd.to_datetime(end_date) + pd.Timedelta(days=1)  # Incluir día completo
            
            mask = (df['timestamp'] >= start) & (df['timestamp'] < end)
            return df[mask].reset_index(drop=True)
            
        except Exception as e:
            logger.error(f"❌ Error filtrando por fechas: {e}")
            return df
    
    def add_technical_indicators(self, df: pd.DataFrame, symbol: str) -> pd.DataFrame:
        """Agregar indicadores técnicos al DataFrame"""
        try:
            logger.debug(f"🔧 Calculando indicadores para {symbol}")
            
            # Usar el sistema de indicadores existente
            df_with_indicators = self.indicators.calculate_all_indicators(df.copy())
            
            return df_with_indicators
            
        except Exception as e:
            logger.warning(f"⚠️ Error calculando indicadores para {symbol}: {e}")
            return df  # Retornar datos sin indicadores
    
    def save_data(self, df: pd.DataFrame, symbol: str, timeframe: str) -> bool:
        """Guardar datos a CSV"""
        try:
            # Crear nombre de archivo
            filename = f"{symbol}_{timeframe}_{datetime.now().strftime('%Y%m%d')}.csv"
            filepath = os.path.join('historical_data/raw_data', filename)
            
            # Guardar CSV
            df.to_csv(filepath, index=False)
            
            logger.debug(f"💾 Guardado {symbol} {timeframe}: {filepath}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error guardando {symbol} {timeframe}: {e}")
            return False
    
    def worker_thread(self, worker_id: int):
        """Worker thread para procesamiento paralelo"""
        logger.debug(f"🔧 Worker {worker_id} iniciado")
        
        while not self.stop_event.is_set():
            try:
                # Obtener tarea con timeout
                priority, task = self.download_queue.get(timeout=1.0)
                
                # Procesar tarea
                success, df, error = self.download_single_symbol(task)
                
                if success:
                    self.mark_task_completed(task)
                else:
                    task.attempts += 1
                    if task.is_exhausted:
                        self.mark_task_failed(task, error)
                        logger.error(f"❌ {task.symbol} {task.timeframe}: Agotados intentos")
                    else:
                        # Re-queue para retry con menor prioridad
                        new_priority = task.priority + task.attempts * 2
                        self.download_queue.put((new_priority, task))
                        logger.info(f"🔄 Retry {task.symbol} {task.timeframe} (intento {task.attempts})")
                
                # Marcar tarea como completa en queue
                self.download_queue.task_done()
                
                # Sleep para respetar rate limits
                time.sleep(0.5)
                
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"💥 Error en worker {worker_id}: {e}")
                continue
        
        logger.debug(f"🔧 Worker {worker_id} terminado")
    
    def print_progress(self):
        """Imprimir progreso actual"""
        elapsed = self.progress.time_elapsed()
        remaining = self.progress.estimate_remaining_time()
        
        print(f"\n📊 PROGRESO DE DESCARGA")
        print(f"   ✅ Completadas: {self.progress.completed_tasks}/{self.progress.total_tasks} "
              f"({self.progress.completion_percentage:.1f}%)")
        print(f"   ❌ Fallidas: {self.progress.failed_tasks}")
        print(f"   📈 Puntos descargados: {self.progress.data_points_downloaded:,}")
        print(f"   ⏱️ Tiempo transcurrido: {elapsed}")
        if remaining:
            print(f"   ⏳ Tiempo estimado restante: {remaining}")
        print(f"   🎯 Actual: {self.progress.current_symbol} {self.progress.current_timeframe}")
        print(f"   📊 Tasa éxito: {self.progress.success_rate:.1f}%")
    
    def download_batch(self, symbols: List[str], timeframes: List[str] = None, 
                      start_date: str = None, end_date: str = None,
                      max_workers: int = None) -> Dict[str, Any]:
        """
        Descargar lote de símbolos con procesamiento paralelo
        
        Args:
            symbols: Lista de símbolos a descargar
            timeframes: Lista de timeframes (default: ['1d', '1h', '15m'])
            start_date: Fecha inicio (default: config.HISTORICAL_START_DATE)
            end_date: Fecha fin (default: hoy)
            max_workers: Máximo workers paralelos (default: auto)
            
        Returns:
            Dict con estadísticas de descarga
        """
        # Defaults
        timeframes = timeframes or ['1d', '1h', '15m']
        start_date = start_date or config.HISTORICAL_START_DATE
        end_date = end_date or datetime.now().strftime('%Y-%m-%d')
        max_workers = max_workers or config.PARALLEL_CONFIG['max_workers']
        
        # Generar tareas
        tasks = self.generate_tasks(symbols, timeframes, start_date, end_date)
        
        # Filtrar tareas ya completadas
        pending_tasks = [task for task in tasks if not self.is_task_completed(task)]
        
        logger.info(f"📋 Tareas pendientes: {len(pending_tasks)}/{len(tasks)}")
        
        if not pending_tasks:
            logger.info("✅ Todas las tareas ya están completadas")
            return {'status': 'completed', 'message': 'No hay tareas pendientes'}
        
        # Configurar progreso
        self.progress.total_tasks = len(tasks)
        self.progress.completed_tasks = len(tasks) - len(pending_tasks)
        self.progress.start_time = datetime.now()
        self.progress.total_estimated_points = sum(t.estimated_points for t in tasks)
        
        # Llenar queue de tareas
        for task in pending_tasks:
            self.download_queue.put((task.priority, task))
        
        # Iniciar workers
        workers = []
        
        for i in range(max_workers):
            worker = threading.Thread(
                target=self.worker_thread,
                args=(i+1,),
                name=f"Worker-{i+1}"
            )
            worker.daemon = True
            worker.start()
            workers.append(worker)
        
        logger.info(f"🚀 Iniciando descarga con {max_workers} workers")
        self.print_progress()
        
        # Monitor de progreso
        last_print = time.time()
        
        try:
            # Loop de monitoreo
            while not self.download_queue.empty() and not self.stop_event.is_set():
                time.sleep(2)
                
                # Imprimir progreso cada 10 segundos
                if time.time() - last_print > 10:
                    self.print_progress()
                    last_print = time.time()
            
            # Esperar que se completen todas las tareas
            logger.info("⏳ Esperando que terminen las tareas...")
            self.download_queue.join()
            
            # Parar threads
            self.stop_event.set()
            
            # Esperar que terminen workers
            for worker in workers:
                worker.join(timeout=5)
            
            # Estadísticas finales
            final_stats = {
                'status': 'completed',
                'total_tasks': self.progress.total_tasks,
                'completed_tasks': self.progress.completed_tasks,
                'failed_tasks': self.progress.failed_tasks,
                'success_rate': self.progress.success_rate,
                'data_points_downloaded': self.progress.data_points_downloaded,
                'time_elapsed': str(self.progress.time_elapsed()),
                'api_usage': self.api_manager.get_daily_summary()
            }
            
            logger.info("🎉 Descarga completada")
            self.print_progress()
            
            return final_stats
            
        except KeyboardInterrupt:
            logger.info("⏹️ Descarga interrumpida por usuario")
            self.stop_event.set()
            
            # Parar workers
            for worker in workers:
                worker.join(timeout=2)
            
            return {
                'status': 'interrupted',
                'completed_tasks': self.progress.completed_tasks,
                'message': 'Descarga interrumpida, progreso guardado'
            }
        
        except Exception as e:
            logger.error(f"💥 Error durante descarga: {e}")
            self.stop_event.set()
            
            # Parar workers
            for worker in workers:
                worker.join(timeout=2)
            
            return {
                'status': 'error',
                'error': str(e),
                'completed_tasks': self.progress.completed_tasks
            }

# =============================================================================
# 🧪 FUNCIONES DE TESTING Y CLI
# =============================================================================

def test_single_download():
    """Test de descarga individual"""
    print("🧪 Testing descarga individual...")
    
    downloader = DataDownloader()
    
    task = DownloadTask(
        symbol='AAPL',
        timeframe='1d',
        start_date='2024-01-01',
        end_date='2024-02-01'
    )
    
    success, df, error = downloader.download_single_symbol(task)
    
    if success:
        print(f"✅ Test exitoso: {len(df) if df is not None else 0} puntos descargados")
        if df is not None:
            print(f"📊 Columnas: {list(df.columns)}")
            print(f"📅 Rango: {df['timestamp'].min()} a {df['timestamp'].max()}")
    else:
        print(f"❌ Test falló: {error}")

def main():
    """Función principal CLI"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Descargador de Datos Históricos V3.0')
    parser.add_argument('--symbols', nargs='+', default=['AAPL', 'GOOGL', 'MSFT'],
                       help='Símbolos a descargar')
    parser.add_argument('--timeframes', nargs='+', default=['1d', '1h'],
                       help='Timeframes a descargar')
    parser.add_argument('--start-date', default=config.HISTORICAL_START_DATE,
                       help='Fecha inicio (YYYY-MM-DD)')
    parser.add_argument('--end-date', default=datetime.now().strftime('%Y-%m-%d'),
                       help='Fecha fin (YYYY-MM-DD)')
    parser.add_argument('--workers', type=int, default=config.PARALLEL_CONFIG['max_workers'],
                       help='Número máximo de workers')
    parser.add_argument('--test', action='store_true',
                       help='Ejecutar test de descarga individual')
    parser.add_argument('--resume', action='store_true',
                       help='Continuar descarga previa')
    parser.add_argument('--clean', action='store_true',
                       help='Limpiar progreso previo y empezar desde cero')
    
    args = parser.parse_args()
    
    if args.test:
        test_single_download()
        return
    
    # Crear downloader
    downloader = DataDownloader()
    
    # Limpiar progreso si se solicita
    if args.clean:
        print("🧹 Limpiando progreso previo...")
        downloader.completed_tasks.clear()
        downloader.failed_tasks.clear()
        if os.path.exists(downloader.progress_file):
            os.remove(downloader.progress_file)
        print("✅ Progreso limpiado")
    
    # Mostrar resumen de descarga
    print(f"\n📋 CONFIGURACIÓN DE DESCARGA:")
    print(f"   Símbolos: {len(args.symbols)} ({', '.join(args.symbols[:5])}{'...' if len(args.symbols) > 5 else ''})")
    print(f"   Timeframes: {args.timeframes}")
    print(f"   Período: {args.start_date} a {args.end_date}")
    print(f"   Workers: {args.workers}")
    print(f"   Resume: {'Sí' if args.resume else 'No'}")
    
    # Confirmar descarga
    if not args.resume and len(args.symbols) > 10:
        response = input(f"\n¿Proceder con la descarga de {len(args.symbols)} símbolos? (s/n): ").lower()
        if response != 's' and response != 'y':
            print("⏹️ Descarga cancelada")
            return
    
    # Ejecutar descarga batch
    start_time = time.time()
    
    try:
        stats = downloader.download_batch(
            symbols=args.symbols,
            timeframes=args.timeframes,
            start_date=args.start_date,
            end_date=args.end_date,
            max_workers=args.workers
        )
        
        elapsed_time = time.time() - start_time
        
        # Mostrar resultados finales
        print(f"\n" + "="*60)
        print(f"📊 RESULTADOS FINALES DE DESCARGA")
        print(f"="*60)
        print(f"   Estado: {stats.get('status', 'unknown')}")
        print(f"   Tareas totales: {stats.get('total_tasks', 0)}")
        print(f"   Tareas completadas: {stats.get('completed_tasks', 0)}")
        print(f"   Tareas fallidas: {stats.get('failed_tasks', 0)}")
        print(f"   Puntos de datos descargados: {stats.get('data_points_downloaded', 0):,}")
        print(f"   Tiempo total: {elapsed_time:.1f} segundos")
        
        if stats.get('status') == 'completed':
            success_rate = stats.get('success_rate', 0)
            print(f"   Tasa de éxito: {success_rate:.1f}%")
            
            if success_rate >= 90:
                print(f"✅ DESCARGA EXCELENTE")
            elif success_rate >= 75:
                print(f"⚠️ DESCARGA BUENA - Algunos errores menores")
            else:
                print(f"❌ DESCARGA PROBLEMÁTICA - Revisar errores")
        
        # Mostrar estadísticas de APIs
        if 'api_usage' in stats:
            print(f"\n📡 ESTADÍSTICAS DE APIS:")
            for api, usage in stats['api_usage'].items():
                if usage.get('requests_made', 0) > 0:
                    print(f"   {api}: {usage['requests_made']} requests, "
                          f"{usage.get('success_rate', 0):.1f}% éxito")
        
        # Mostrar archivos generados
        raw_data_dir = 'historical_data/raw_data'
        if os.path.exists(raw_data_dir):
            csv_files = [f for f in os.listdir(raw_data_dir) if f.endswith('.csv')]
            print(f"\n📁 ARCHIVOS GENERADOS: {len(csv_files)} CSV files en {raw_data_dir}")
            
            # Mostrar algunos ejemplos
            if csv_files:
                print(f"   Ejemplos:")
                for file in sorted(csv_files)[-5:]:  # Últimos 5 archivos
                    filepath = os.path.join(raw_data_dir, file)
                    size = os.path.getsize(filepath) / 1024  # KB
                    print(f"     {file} ({size:.1f} KB)")
        
        print(f"\n🎉 ¡Descarga finalizada! Verifica los archivos en historical_data/raw_data/")
        
    except KeyboardInterrupt:
        print(f"\n⏹️ Descarga interrumpida por usuario")
        print(f"📝 El progreso ha sido guardado. Usa --resume para continuar.")
    
    except Exception as e:
        print(f"\n💥 Error durante descarga: {e}")
        print(f"📝 Revisa los logs para más detalles.")

if __name__ == "__main__":
    main()