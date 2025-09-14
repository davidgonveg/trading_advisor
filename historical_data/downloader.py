#!/usr/bin/env python3
"""
📥 DOWNLOADER - DESCARGA MASIVA DE DATOS HISTÓRICOS V4.0
======================================================

Sistema simplificado pero robusto para descarga masiva de datos históricos
usando múltiples APIs con rate limiting inteligente.

🎯 CARACTERÍSTICAS:
- Multi-API con fallback automático (Yahoo, Twelve Data, Alpha Vantage, Polygon)
- Rate limiting inteligente por API
- Progress tracking con ETA
- Resume capability (continúa donde se quedó)
- Paralelización controlada
- Validación y limpieza automática de datos
- Integración directa con sistema principal

📊 OUTPUT:
- CSV files por símbolo/timeframe
- Datos listos para backtesting
- Progress logs detallados
"""

import os
import sys
import time
import json
import pandas as pd
import yfinance as yf
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
import argparse

# Setup paths
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

# Import config
try:
    import config
    print("✅ Config cargado")
except ImportError as e:
    print(f"❌ Error cargando config: {e}")
    sys.exit(1)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@dataclass
class DownloadTask:
    """Tarea de descarga"""
    symbol: str
    timeframe: str
    start_date: str
    end_date: str
    priority: int = 0  # Mayor número = mayor prioridad

class APIRotator:
    """Rotador de APIs con rate limiting"""
    
    def __init__(self):
        self.last_request = {}  # API -> timestamp
        self.request_counts = {}  # API -> count today
        self.failed_apis = set()  # APIs temporalmente bloqueadas
        
        # Inicializar contadores
        today = datetime.now().strftime('%Y-%m-%d')
        for api in config.API_PRIORITY:
            self.last_request[api] = 0
            self.request_counts[api] = 0
    
    def can_use_api(self, api_name: str) -> bool:
        """¿Puede usar esta API ahora?"""
        if api_name in self.failed_apis:
            return False
        
        # Verificar disponibilidad
        if not config.is_api_available(api_name):
            return False
        
        # Verificar rate limit
        now = time.time()
        last_req = self.last_request.get(api_name, 0)
        rate_limit = config.RATE_LIMITS.get(api_name, 1.0)
        
        return (now - last_req) >= rate_limit
    
    def wait_for_api(self, api_name: str):
        """Esperar el rate limit de una API"""
        now = time.time()
        last_req = self.last_request.get(api_name, 0)
        rate_limit = config.RATE_LIMITS.get(api_name, 1.0)
        
        wait_time = rate_limit - (now - last_req)
        if wait_time > 0:
            logger.info(f"⏰ Esperando {wait_time:.1f}s para {api_name}")
            time.sleep(wait_time)
    
    def mark_request(self, api_name: str, success: bool = True):
        """Marcar request realizado"""
        self.last_request[api_name] = time.time()
        self.request_counts[api_name] = self.request_counts.get(api_name, 0) + 1
        
        if not success:
            # Si falla mucho, marcar temporalmente como bloqueada
            logger.warning(f"⚠️ {api_name} falló, evaluando bloqueo temporal")
    
    def get_next_api(self) -> Optional[str]:
        """Obtener la siguiente API disponible"""
        for api in config.API_PRIORITY:
            if self.can_use_api(api):
                return api
        return None

