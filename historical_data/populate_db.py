#!/usr/bin/env python3
"""
💾 POPULATE DATABASE - LLENAR BD CON DATOS HISTÓRICOS V4.0
========================================================

Procesa archivos CSV descargados y los inserta en la base de datos,
calculando indicadores técnicos como el sistema principal.

🎯 FUNCIONES:
- Lee CSVs del directorio raw_data/
- Calcula indicadores técnicos (usando indicators.py del sistema principal)
- Inserta en tabla indicators_data de la base de datos
- Validación y limpieza de datos
- Progress tracking y estadísticas

📊 INTEGRACIÓN:
- Compatible 100% con sistema principal
- Mismos indicadores y formatos
- Lista para backtesting inmediato
"""

import os
import sys
import time
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple, Any
import logging
import argparse
import glob

# Setup paths para importar desde sistema principal
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, current_dir)
sys.path.insert(0, parent_dir)

# Imports
try:
    import config
    print("✅ Config cargado")
    
    # Import from main system
    from database.connection import get_connection, save_indicators_data
    print("✅ Database connection disponible")
    
    from indicators import TechnicalIndicators
    print("✅ Technical indicators disponibles")
    
except ImportError as e:
    print(f"❌ Error importing: {e}")
    print("📝 Asegúrate de estar en el directorio correcto y tener el sistema principal")
    sys.exit(1)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class DatabasePopulator:
    """Poblador de base de datos con datos históricos"""
    
    def __init__(self):
        self.indicators_calculator = TechnicalIndicators()
        self.stats = {
            'files_processed': 0,
            'files_failed': 0,
            'total_rows_processed': 0,
            'total_rows_inserted': 0,
            'start_time': time.time(),
            'symbols_processed': set(),
            'timeframes_processed': set()
        }
        
        logger.info("💾 Database Populator V4.0 inicializado")
    
    def find_csv_files(self, data_dir: str = None) -> List[str]:
        """Encontrar archivos CSV en directorio raw_data"""
        if not data_dir:
            data_dir = 'raw_data'  # Ruta simple y directa
        
        if not os.path.exists(data_dir):
            logger.error(f"❌ Directorio {data_dir} no existe")
            return []
        
        # Buscar archivos CSV
        csv_pattern = os.path.join(data_dir, "*.csv")
        csv_files = glob.glob(csv_pattern)
        
        logger.info(f"📁 Encontrados {len(csv_files)} archivos CSV")
        
        # Mostrar algunos ejemplos
        for i, file in enumerate(csv_files[:5]):
            filename = os.path.basename(file)
            file_size = os.path.getsize(file) / 1024  # KB
            logger.info(f"   {i+1}. {filename} ({file_size:.1f} KB)")
        
        if len(csv_files) > 5:
            logger.info(f"   ... y {len(csv_files) - 5} archivos más")
        
        return sorted(csv_files)
    
    def parse_filename(self, filepath: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Extraer información del nombre de archivo CSV"""
        try:
            filename = os.path.basename(filepath)
            # Formato esperado: SYMBOL_TIMEFRAME_TIMESTAMP.csv
            # Ejemplo: AAPL_1d_20250914_152039.csv
            
            parts = filename.replace('.csv', '').split('_')
            if len(parts) >= 2:
                symbol = parts[0]
                timeframe = parts[1]
                timestamp = '_'.join(parts[2:]) if len(parts) > 2 else None
                
                return symbol, timeframe, timestamp
            else:
                logger.warning(f"⚠️ Formato de archivo no reconocido: {filename}")
                return None, None, None
                
        except Exception as e:
            logger.error(f"❌ Error parsing filename {filepath}: {e}")
            return None, None, None
    
    def validate_csv_data(self, df: pd.DataFrame, symbol: str, timeframe: str) -> Tuple[bool, str]:
        """Validar datos del CSV"""
        try:
            # Verificar columnas requeridas
            required_columns = ['open', 'high', 'low', 'close', 'volume']
            missing_columns = [col for col in required_columns if col not in df.columns]
            
            if missing_columns:
                return False, f"Missing columns: {missing_columns}"
            
            # Verificar que no esté vacío
            if len(df) == 0:
                return False, "DataFrame is empty"
            
            # Verificar tipos de datos
            for col in ['open', 'high', 'low', 'close', 'volume']:
                if df[col].dtype not in ['float64', 'int64']:
                    try:
                        df[col] = pd.to_numeric(df[col], errors='coerce')
                    except:
                        return False, f"Cannot convert {col} to numeric"
            
            # Verificar valores razonables
            if (df['high'] < df['low']).any():
                return False, "High < Low found"
            
            if (df[['open', 'high', 'low', 'close']] <= 0).any().any():
                return False, "Zero or negative prices found"
            
            if (df['volume'] < 0).any():
                return False, "Negative volume found"
            
            # Verificar duplicados por timestamp
            if df.index.duplicated().any():
                logger.warning(f"⚠️ {symbol} {timeframe}: Removing {df.index.duplicated().sum()} duplicated timestamps")
                df = df[~df.index.duplicated()]
            
            logger.info(f"✅ {symbol} {timeframe}: Validation passed - {len(df)} rows")
            return True, f"Valid - {len(df)} rows"
            
        except Exception as e:
            return False, f"Validation error: {str(e)}"
    
    def calculate_indicators_for_df(self, df: pd.DataFrame, symbol: str) -> pd.DataFrame:
        """Calcular indicadores técnicos usando sistema principal"""
        try:
            logger.info(f"📊 Calculando indicadores para {symbol}...")
            
            # Preparar datos en formato que espera indicators.py
            # El sistema principal espera columnas con nombres específicos
            data_for_indicators = df.copy()
            
            # Asegurar que tenemos el timestamp como índice
            if 'timestamp' in data_for_indicators.columns:
                data_for_indicators = data_for_indicators.set_index('timestamp')
            
            # Renombrar si es necesario para compatibilidad
            column_mapping = {
                'Open': 'open', 'High': 'high', 'Low': 'low', 
                'Close': 'close', 'Volume': 'volume'
            }
            data_for_indicators = data_for_indicators.rename(columns=column_mapping)
            
            # Calcular todos los indicadores usando la clase del sistema principal
            indicators = self.indicators_calculator.calculate_all_indicators(
                data_for_indicators, symbol
            )
            
            # El método calculate_all_indicators devuelve un dict con todos los indicadores
            # Necesitamos convertirlo a format para la base de datos
            
            # Preparar DataFrame final para insertar
            result_rows = []
            
            # Para cada timestamp en los datos originales
            for idx, row in data_for_indicators.iterrows():
                try:
                    # Datos base OHLCV
                    base_data = {
                        'timestamp': idx if pd.notnull(idx) else datetime.now(),
                        'symbol': symbol,
                        'open_price': float(row['open']),
                        'high_price': float(row['high']),
                        'low_price': float(row['low']),
                        'close_price': float(row['close']),
                        'volume': int(row['volume']) if pd.notnull(row['volume']) else 0,
                    }
                    
                    # Agregar indicadores si están disponibles
                    if 'rsi' in indicators and 'rsi' in indicators['rsi']:
                        # RSI
                        rsi_values = indicators['rsi']['rsi_values']
                        if len(rsi_values) > 0 and not pd.isna(rsi_values.iloc[-1]):
                            base_data['rsi_value'] = float(rsi_values.iloc[-1])
                        else:
                            base_data['rsi_value'] = None
                    
                    if 'macd' in indicators:
                        # MACD
                        macd_data = indicators['macd']
                        base_data['macd_line'] = macd_data.get('macd_line')
                        base_data['macd_signal'] = macd_data.get('signal_line')
                        base_data['macd_histogram'] = macd_data.get('histogram')
                    
                    if 'roc' in indicators and 'roc' in indicators['roc']:
                        # ROC
                        base_data['roc_value'] = indicators['roc']['roc']
                    
                    if 'vwap' in indicators and 'vwap' in indicators['vwap']:
                        # VWAP
                        base_data['vwap_value'] = indicators['vwap']['vwap']
                    
                    if 'bollinger' in indicators:
                        # Bollinger Bands
                        bb_data = indicators['bollinger']
                        base_data['bb_upper'] = bb_data.get('upper_band')
                        base_data['bb_middle'] = bb_data.get('middle_band')
                        base_data['bb_lower'] = bb_data.get('lower_band')
                    
                    if 'atr' in indicators and 'atr' in indicators['atr']:
                        # ATR
                        base_data['atr_value'] = indicators['atr']['atr']
                    
                    if 'volume_osc' in indicators and 'volume_oscillator' in indicators['volume_osc']:
                        # Volume Oscillator
                        base_data['volume_oscillator'] = indicators['volume_osc']['volume_oscillator']
                    
                    result_rows.append(base_data)
                    
                except Exception as e:
                    logger.warning(f"⚠️ Error procesando row {idx}: {e}")
                    continue
            
            if not result_rows:
                logger.error(f"❌ No se pudieron procesar filas para {symbol}")
                return pd.DataFrame()
            
            result_df = pd.DataFrame(result_rows)
            logger.info(f"✅ {symbol}: Calculados indicadores para {len(result_df)} rows")
            
            return result_df
            
        except Exception as e:
            logger.error(f"❌ Error calculando indicadores para {symbol}: {e}")
            return pd.DataFrame()
    
    def insert_to_database(self, df: pd.DataFrame) -> Tuple[bool, str]:
        """Insertar datos en la base de datos"""
        try:
            # Convertir DataFrame a formato para save_indicators_data
            inserted_count = 0
            
            for _, row in df.iterrows():
                try:
                    # Crear dict con formato esperado por save_indicators_data
                    indicator_data = {
                        'timestamp': row['timestamp'],
                        'symbol': row['symbol'],
                        'current_price': row['close_price'],
                        'open_price': row['open_price'],
                        'high_price': row['high_price'], 
                        'low_price': row['low_price'],
                        'close_price': row['close_price'],
                        'volume': row['volume'],
                        'rsi_value': row.get('rsi_value'),
                        'macd_line': row.get('macd_line'),
                        'macd_signal': row.get('macd_signal'),
                        'macd_histogram': row.get('macd_histogram'),
                        'roc_value': row.get('roc_value'),
                        'vwap_value': row.get('vwap_value'),
                        'bb_upper': row.get('bb_upper'),
                        'bb_middle': row.get('bb_middle'),
                        'bb_lower': row.get('bb_lower'),
                        'atr_value': row.get('atr_value'),
                        'volume_oscillator': row.get('volume_oscillator')
                    }
                    
                    # Usar función del sistema principal para guardar
                    save_indicators_data(indicator_data)
                    inserted_count += 1
                    
                except Exception as e:
                    logger.warning(f"⚠️ Error insertando row: {e}")
                    continue
            
            logger.info(f"✅ Insertadas {inserted_count} filas en la base de datos")
            return True, f"Inserted {inserted_count} rows"
            
        except Exception as e:
            logger.error(f"❌ Error insertando en base de datos: {e}")
            return False, f"Database error: {str(e)}"
    
    def process_single_file(self, filepath: str) -> Tuple[bool, Dict[str, Any]]:
        """Procesar un archivo CSV individual"""
        filename = os.path.basename(filepath)
        logger.info(f"📄 Procesando: {filename}")
        
        file_stats = {
            'filename': filename,
            'filepath': filepath,
            'rows_read': 0,
            'rows_processed': 0,
            'rows_inserted': 0,
            'status': 'unknown',
            'message': '',
            'processing_time': 0
        }
        
        start_time = time.time()
        
        try:
            # Extraer info del filename
            symbol, timeframe, timestamp = self.parse_filename(filepath)
            if not symbol or not timeframe:
                file_stats.update({
                    'status': 'failed',
                    'message': 'Cannot parse filename'
                })
                return False, file_stats
            
            # Leer CSV
            try:
                df = pd.read_csv(filepath, index_col=0, parse_dates=True)
                file_stats['rows_read'] = len(df)
                
                if len(df) == 0:
                    file_stats.update({
                        'status': 'skipped',
                        'message': 'Empty file'
                    })
                    return False, file_stats
                
            except Exception as e:
                file_stats.update({
                    'status': 'failed',
                    'message': f'Cannot read CSV: {str(e)}'
                })
                return False, file_stats
            
            # Validar datos
            is_valid, validation_msg = self.validate_csv_data(df, symbol, timeframe)
            if not is_valid:
                file_stats.update({
                    'status': 'failed',
                    'message': f'Validation failed: {validation_msg}'
                })
                return False, file_stats
            
            # Agregar metadatos si no existen
            if 'symbol' not in df.columns:
                df['symbol'] = symbol
            if 'timeframe' not in df.columns:
                df['timeframe'] = timeframe
            
            file_stats['rows_processed'] = len(df)
            
            # Calcular indicadores técnicos
            df_with_indicators = self.calculate_indicators_for_df(df, symbol)
            
            if df_with_indicators.empty:
                file_stats.update({
                    'status': 'failed',
                    'message': 'Failed to calculate indicators'
                })
                return False, file_stats
            
            # Insertar en base de datos
            insert_success, insert_msg = self.insert_to_database(df_with_indicators)
            
            if insert_success:
                file_stats.update({
                    'status': 'completed',
                    'message': insert_msg,
                    'rows_inserted': len(df_with_indicators)
                })
                
                # Actualizar stats globales
                self.stats['symbols_processed'].add(symbol)
                self.stats['timeframes_processed'].add(timeframe)
                self.stats['total_rows_processed'] += len(df)
                self.stats['total_rows_inserted'] += len(df_with_indicators)
                
                return True, file_stats
            else:
                file_stats.update({
                    'status': 'failed',
                    'message': f'Database insertion failed: {insert_msg}'
                })
                return False, file_stats
                
        except Exception as e:
            file_stats.update({
                'status': 'failed',
                'message': f'Processing error: {str(e)}'
            })
            return False, file_stats
        
        finally:
            file_stats['processing_time'] = time.time() - start_time
    
    def process_all_files(self, csv_files: List[str]) -> Dict[str, Any]:
        """Procesar todos los archivos CSV"""
        logger.info(f"🚀 Procesando {len(csv_files)} archivos CSV...")
        
        results = {
            'total_files': len(csv_files),
            'completed_files': 0,
            'failed_files': 0,
            'skipped_files': 0,
            'file_results': [],
            'summary': {}
        }
        
        for i, filepath in enumerate(csv_files):
            logger.info(f"\n📊 Progreso: {i+1}/{len(csv_files)} ({((i+1)/len(csv_files)*100):.1f}%)")
            
            success, file_result = self.process_single_file(filepath)
            results['file_results'].append(file_result)
            
            if success:
                results['completed_files'] += 1
                self.stats['files_processed'] += 1
            else:
                if file_result['status'] == 'skipped':
                    results['skipped_files'] += 1
                else:
                    results['failed_files'] += 1
                    self.stats['files_failed'] += 1
            
            # Progress update cada 5 archivos
            if (i + 1) % 5 == 0:
                progress = ((i + 1) / len(csv_files)) * 100
                elapsed = time.time() - self.stats['start_time']
                eta = (elapsed / (i + 1)) * (len(csv_files) - i - 1)
                logger.info(f"📈 Progress: {progress:.1f}% - ETA: {eta:.0f}s")
        
        # Estadísticas finales
        total_time = time.time() - self.stats['start_time']
        success_rate = (results['completed_files'] / len(csv_files)) * 100 if csv_files else 0
        
        results['summary'] = {
            'success_rate': success_rate,
            'total_processing_time': total_time,
            'symbols_processed': list(self.stats['symbols_processed']),
            'timeframes_processed': list(self.stats['timeframes_processed']),
            'total_rows_processed': self.stats['total_rows_processed'],
            'total_rows_inserted': self.stats['total_rows_inserted'],
            'avg_processing_time': total_time / len(csv_files) if csv_files else 0
        }
        
        return results

def main():
    """Función principal CLI"""
    parser = argparse.ArgumentParser(description='Database Populator V4.0')
    parser.add_argument('--data-dir', default=None,
                       help='Directorio con archivos CSV (default: raw_data/)')
    parser.add_argument('--test', action='store_true',
                       help='Modo test: solo procesar un archivo')
    parser.add_argument('--symbol', default=None,
                       help='Procesar solo archivos de un símbolo específico')
    
    args = parser.parse_args()
    
    print(f"💾 DATABASE POPULATOR V4.0")
    print(f"=" * 50)
    
    # Inicializar populator
    populator = DatabasePopulator()
    
    # Encontrar archivos CSV
    csv_files = populator.find_csv_files(args.data_dir)
    
    if not csv_files:
        print(f"❌ No se encontraron archivos CSV")
        print(f"💡 Ejecuta primero: python downloader.py --test")
        return
    
    # Filtrar por símbolo si se especifica
    if args.symbol:
        csv_files = [f for f in csv_files if args.symbol.upper() in os.path.basename(f).upper()]
        print(f"🔍 Filtrado por símbolo {args.symbol}: {len(csv_files)} archivos")
    
    # Modo test: solo primer archivo
    if args.test:
        csv_files = csv_files[:1]
        print(f"🧪 MODO TEST: Solo procesando primer archivo")
    
    # Procesar archivos
    start_time = time.time()
    results = populator.process_all_files(csv_files)
    total_time = time.time() - start_time
    
    # Mostrar resultados finales
    print(f"\n" + "=" * 50)
    print(f"📊 RESULTADOS FINALES")
    print(f"=" * 50)
    print(f"✅ Archivos completados: {results['completed_files']}")
    print(f"❌ Archivos fallidos: {results['failed_files']}")
    print(f"⏭️ Archivos omitidos: {results['skipped_files']}")
    print(f"📊 Tasa éxito: {results['summary']['success_rate']:.1f}%")
    print(f"⏱️ Tiempo total: {total_time:.1f}s")
    
    # Detalles de procesamiento
    summary = results['summary']
    print(f"\n📈 ESTADÍSTICAS DE DATOS:")
    print(f"   Símbolos procesados: {len(summary['symbols_processed'])} ({', '.join(summary['symbols_processed'])})")
    print(f"   Timeframes procesados: {', '.join(summary['timeframes_processed'])}")
    print(f"   Filas procesadas: {summary['total_rows_processed']:,}")
    print(f"   Filas insertadas: {summary['total_rows_inserted']:,}")
    
    # Archivos con errores
    failed_files = [r for r in results['file_results'] if r['status'] == 'failed']
    if failed_files:
        print(f"\n❌ ARCHIVOS CON ERRORES:")
        for file_result in failed_files[:5]:  # Mostrar primeros 5
            print(f"   {file_result['filename']}: {file_result['message']}")
        if len(failed_files) > 5:
            print(f"   ... y {len(failed_files) - 5} más")
    
    # Siguiente paso
    if results['completed_files'] > 0:
        print(f"\n🎉 ¡Base de datos poblada exitosamente!")
        print(f"💡 Siguiente paso: python backtest_engine.py")
    else:
        print(f"\n⚠️ No se procesaron archivos exitosamente")
        print(f"💡 Revisa los errores y verifica los archivos CSV")

if __name__ == "__main__":
    main()