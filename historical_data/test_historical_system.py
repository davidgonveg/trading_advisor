#!/usr/bin/env python3
"""
🧪 TESTING SUITE - SISTEMA DE DATOS HISTÓRICOS V3.0
================================================

Suite completa de testing para validar:
- API Manager functionality
- Data Downloader operations  
- Data integrity and processing
- Error handling and recovery
- Performance benchmarks

🎯 TESTS INCLUIDOS:
1. API Manager Tests
   - Connectivity to all APIs
   - Rate limiting behavior
   - Fallback mechanisms
   - Usage tracking

2. Data Downloader Tests
   - Single symbol download
   - Batch processing
   - Progress tracking
   - Resume capability

3. Data Quality Tests
   - OHLCV data validation
   - Technical indicators accuracy
   - Date range filtering
   - Missing data handling

4. Integration Tests
   - End-to-end workflow
   - Database population
   - Error recovery
   - Performance metrics
"""

import sys
import os
import time
import json
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import logging

# Setup de imports
def setup_imports():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    if current_dir not in sys.path:
        sys.path.insert(0, current_dir)
    parent_dir = os.path.dirname(current_dir)
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)

setup_imports()

# Imports del sistema
try:
    import config
    from api_manager import APIManager
    from data_downloader import DataDownloader, DownloadTask