class HistoricalDownloader:
    """Descargador principal de datos históricos"""
    
    def __init__(self):
        self.api_rotator = APIRotator()
        self.progress_file = config.PATHS['progress_file']
        self.completed_tasks = set()
        self.failed_tasks = set()
        self.stats = {
            'started_at': datetime.now(),
            'total_tasks': 0,
            'completed': 0,
            'failed': 0,
            'api_usage': {}
        }
        
        # Cargar progreso previo si existe
        self.load_progress()
        
        logger.info("📥 Historical Downloader V4.0 inicializado")
    
    def load_progress(self):
        """Cargar progreso previo"""
        if os.path.exists(self.progress_file):
            try:
                with open(self.progress_file, 'r') as f:
                    progress = json.load(f)
                
                self.completed_tasks = set(progress.get('completed_tasks', []))
                self.failed_tasks = set(progress.get('failed_tasks', []))
                
                logger.info(f"📋 Progreso cargado: {len(self.completed_tasks)} completadas, {len(self.failed_tasks)} fallidas")
                
            except Exception as e:
                logger.warning(f"⚠️ Error cargando progreso: {e}")
    
    def save_progress(self):
        """Guardar progreso actual"""
        try:
            os.makedirs(os.path.dirname(self.progress_file), exist_ok=True)
            
            progress = {
                'timestamp': datetime.now().isoformat(),
                'completed_tasks': list(self.completed_tasks),
                'failed_tasks': list(self.failed_tasks),
                'stats': self.stats
            }
            
            with open(self.progress_file, 'w') as f:
                json.dump(progress, f, indent=2)
                
        except Exception as e:
            logger.error(f"❌ Error guardando progreso: {e}")
    
    def download_yahoo_finance(self, task: DownloadTask) -> Tuple[bool, Optional[pd.DataFrame], str]:
        """Descargar datos usando Yahoo Finance (yfinance)"""
        try:
            ticker = yf.Ticker(task.symbol)
            
            # Convertir timeframe de config a yfinance format
            yf_interval = task.timeframe
            if task.timeframe == '15m':
                yf_interval = '15m'
            elif task.timeframe == '1h':
                yf_interval = '1h'
            elif task.timeframe == '1d':
                yf_interval = '1d'
            
            data = ticker.history(
                start=task.start_date,
                end=task.end_date,
                interval=yf_interval,
                auto_adjust=True,
                prepost=True
            )
            
            if data.empty:
                return False, None, f"No data for {task.symbol}"
            
            # Limpiar y validar datos
            data = data.dropna()
            
            if len(data) == 0:
                return False, None, f"No valid data after cleanup"
            
            # Renombrar columnas a formato estándar
            data = data.rename(columns={
                'Open': 'open',
                'High': 'high', 
                'Low': 'low',
                'Close': 'close',
                'Volume': 'volume'
            })
            
            # Agregar metadatos
            data['symbol'] = task.symbol
            data['timeframe'] = task.timeframe
            data['timestamp'] = data.index
            
            return True, data, f"OK - {len(data)} points"
            
        except Exception as e:
            error_msg = str(e)
            if "429" in error_msg or "Too Many Requests" in error_msg:
                return False, None, "Rate limited"
            else:
                return False, None, f"Error: {error_msg[:100]}"
    
    def download_alpha_vantage(self, task: DownloadTask) -> Tuple[bool, Optional[pd.DataFrame], str]:
        """Descargar datos usando Alpha Vantage"""
        try:
            # Determinar función según timeframe
            if task.timeframe == '1d':
                function = 'TIME_SERIES_DAILY'
                params = {
                    'function': function,
                    'symbol': task.symbol,
                    'apikey': config.API_KEYS['ALPHA_VANTAGE'],
                    'outputsize': 'full'
                }
            else:
                function = 'TIME_SERIES_INTRADAY'
                params = {
                    'function': function,
                    'symbol': task.symbol,
                    'interval': task.timeframe,
                    'apikey': config.API_KEYS['ALPHA_VANTAGE'],
                    'outputsize': 'full'
                }
            
            response = requests.get(config.API_ENDPOINTS['ALPHA_VANTAGE'], 
                                  params=params, timeout=30)
            
            if response.status_code != 200:
                return False, None, f"HTTP {response.status_code}"
            
            data = response.json()
            
            # Manejar errores de API
            if 'Error Message' in data:
                return False, None, data['Error Message']
            elif 'Note' in data:
                return False, None, "Rate limited"
            
            # Extraer datos según función
            if function == 'TIME_SERIES_DAILY':
                time_series = data.get('Time Series (Daily)', {})
            else:
                time_series_key = f'Time Series ({task.timeframe})'
                time_series = data.get(time_series_key, {})
            
            if not time_series:
                return False, None, "No time series data"
            
            # Convertir a DataFrame
            df_data = []
            for timestamp, ohlcv in time_series.items():
                df_data.append({
                    'timestamp': pd.to_datetime(timestamp),
                    'open': float(ohlcv['1. open']),
                    'high': float(ohlcv['2. high']),
                    'low': float(ohlcv['3. low']),
                    'close': float(ohlcv['4. close']),
                    'volume': int(ohlcv['5. volume']),
                    'symbol': task.symbol,
                    'timeframe': task.timeframe
                })
            
            df = pd.DataFrame(df_data)
            df = df.set_index('timestamp')
            df = df.sort_index()
            
            # Filtrar por fechas solicitadas
            start_date = pd.to_datetime(task.start_date)
            end_date = pd.to_datetime(task.end_date)
            df = df[(df.index >= start_date) & (df.index <= end_date)]
            
            return True, df, f"OK - {len(df)} points"
            
        except Exception as e:
            return False, None, f"Error: {str(e)[:100]}"
    
    def download_twelve_data(self, task: DownloadTask) -> Tuple[bool, Optional[pd.DataFrame], str]:
        """Descargar datos usando Twelve Data"""
        try:
            # Convertir timeframe
            td_interval = task.timeframe.replace('m', 'min').replace('h', 'h').replace('d', 'day')
            
            params = {
                'symbol': task.symbol,
                'interval': td_interval,
                'apikey': config.API_KEYS['TWELVE_DATA'],
                'outputsize': 5000,
                'format': 'JSON'
            }
            
            response = requests.get(config.API_ENDPOINTS['TWELVE_DATA'], 
                                  params=params, timeout=30)
            
            if response.status_code != 200:
                return False, None, f"HTTP {response.status_code}"
            
            data = response.json()
            
            # Manejar errores
            if 'status' in data and data['status'] == 'error':
                return False, None, data.get('message', 'Unknown error')
            
            values = data.get('values', [])
            if not values:
                return False, None, "No data values"
            
            # Convertir a DataFrame
            df_data = []
            for item in values:
                df_data.append({
                    'timestamp': pd.to_datetime(item['datetime']),
                    'open': float(item['open']),
                    'high': float(item['high']),
                    'low': float(item['low']),
                    'close': float(item['close']),
                    'volume': int(item['volume']),
                    'symbol': task.symbol,
                    'timeframe': task.timeframe
                })
            
            df = pd.DataFrame(df_data)
            df = df.set_index('timestamp')
            df = df.sort_index()
            
            # Filtrar por fechas
            start_date = pd.to_datetime(task.start_date)
            end_date = pd.to_datetime(task.end_date)
            df = df[(df.index >= start_date) & (df.index <= end_date)]
            
            return True, df, f"OK - {len(df)} points"
            
        except Exception as e:
            return False, None, f"Error: {str(e)[:100]}"
    
    def download_polygon(self, task: DownloadTask) -> Tuple[bool, Optional[pd.DataFrame], str]:
        """Descargar datos usando Polygon"""
        try:
            # Convertir timeframe para Polygon
            if task.timeframe == '1d':
                multiplier, timespan = 1, 'day'
            elif task.timeframe == '1h':
                multiplier, timespan = 1, 'hour'
            elif task.timeframe == '15m':
                multiplier, timespan = 15, 'minute'
            else:
                return False, None, f"Timeframe {task.timeframe} not supported"
            
            url = f"{config.API_ENDPOINTS['POLYGON']}{task.symbol}/range/{multiplier}/{timespan}/{task.start_date}/{task.end_date}"
            params = {
                'apikey': config.API_KEYS['POLYGON'],
                'adjusted': 'true',
                'sort': 'asc'
            }
            
            response = requests.get(url, params=params, timeout=30)
            
            if response.status_code != 200:
                return False, None, f"HTTP {response.status_code}"
            
            data = response.json()
            
            if data.get('status') != 'OK':
                return False, None, data.get('error', 'Unknown error')
            
            results = data.get('results', [])
            if not results:
                return False, None, "No results"
            
            # Convertir a DataFrame
            df_data = []
            for item in results:
                df_data.append({
                    'timestamp': pd.to_datetime(item['t'], unit='ms'),
                    'open': float(item['o']),
                    'high': float(item['h']),
                    'low': float(item['l']),
                    'close': float(item['c']),
                    'volume': int(item['v']),
                    'symbol': task.symbol,
                    'timeframe': task.timeframe
                })
            
            df = pd.DataFrame(df_data)
            df = df.set_index('timestamp')
            df = df.sort_index()
            
            return True, df, f"OK - {len(df)} points"
            
        except Exception as e:
            return False, None, f"Error: {str(e)[:100]}"
    
    def download_single_task(self, task: DownloadTask) -> Tuple[bool, Optional[pd.DataFrame], str, str]:
        """Descargar una tarea usando rotación de APIs"""
        task_id = f"{task.symbol}_{task.timeframe}_{task.start_date}_{task.end_date}"
        
        # Verificar si ya está completada
        if task_id in self.completed_tasks:
            return True, None, "Already completed", "CACHE"
        
        # Intentar con cada API disponible
        for attempt, api in enumerate(config.API_PRIORITY):
            if not self.api_rotator.can_use_api(api):
                continue
            
            logger.info(f"📊 Downloading {task.symbol} {task.timeframe} usando {api}...")
            
            # Esperar rate limit si es necesario
            self.api_rotator.wait_for_api(api)
            
            # Intentar descarga según API
            success, data, message = False, None, "No data"
            
            if api == 'YAHOO':
                success, data, message = self.download_yahoo_finance(task)
            elif api == 'ALPHA_VANTAGE':
                success, data, message = self.download_alpha_vantage(task)
            elif api == 'TWELVE_DATA':
                success, data, message = self.download_twelve_data(task)
            elif api == 'POLYGON':
                success, data, message = self.download_polygon(task)
            
            # Marcar request en API rotator
            self.api_rotator.mark_request(api, success)
            
            # Actualizar stats
            api_stats = self.stats['api_usage'].get(api, {'requests': 0, 'success': 0})
            api_stats['requests'] += 1
            if success:
                api_stats['success'] += 1
            self.stats['api_usage'][api] = api_stats
            
            if success and data is not None:
                logger.info(f"✅ {task.symbol} {task.timeframe}: {message} desde {api}")
                self.completed_tasks.add(task_id)
                return True, data, message, api
            else:
                logger.warning(f"⚠️ {api} falló para {task.symbol}: {message}")
                
                # Si es rate limit, probar siguiente API
                if "rate" in message.lower() or "429" in message:
                    continue
        
        # Ninguna API funcionó
        self.failed_tasks.add(task_id)
        return False, None, "All APIs failed", "NONE"
    
    def save_to_csv(self, data: pd.DataFrame, symbol: str, timeframe: str) -> str:
        """Guardar datos a CSV"""
        try:
            # Crear nombre de archivo
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{symbol}_{timeframe}_{timestamp}.csv"
            filepath = os.path.join(config.PATHS['raw_data'], filename)
            
            # Asegurar directorio existe
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            
            # Guardar CSV
            data.to_csv(filepath)
            
            logger.info(f"💾 Guardado: {filename} ({len(data)} rows)")
            return filepath
            
        except Exception as e:
            logger.error(f"❌ Error guardando CSV: {e}")
            return ""
    
    def download_batch(self, tasks: List[DownloadTask], max_workers: int = 4) -> Dict[str, Any]:
        """Descargar lote de tareas en paralelo"""
        logger.info(f"🚀 Iniciando descarga de {len(tasks)} tareas con {max_workers} workers")
        
        self.stats['total_tasks'] = len(tasks)
        start_time = time.time()
        
        # Filtrar tareas ya completadas
        pending_tasks = []
        for task in tasks:
            task_id = f"{task.symbol}_{task.timeframe}_{task.start_date}_{task.end_date}"
            if task_id not in self.completed_tasks:
                pending_tasks.append(task)
        
        logger.info(f"📋 {len(pending_tasks)} tareas pendientes, {len(tasks) - len(pending_tasks)} ya completadas")
        
        if not pending_tasks:
            return {
                'status': 'completed',
                'message': 'All tasks already completed',
                'stats': self.stats
            }
        
        # Ejecutar en paralelo
        completed_count = 0
        failed_count = 0
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Enviar tareas
            future_to_task = {
                executor.submit(self.download_single_task, task): task 
                for task in pending_tasks
            }
            
            # Procesar resultados
            for future in as_completed(future_to_task):
                task = future_to_task[future]
                
                try:
                    success, data, message, api_used = future.result()
                    
                    if success and data is not None:
                        # Guardar datos
                        filepath = self.save_to_csv(data, task.symbol, task.timeframe)
                        completed_count += 1
                        self.stats['completed'] = completed_count
                    else:
                        failed_count += 1
                        self.stats['failed'] = failed_count
                        logger.error(f"❌ {task.symbol} {task.timeframe}: {message}")
                    
                    # Progress update cada 10 tareas
                    if (completed_count + failed_count) % 10 == 0:
                        progress = (completed_count + failed_count) / len(pending_tasks) * 100
                        elapsed = time.time() - start_time
                        eta = (elapsed / (completed_count + failed_count)) * (len(pending_tasks) - completed_count - failed_count)
                        
                        logger.info(f"📊 Progress: {progress:.1f}% ({completed_count + failed_count}/{len(pending_tasks)}) - ETA: {eta:.0f}s")
                        
                        # Guardar progreso
                        self.save_progress()
                
                except Exception as e:
                    failed_count += 1
                    self.stats['failed'] = failed_count
                    logger.error(f"❌ Error procesando {task.symbol}: {e}")
        
        # Estadísticas finales
        elapsed = time.time() - start_time
        success_rate = (completed_count / len(pending_tasks)) * 100 if pending_tasks else 0
        
        # Guardar progreso final
        self.save_progress()
        
        return {
            'status': 'completed' if failed_count == 0 else 'partial',
            'completed': completed_count,
            'failed': failed_count,
            'total': len(pending_tasks),
            'success_rate': success_rate,
            'elapsed_time': elapsed,
            'api_usage': self.stats['api_usage']
        }