except ImportError as e:
    print(f"❌ Error importando módulos: {e}")
    sys.exit(1)

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class HistoricalSystemTester:
    """
    Suite de testing para el sistema completo
    """
    
    def __init__(self):
        """Inicializar tester"""
        self.api_manager = None
        self.downloader = None
        self.test_results = {
            'api_manager': {},
            'data_downloader': {},
            'data_quality': {},
            'integration': {},
            'performance': {}
        }
        self.start_time = datetime.now()
        
        print("🧪 Inicializando Historical System Tester V3.0")
        print("=" * 60)
    
    def run_all_tests(self) -> Dict:
        """Ejecutar toda la suite de tests"""
        print("\n🚀 INICIANDO SUITE COMPLETA DE TESTS")
        print("=" * 60)
        
        try:
            # 1. API Manager Tests
            print("\n1️⃣ TESTING API MANAGER")
            print("-" * 30)
            self.test_api_manager()
            
            # 2. Data Downloader Tests
            print("\n2️⃣ TESTING DATA DOWNLOADER")
            print("-" * 30)
            self.test_data_downloader()
            
            # 3. Data Quality Tests
            print("\n3️⃣ TESTING DATA QUALITY")
            print("-" * 30)
            self.test_data_quality()
            
            # 4. Integration Tests
            print("\n4️⃣ TESTING INTEGRATION")
            print("-" * 30)
            self.test_integration()
            
            # 5. Performance Tests
            print("\n5️⃣ TESTING PERFORMANCE")
            print("-" * 30)
            self.test_performance()
            
        except Exception as e:
            print(f"💥 Error durante testing: {e}")
            self.test_results['error'] = str(e)
        
        # Generar reporte final
        self.generate_report()
        
        return self.test_results
    
    def test_api_manager(self):
        """Test del API Manager"""
        results = {}
        
        try:
            # Crear instancia
            self.api_manager = APIManager()
            results['initialization'] = '✅ PASS'
            
            # Test 1: APIs disponibles
            available_apis = self.api_manager.get_available_apis()
            if available_apis:
                results['available_apis'] = f'✅ PASS - {len(available_apis)} APIs disponibles: {available_apis}'
            else:
                results['available_apis'] = '❌ FAIL - No hay APIs disponibles'
            
            # Test 2: Connectivity test
            print("   🔍 Testing conectividad...")
            success, data, source = self.api_manager.get_data('AAPL', interval='1d', period='5d')
            
            if success:
                results['connectivity'] = f'✅ PASS - Conectado via {source}'
            else:
                results['connectivity'] = f'❌ FAIL - No se pudo conectar: {source}'
            
            # Test 3: Rate limiting
            print("   ⏱️ Testing rate limiting...")
            start_time = time.time()
            
            # Hacer 3 requests seguidos
            for i in range(3):
                self.api_manager.get_data('MSFT', interval='1d', period='5d')
            
            elapsed = time.time() - start_time
            
            if elapsed >= 2.0:  # Debería tomar al menos 2 segundos con rate limiting
                results['rate_limiting'] = f'✅ PASS - Rate limiting funcionando ({elapsed:.1f}s)'
            else:
                results['rate_limiting'] = f'⚠️ WARNING - Rate limiting posible bypass ({elapsed:.1f}s)'
            
            # Test 4: Usage tracking
            print("   📊 Testing usage tracking...")
            summary = self.api_manager.get_daily_summary()
            
            if summary and any(stats['requests_made'] > 0 for stats in summary.values()):
                results['usage_tracking'] = '✅ PASS - Usage tracking activo'
            else:
                results['usage_tracking'] = '❌ FAIL - Usage tracking no funciona'
            
            # Test 5: Error handling
            print("   🛡️ Testing error handling...")
            success, data, error = self.api_manager.get_data('INVALID_SYMBOL_12345', interval='1d', period='5d')
            
            if not success and error:
                results['error_handling'] = f'✅ PASS - Error manejado correctamente'
            else:
                results['error_handling'] = f'❌ FAIL - Error handling no funciona'
                
        except Exception as e:
            results['exception'] = f'💥 EXCEPTION - {str(e)}'
        
        self.test_results['api_manager'] = results
        self.print_test_results('API MANAGER', results)
    
    def test_data_downloader(self):
        """Test del Data Downloader"""
        results = {}
        
        try:
            # Crear instancia
            self.downloader = DataDownloader(self.api_manager)
            results['initialization'] = '✅ PASS'
            
            # Test 1: Single symbol download
            print("   📥 Testing single symbol download...")
            task = DownloadTask(
                symbol='AAPL',
                timeframe='1d',
                start_date='2024-01-01',
                end_date='2024-01-31'
            )
            
            success, df, error = self.downloader.download_single_symbol(task)
            
            if success and df is not None and len(df) > 0:
                results['single_download'] = f'✅ PASS - {len(df)} puntos descargados'
            else:
                results['single_download'] = f'❌ FAIL - {error}'
            
            # Test 2: Task generation
            print("   📋 Testing task generation...")
            tasks = self.downloader.generate_tasks(
                symbols=['AAPL', 'GOOGL'], 
                timeframes=['1d', '1h'], 
                start_date='2024-01-01', 
                end_date='2024-01-31'
            )
            
            expected_tasks = 2 * 2  # 2 símbolos × 2 timeframes
            if len(tasks) == expected_tasks:
                results['task_generation'] = f'✅ PASS - {len(tasks)} tareas generadas'
            else:
                results['task_generation'] = f'❌ FAIL - Esperadas {expected_tasks}, generadas {len(tasks)}'
            
            # Test 3: Progress tracking
            print("   📊 Testing progress tracking...")
            if hasattr(self.downloader, 'progress') and self.downloader.progress:
                results['progress_tracking'] = '✅ PASS - Progress object existe'
            else:
                results['progress_tracking'] = '❌ FAIL - No hay progress tracking'
            
            # Test 4: Data processing
            print("   🔧 Testing data processing...")
            if success and df is not None:
                required_columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
                has_all_columns = all(col in df.columns for col in required_columns)
                
                if has_all_columns:
                    results['data_processing'] = '✅ PASS - Todas las columnas requeridas presentes'
                else:
                    missing = [col for col in required_columns if col not in df.columns]
                    results['data_processing'] = f'❌ FAIL - Columnas faltantes: {missing}'
            else:
                results['data_processing'] = '⏭️ SKIP - No hay datos para procesar'
            
            # Test 5: File saving
            print("   💾 Testing file saving...")
            if success and df is not None:
                save_success = self.downloader.save_data(df, 'TEST_AAPL', '1d')
                if save_success:
                    results['file_saving'] = '✅ PASS - Archivo guardado correctamente'
                else:
                    results['file_saving'] = '❌ FAIL - Error guardando archivo'
            else:
                results['file_saving'] = '⏭️ SKIP - No hay datos para guardar'
                
        except Exception as e:
            results['exception'] = f'💥 EXCEPTION - {str(e)}'
        
        self.test_results['data_downloader'] = results
        self.print_test_results('DATA DOWNLOADER', results)
    
    def test_data_quality(self):
        """Test de calidad de datos"""
        results = {}
        
        try:
            # Necesitamos datos de test previo
            task = DownloadTask(
                symbol='AAPL',
                timeframe='1d',
                start_date='2024-01-01',
                end_date='2024-01-31'
            )
            
            success, df, error = self.downloader.download_single_symbol(task)
            
            if not success or df is None or df.empty:
                results['data_availability'] = f'❌ FAIL - No hay datos para testear: {error}'
                self.test_results['data_quality'] = results
                self.print_test_results('DATA QUALITY', results)
                return
            
            results['data_availability'] = f'✅ PASS - {len(df)} puntos disponibles'
            
            # Test 1: OHLCV consistency
            print("   🔍 Testing OHLCV consistency...")
            ohlcv_valid = True
            ohlcv_errors = []
            
            for idx, row in df.iterrows():
                # High >= Open, Close, Low
                if row['high'] < max(row['open'], row['close'], row['low']):
                    ohlcv_valid = False
                    ohlcv_errors.append(f"Row {idx}: High too low")
                
                # Low <= Open, Close, High  
                if row['low'] > min(row['open'], row['close'], row['high']):
                    ohlcv_valid = False
                    ohlcv_errors.append(f"Row {idx}: Low too high")
                
                # Volume >= 0
                if row['volume'] < 0:
                    ohlcv_valid = False
                    ohlcv_errors.append(f"Row {idx}: Negative volume")
            
            if ohlcv_valid:
                results['ohlcv_consistency'] = '✅ PASS - OHLCV data consistent'
            else:
                results['ohlcv_consistency'] = f'❌ FAIL - {len(ohlcv_errors)} errors: {ohlcv_errors[:3]}'
            
            # Test 2: Missing data
            print("   🕳️ Testing missing data...")
            missing_data = df.isnull().sum()
            critical_columns = ['open', 'high', 'low', 'close']
            critical_missing = missing_data[critical_columns].sum()
            
            if critical_missing == 0:
                results['missing_data'] = '✅ PASS - No critical missing data'
            else:
                results['missing_data'] = f'❌ FAIL - {critical_missing} missing values in critical columns'
            
            # Test 3: Date continuity
            print("   📅 Testing date continuity...")
            df_sorted = df.sort_values('timestamp')
            date_gaps = []
            
            for i in range(1, len(df_sorted)):
                current_date = df_sorted.iloc[i]['timestamp']
                prev_date = df_sorted.iloc[i-1]['timestamp']
                gap = (current_date - prev_date).days
                
                # Para datos diarios, gap > 7 días es sospechoso (weekends + holidays)
                if gap > 7:
                    date_gaps.append(f"{prev_date.date()} -> {current_date.date()}: {gap} days")
            
            if len(date_gaps) == 0:
                results['date_continuity'] = '✅ PASS - No significant date gaps'
            elif len(date_gaps) <= 2:
                results['date_continuity'] = f'⚠️ WARNING - {len(date_gaps)} gaps (possibly holidays)'
            else:
                results['date_continuity'] = f'❌ FAIL - {len(date_gaps)} large gaps: {date_gaps[:2]}'
            
            # Test 4: Price reasonableness
            print("   💰 Testing price reasonableness...")
            price_issues = []
            
            # Check for zero prices
            zero_prices = ((df['open'] == 0) | (df['high'] == 0) | 
                          (df['low'] == 0) | (df['close'] == 0)).sum()
            if zero_prices > 0:
                price_issues.append(f"{zero_prices} zero prices")
            
            # Check for extreme price changes (>50% in one day)
            df_sorted['price_change'] = (df_sorted['close'] - df_sorted['open']) / df_sorted['open'] * 100
            extreme_changes = (abs(df_sorted['price_change']) > 50).sum()
            if extreme_changes > 0:
                price_issues.append(f"{extreme_changes} extreme changes (>50%)")
            
            if len(price_issues) == 0:
                results['price_reasonableness'] = '✅ PASS - Prices look reasonable'
            else:
                results['price_reasonableness'] = f'⚠️ WARNING - {", ".join(price_issues)}'
            
            # Test 5: Technical indicators (si están disponibles)
            print("   📈 Testing technical indicators...")
            indicator_columns = [col for col in df.columns if col not in 
                               ['timestamp', 'open', 'high', 'low', 'close', 'volume']]
            
            if indicator_columns:
                # Verificar que indicadores no son todos NaN
                indicator_data = df[indicator_columns]
                non_null_indicators = indicator_data.count()
                valid_indicators = (non_null_indicators > len(df) * 0.5).sum()  # Al menos 50% de datos
                
                if valid_indicators == len(indicator_columns):
                    results['technical_indicators'] = f'✅ PASS - {len(indicator_columns)} indicators calculated'
                else:
                    results['technical_indicators'] = f'⚠️ WARNING - {len(indicator_columns) - valid_indicators} indicators with insufficient data'
            else:
                results['technical_indicators'] = '⏭️ SKIP - No technical indicators found'
                
        except Exception as e:
            results['exception'] = f'💥 EXCEPTION - {str(e)}'
        
        self.test_results['data_quality'] = results
        self.print_test_results('DATA QUALITY', results)
    
    def test_integration(self):
        """Test de integración completa"""
        results = {}
        
        try:
            # Test 1: End-to-end workflow
            print("   🔄 Testing end-to-end workflow...")
            
            # Pequeño batch download
            symbols = ['AAPL', 'MSFT']
            timeframes = ['1d']
            start_date = '2024-01-01'
            end_date = '2024-01-15'  # Solo 2 semanas para rapidez
            
            stats = self.downloader.download_batch(
                symbols=symbols,
                timeframes=timeframes,
                start_date=start_date,
                end_date=end_date,
                max_workers=2
            )
            
            if stats['status'] == 'completed' and stats['completed_tasks'] > 0:
                results['end_to_end'] = f'✅ PASS - {stats["completed_tasks"]} tareas completadas'
            else:
                results['end_to_end'] = f'❌ FAIL - Status: {stats.get("status", "unknown")}'
            
            # Test 2: File system integration
            print("   📁 Testing file system...")
            raw_data_dir = 'historical_data/raw_data'
            
            if os.path.exists(raw_data_dir):
                files = os.listdir(raw_data_dir)
                csv_files = [f for f in files if f.endswith('.csv')]
                
                if len(csv_files) > 0:
                    results['file_system'] = f'✅ PASS - {len(csv_files)} CSV files created'
                else:
                    results['file_system'] = '❌ FAIL - No CSV files found'
            else:
                results['file_system'] = '❌ FAIL - Raw data directory not found'
            
            # Test 3: Progress persistence
            print("   💾 Testing progress persistence...")
            progress_file = self.downloader.progress_file
            
            if os.path.exists(progress_file):
                try:
                    with open(progress_file, 'r') as f:
                        progress_data = json.load(f)
                    
                    if 'completed_tasks' in progress_data and 'failed_tasks' in progress_data:
                        results['progress_persistence'] = '✅ PASS - Progress file valid'
                    else:
                        results['progress_persistence'] = '❌ FAIL - Progress file invalid format'
                except:
                    results['progress_persistence'] = '❌ FAIL - Progress file corrupt'
            else:
                results['progress_persistence'] = '⚠️ WARNING - No progress file found'
            
            # Test 4: Error recovery
            print("   🛡️ Testing error recovery...")
            
            # Intentar descargar símbolo inválido
            invalid_task = DownloadTask(
                symbol='INVALID_SYMBOL_XYZ',
                timeframe='1d', 
                start_date='2024-01-01',
                end_date='2024-01-15'
            )
            
            success, df, error = self.downloader.download_single_symbol(invalid_task)
            
            if not success and error and 'ALREADY_COMPLETED' not in error:
                results['error_recovery'] = '✅ PASS - Errors handled gracefully'
            else:
                results['error_recovery'] = '⚠️ WARNING - Error handling unclear'
            
            # Test 5: Resource cleanup
            print("   🧹 Testing resource cleanup...")
            
            # Verificar que no hay archivos temporales colgados
            temp_dir = 'historical_data/temp_data'
            if os.path.exists(temp_dir):
                temp_files = os.listdir(temp_dir)
                if len(temp_files) == 0:
                    results['resource_cleanup'] = '✅ PASS - No temp files left'
                else:
                    results['resource_cleanup'] = f'⚠️ WARNING - {len(temp_files)} temp files remain'
            else:
                results['resource_cleanup'] = '✅ PASS - Temp directory clean'
                
        except Exception as e:
            results['exception'] = f'💥 EXCEPTION - {str(e)}'
        
        self.test_results['integration'] = results
        self.print_test_results('INTEGRATION', results)
    
    def test_performance(self):
        """Test de rendimiento"""
        results = {}
        
        try:
            # Test 1: Download speed
            print("   ⚡ Testing download speed...")
            
            start_time = time.time()
            task = DownloadTask(
                symbol='AAPL',
                timeframe='1d',
                start_date='2024-01-01',
                end_date='2024-01-31'
            )
            
            success, df, error = self.downloader.download_single_symbol(task)
            elapsed = time.time() - start_time
            
            if success and df is not None:
                points_per_second = len(df) / elapsed
                results['download_speed'] = f'✅ PASS - {points_per_second:.1f} points/sec'
            else:
                results['download_speed'] = f'❌ FAIL - Download failed: {error}'
            
            # Test 2: Memory usage
            print("   🧠 Testing memory usage...")
            
            # Descargar dataset más grande para ver uso de memoria
            import psutil
            import os
            
            process = psutil.Process(os.getpid())
            memory_before = process.memory_info().rss / 1024 / 1024  # MB
            
            # Simular descarga de múltiples símbolos
            large_task_symbols = ['AAPL', 'GOOGL', 'MSFT', 'AMZN', 'TSLA']
            memory_test_data = []
            
            for symbol in large_task_symbols:
                task = DownloadTask(
                    symbol=symbol,
                    timeframe='1d',
                    start_date='2024-01-01', 
                    end_date='2024-01-31'
                )
                success, df, error = self.downloader.download_single_symbol(task)
                if success and df is not None:
                    memory_test_data.append(df)
            
            memory_after = process.memory_info().rss / 1024 / 1024  # MB
            memory_used = memory_after - memory_before
            
            if memory_used < 100:  # Menos de 100MB es razonable
                results['memory_usage'] = f'✅ PASS - {memory_used:.1f}MB used'
            elif memory_used < 250:
                results['memory_usage'] = f'⚠️ WARNING - {memory_used:.1f}MB used (high)'
            else:
                results['memory_usage'] = f'❌ FAIL - {memory_used:.1f}MB used (excessive)'
            
            # Test 3: API efficiency
            print("   🎯 Testing API efficiency...")
            
            api_summary = self.api_manager.get_daily_summary()
            total_requests = sum(stats.get('requests_made', 0) for stats in api_summary.values())
            successful_requests = sum(stats.get('requests_made', 0) * stats.get('success_rate', 0) / 100 
                                    for stats in api_summary.values())
            
            if total_requests > 0:
                efficiency = (successful_requests / total_requests) * 100
                if efficiency >= 90:
                    results['api_efficiency'] = f'✅ PASS - {efficiency:.1f}% success rate'
                elif efficiency >= 75:
                    results['api_efficiency'] = f'⚠️ WARNING - {efficiency:.1f}% success rate'
                else:
                    results['api_efficiency'] = f'❌ FAIL - {efficiency:.1f}% success rate'
            else:
                results['api_efficiency'] = '⏭️ SKIP - No API requests made'
            
            # Test 4: Parallel processing
            print("   🔀 Testing parallel processing...")
            
            # Test con múltiples workers vs single worker
            symbols_parallel = ['AAPL', 'GOOGL']
            timeframes_parallel = ['1d']
            
            # Single worker
            start_single = time.time()
            stats_single = self.downloader.download_batch(
                symbols=symbols_parallel,
                timeframes=timeframes_parallel,
                start_date='2024-01-01',
                end_date='2024-01-15',
                max_workers=1
            )
            time_single = time.time() - start_single
            
            # Multiple workers (si es posible)
            if config.PARALLEL_CONFIG.get('max_workers', 1) > 1:
                # Limpiar tareas completadas para re-test
                self.downloader.completed_tasks = set()
                
                start_parallel = time.time()
                stats_parallel = self.downloader.download_batch(
                    symbols=symbols_parallel,
                    timeframes=timeframes_parallel,
                    start_date='2024-01-01',
                    end_date='2024-01-15',
                    max_workers=2
                )
                time_parallel = time.time() - start_parallel
                
                speedup = time_single / time_parallel if time_parallel > 0 else 1.0
                
                if speedup > 1.2:
                    results['parallel_processing'] = f'✅ PASS - {speedup:.1f}x speedup'
                elif speedup > 0.8:
                    results['parallel_processing'] = f'⚠️ WARNING - {speedup:.1f}x speedup (minimal)'
                else:
                    results['parallel_processing'] = f'❌ FAIL - {speedup:.1f}x slowdown'
            else:
                results['parallel_processing'] = '⏭️ SKIP - Single worker configured'
            
            # Test 5: Overall performance
            total_time = (datetime.now() - self.start_time).total_seconds()
            
            if total_time < 60:
                results['overall_performance'] = f'✅ PASS - All tests completed in {total_time:.1f}s'
            elif total_time < 120:
                results['overall_performance'] = f'⚠️ WARNING - Tests took {total_time:.1f}s (slow)'
            else:
                results['overall_performance'] = f'❌ FAIL - Tests took {total_time:.1f}s (very slow)'
                
        except Exception as e:
            results['exception'] = f'💥 EXCEPTION - {str(e)}'
        
        self.test_results['performance'] = results
        self.print_test_results('PERFORMANCE', results)
    
    def print_test_results(self, category: str, results: Dict):
        """Imprimir resultados de una categoría de tests"""
        print(f"\n   📋 RESULTADOS {category}:")
        for test_name, result in results.items():
            print(f"      {test_name}: {result}")
    
    def generate_report(self):
        """Generar reporte final completo"""
        total_time = (datetime.now() - self.start_time).total_seconds()
        
        print("\n" + "=" * 60)
        print("📊 REPORTE FINAL - HISTORICAL SYSTEM TESTS")
        print("=" * 60)
        
        # Contar resultados por categoría
        category_stats = {}
        overall_stats = {'PASS': 0, 'WARNING': 0, 'FAIL': 0, 'SKIP': 0, 'EXCEPTION': 0}
        
        for category, tests in self.test_results.items():
            if category == 'error':
                continue
            
            stats = {'PASS': 0, 'WARNING': 0, 'FAIL': 0, 'SKIP': 0, 'EXCEPTION': 0}
            
            for test_name, result in tests.items():
                if '✅ PASS' in result:
                    stats['PASS'] += 1
                    overall_stats['PASS'] += 1
                elif '⚠️ WARNING' in result:
                    stats['WARNING'] += 1
                    overall_stats['WARNING'] += 1
                elif '❌ FAIL' in result:
                    stats['FAIL'] += 1
                    overall_stats['FAIL'] += 1
                elif '⏭️ SKIP' in result:
                    stats['SKIP'] += 1
                    overall_stats['SKIP'] += 1
                elif '💥 EXCEPTION' in result:
                    stats['EXCEPTION'] += 1
                    overall_stats['EXCEPTION'] += 1
            
            category_stats[category] = stats
        
        # Imprimir estadísticas por categoría
        for category, stats in category_stats.items():
            total_tests = sum(stats.values())
            if total_tests > 0:
                print(f"\n{category.upper().replace('_', ' ')}:")
                print(f"   ✅ Pass: {stats['PASS']}")
                print(f"   ⚠️ Warning: {stats['WARNING']}")
                print(f"   ❌ Fail: {stats['FAIL']}")
                print(f"   ⏭️ Skip: {stats['SKIP']}")
                if stats['EXCEPTION'] > 0:
                    print(f"   💥 Exception: {stats['EXCEPTION']}")
        
        # Estadísticas generales
        total_tests = sum(overall_stats.values())
        pass_rate = (overall_stats['PASS'] / total_tests * 100) if total_tests > 0 else 0
        
        print(f"\n📈 ESTADÍSTICAS GENERALES:")
        print(f"   Total tests: {total_tests}")
        print(f"   Pass rate: {pass_rate:.1f}%")
        print(f"   Time elapsed: {total_time:.1f} seconds")
        
        # Evaluación general del sistema
        print(f"\n🎯 EVALUACIÓN GENERAL:")
        if overall_stats['EXCEPTION'] > 0:
            print("   ❌ CRITICAL - Sistema tiene excepciones críticas")
        elif overall_stats['FAIL'] > overall_stats['PASS']:
            print("   ❌ POOR - Más fallos que éxitos")
        elif pass_rate >= 80:
            print("   ✅ EXCELLENT - Sistema funcionando correctamente")
        elif pass_rate >= 60:
            print("   ⚠️ GOOD - Sistema mayormente funcional con warnings")
        else:
            print("   ❌ NEEDS WORK - Sistema requiere mejoras significativas")
        
        # Guardar reporte en archivo
        self.save_report(total_time, overall_stats, category_stats)
    
    def save_report(self, total_time: float, overall_stats: Dict, category_stats: Dict):
        """Guardar reporte en archivo JSON"""
        try:
            report_data = {
                'timestamp': datetime.now().isoformat(),
                'total_time_seconds': total_time,
                'overall_stats': overall_stats,
                'category_stats': category_stats,
                'detailed_results': self.test_results
            }
            
            report_file = f"historical_data/logs/test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            os.makedirs(os.path.dirname(report_file), exist_ok=True)
            
            with open(report_file, 'w') as f:
                json.dump(report_data, f, indent=2)
            
            print(f"\n💾 Reporte guardado en: {report_file}")
            
        except Exception as e:
            print(f"❌ Error guardando reporte: {e}")

def quick_test():
    """Test rápido básico"""
    print("🚀 QUICK TEST - Funcionalidad Básica")
    print("-" * 40)
    
    tester = HistoricalSystemTester()
    
    # Solo test críticos
    tester.test_api_manager()
    
    print(f"\n⏱️ Quick test completado en {(datetime.now() - tester.start_time).total_seconds():.1f}s")

def main():
    """Función principal CLI"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Historical System Tester V3.0')
    parser.add_argument('--quick', action='store_true',
                       help='Ejecutar solo tests básicos')
    parser.add_argument('--category', choices=['api', 'downloader', 'quality', 'integration', 'performance'],
                       help='Ejecutar solo una categoría específica')
    
    args = parser.parse_args()
    
    if args.quick:
        quick_test()
        return
    
    tester = HistoricalSystemTester()
    
    if args.category:
        if args.category == 'api':
            tester.test_api_manager()
        elif args.category == 'downloader':
            tester.test_data_downloader()
        elif args.category == 'quality':
            tester.test_data_quality()
        elif args.category == 'integration':
            tester.test_integration()
        elif args.category == 'performance':
            tester.test_performance()
    else:
        tester.run_all_tests()

if __name__ == "__main__":
    main()