def generate_tasks(symbols: List[str], timeframes: List[str], 
                  start_date: str, end_date: str) -> List[DownloadTask]:
    """Generar lista de tareas de descarga"""
    tasks = []
    
    for symbol in symbols:
        for timeframe in timeframes:
            task = DownloadTask(
                symbol=symbol,
                timeframe=timeframe,
                start_date=start_date,
                end_date=end_date,
                priority=1 if timeframe == '1d' else 0  # Priorizar daily data
            )
            tasks.append(task)
    
    # Ordenar por prioridad
    tasks.sort(key=lambda x: x.priority, reverse=True)
    return tasks

def main():
    """Función principal CLI"""
    parser = argparse.ArgumentParser(description='Historical Data Downloader V4.0')
    parser.add_argument('--symbols', nargs='+', default=None,
                       help='Símbolos a descargar (ej: AAPL GOOGL MSFT)')
    parser.add_argument('--timeframes', nargs='+', default=['1d'],
                       help='Timeframes (ej: 1d 1h 15m)')
    parser.add_argument('--start-date', default=config.HISTORICAL_START_DATE,
                       help='Fecha inicio YYYY-MM-DD')
    parser.add_argument('--end-date', default=datetime.now().strftime('%Y-%m-%d'),
                       help='Fecha fin YYYY-MM-DD')
    parser.add_argument('--workers', type=int, default=4,
                       help='Número de workers paralelos')
    parser.add_argument('--test', action='store_true',
                       help='Modo test: solo descargar AAPL 1d último mes')
    
    args = parser.parse_args()
    
    # Configurar parámetros
    if args.test:
        symbols = ['AAPL']
        timeframes = ['1d']
        start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        end_date = datetime.now().strftime('%Y-%m-%d')
        print("🧪 MODO TEST: Solo AAPL último mes")
    else:
        symbols = args.symbols or config.SYMBOLS[:5]  # Primeros 5 por defecto
        timeframes = args.timeframes
        start_date = args.start_date
        end_date = args.end_date
    
    print(f"📥 HISTORICAL DOWNLOADER V4.0")
    print(f"=" * 50)
    print(f"📊 Símbolos: {len(symbols)} ({', '.join(symbols[:3])}{'...' if len(symbols) > 3 else ''})")
    print(f"⏱️ Timeframes: {', '.join(timeframes)}")
    print(f"📅 Período: {start_date} a {end_date}")
    print(f"🔧 Workers: {args.workers}")
    
    # Generar tareas
    tasks = generate_tasks(symbols, timeframes, start_date, end_date)
    print(f"📋 Total de tareas: {len(tasks)}")
    
    # Inicializar downloader
    downloader = HistoricalDownloader()
    
    # Ejecutar descarga
    start_time = time.time()
    results = downloader.download_batch(tasks, max_workers=args.workers)
    elapsed = time.time() - start_time
    
    # Mostrar resultados
    print(f"\n" + "=" * 50)
    print(f"📊 RESULTADOS FINALES")
    print(f"=" * 50)
    print(f"✅ Completadas: {results['completed']}")
    print(f"❌ Fallidas: {results['failed']}")
    print(f"📊 Tasa éxito: {results['success_rate']:.1f}%")
    print(f"⏱️ Tiempo total: {elapsed:.1f}s")
    
    # API usage
    if results['api_usage']:
        print(f"\n📡 USO DE APIs:")
        for api, stats in results['api_usage'].items():
            success_rate = (stats['success'] / stats['requests']) * 100 if stats['requests'] > 0 else 0
            print(f"   {api}: {stats['requests']} requests, {success_rate:.1f}% éxito")
    
    # Archivos generados
    raw_data_dir = config.PATHS['raw_data']
    if os.path.exists(raw_data_dir):
        csv_files = [f for f in os.listdir(raw_data_dir) if f.endswith('.csv')]
        print(f"\n📁 Archivos CSV generados: {len(csv_files)}")
    
    print(f"\n🎉 ¡Descarga finalizada! Siguiente paso: python populate_db.py")

if __name__ == "__main__":
    main()