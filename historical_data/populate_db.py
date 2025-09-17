#!/usr/bin/env python3
"""
📊 DATABASE POPULATOR V3.0 - OPTIMIZADO PARA TUS CSVS
====================================================

Nuevo sistema de población optimizado para los formatos específicos de CSV descargados:

FORMATO 1 (1h): Datetime,open,high,low,close,volume,Dividends,Stock Splits,symbol,timeframe,timestamp
FORMATO 2 (15m): timestamp,open,high,low,close,volume,symbol,timeframe

🎯 CARACTERÍSTICAS:
- Auto-detección de formato de CSV
- Normalización de timestamps a UTC
- Población de ohlcv_data + indicators_data
- Procesamiento por lotes eficiente
- Validación robusta de datos OHLCV
- Cálculo de indicadores con contexto histórico
- Resume capability y modo incremental

USO:
    python populate_db.py                    # Procesar todos los CSVs
    python populate_db.py --force             # Sobrescribir datos existentes
    python populate_db.py --test             # Solo primeros 2 archivos
    python populate_db.py --symbol AAPL      # Solo archivos de AAPL
    python populate_db.py --validate-only    # Solo validar, no poblar
"""

import os
import sys
import pandas as pd
import numpy as np
import logging
import argparse
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
import sqlite3
from pathlib import Path
import time
import json

# Configurar paths correctamente
current_dir = Path(__file__).parent.absolute()
project_root = current_dir.parent if current_dir.name == 'historical_data' else current_dir
sys.path.insert(0, str(project_root))

# Imports del sistema
try:
    import config
    from database.connection import get_connection
    from indicators import TechnicalIndicators
    print("✅ Módulos del sistema importados correctamente")
except ImportError as e:
    print(f"❌ Error importando módulos: {e}")
    sys.exit(1)

# Configurar logging detallado
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

class DataPopulator:
    """Poblador de datos históricos optimizado"""
    
    def __init__(self, force_mode: bool = False, batch_size: int = 100):
        self.force_mode = force_mode
        self.batch_size = batch_size
        self.project_root = project_root
        self.csv_dir = project_root / 'historical_data' / 'raw_data'
        
        # Componentes del sistema
        self.db_conn = None
        self.indicators_calc = None
        
        # Estadísticas
        self.stats = {
            'files_processed': 0,
            'files_skipped': 0,
            'files_failed': 0,
            'total_csv_rows': 0,
            'ohlcv_rows_inserted': 0,
            'indicators_rows_inserted': 0,
            'symbols_processed': set(),
            'timeframes_processed': set(),
            'start_time': time.time(),
            'errors': [],
            'warnings': []
        }
    
    def initialize(self) -> bool:
        """Inicializar conexiones y componentes"""
        try:
            logger.info("🔧 Inicializando sistema...")
            
            # Test database connection
            self.db_conn = get_connection()
            if self.db_conn is None:
                logger.error("❌ No se pudo conectar a la base de datos")
                return False
            
            # Verificar que las tablas existen
            cursor = self.db_conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [row[0] for row in cursor.fetchall()]
            
            required_tables = ['ohlcv_data', 'indicators_data']
            missing_tables = [t for t in required_tables if t not in tables]
            
            if missing_tables:
                logger.error(f"❌ Tablas faltantes: {missing_tables}")
                return False
            
            # Inicializar calculadora de indicadores
            self.indicators_calc = TechnicalIndicators()
            
            logger.info("✅ Sistema inicializado correctamente")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error en inicialización: {e}")
            return False
    
    def detect_csv_format(self, file_path: Path) -> Optional[str]:
        """Detectar el formato del CSV"""
        try:
            # Leer solo las primeras filas para detectar formato
            sample = pd.read_csv(file_path, nrows=3)
            columns = set(sample.columns.str.lower())
            
            # FORMATO 1: Datetime,open,high,low,close,volume,Dividends,Stock Splits,symbol,timeframe,timestamp
            format1_indicators = {'datetime', 'dividends', 'stock splits'}
            
            # FORMATO 2: timestamp,open,high,low,close,volume,symbol,timeframe
            format2_indicators = {'timestamp'}
            
            if format1_indicators.issubset(columns):
                return 'format1'
            elif format2_indicators.issubset(columns) and 'datetime' not in columns:
                return 'format2'
            else:
                return None
                
        except Exception as e:
            logger.error(f"❌ Error detectando formato de {file_path.name}: {e}")
            return None
    
    def parse_filename(self, filename: str) -> Optional[Dict[str, str]]:
        """Parsear información del filename"""
        try:
            # Formato esperado: SYMBOL_TIMEFRAME_YYYYMMDD_HHMMSS.csv
            name_parts = filename.replace('.csv', '').split('_')
            
            if len(name_parts) >= 2:
                return {
                    'symbol': name_parts[0].upper(),
                    'timeframe': name_parts[1],
                    'date_part': name_parts[2] if len(name_parts) > 2 else '',
                    'time_part': name_parts[3] if len(name_parts) > 3 else ''
                }
            else:
                return None
                
        except Exception as e:
            logger.warning(f"⚠️ Error parseando filename {filename}: {e}")
            return None
    
    def normalize_dataframe(self, df: pd.DataFrame, csv_format: str, file_info: Dict) -> pd.DataFrame:
        """Normalizar DataFrame según formato detectado"""
        try:
            df_clean = df.copy()
            
            # Normalizar nombres de columnas a lowercase
            df_clean.columns = df_clean.columns.str.lower()
            
            if csv_format == 'format1':
                # FORMATO 1: usar columna 'timestamp' como timestamp principal
                if 'timestamp' in df_clean.columns:
                    df_clean['timestamp_norm'] = pd.to_datetime(df_clean['timestamp'])
                elif 'datetime' in df_clean.columns:
                    df_clean['timestamp_norm'] = pd.to_datetime(df_clean['datetime'])
                else:
                    raise ValueError("No timestamp column found in format1")
                
                # Mapear columnas adicionales
                df_clean['dividends_norm'] = df_clean.get('dividends', 0.0)
                df_clean['stock_splits_norm'] = df_clean.get('stock splits', 0.0)
                
            elif csv_format == 'format2':
                # FORMATO 2: usar columna 'timestamp'
                df_clean['timestamp_norm'] = pd.to_datetime(df_clean['timestamp'])
                df_clean['dividends_norm'] = 0.0
                df_clean['stock_splits_norm'] = 0.0
            
            # Normalizar columnas OHLCV básicas
            df_clean['open_norm'] = pd.to_numeric(df_clean['open'], errors='coerce')
            df_clean['high_norm'] = pd.to_numeric(df_clean['high'], errors='coerce')
            df_clean['low_norm'] = pd.to_numeric(df_clean['low'], errors='coerce')
            df_clean['close_norm'] = pd.to_numeric(df_clean['close'], errors='coerce')
            df_clean['volume_norm'] = pd.to_numeric(df_clean['volume'], errors='coerce').fillna(0).astype(int)
            
            # Agregar metadatos
            df_clean['symbol_norm'] = file_info['symbol']
            df_clean['timeframe_norm'] = file_info['timeframe']
            df_clean['source_file'] = file_info.get('filename', '')
            
            # Filtrar filas con datos válidos
            valid_mask = (
                df_clean['timestamp_norm'].notna() &
                df_clean['open_norm'].notna() &
                df_clean['high_norm'].notna() &
                df_clean['low_norm'].notna() &
                df_clean['close_norm'].notna() &
                (df_clean['close_norm'] > 0) &
                (df_clean['high_norm'] >= df_clean['low_norm'])
            )
            
            df_final = df_clean[valid_mask].copy()
            
            # Ordenar por timestamp
            df_final = df_final.sort_values('timestamp_norm').reset_index(drop=True)
            
            logger.info(f"📊 Normalizados {len(df_final)}/{len(df)} filas válidas")
            
            return df_final
            
        except Exception as e:
            logger.error(f"❌ Error normalizando DataFrame: {e}")
            return pd.DataFrame()
    
    def validate_ohlcv_data(self, df: pd.DataFrame) -> Tuple[bool, str, pd.DataFrame]:
        """Validar datos OHLCV normalizados"""
        try:
            if df.empty:
                return False, "DataFrame vacío después de normalización", df
            
            # Verificar rangos básicos
            invalid_ohlc = (df['high_norm'] < df['low_norm']).any()
            if invalid_ohlc:
                logger.warning("⚠️ Datos con High < Low detectados, corrigiendo...")
                # Corregir intercambiando high y low donde sea necesario
                mask = df['high_norm'] < df['low_norm']
                df.loc[mask, ['high_norm', 'low_norm']] = df.loc[mask, ['low_norm', 'high_norm']].values
            
            # Verificar precios negativos o cero
            negative_prices = (
                (df['open_norm'] <= 0) | 
                (df['high_norm'] <= 0) | 
                (df['low_norm'] <= 0) | 
                (df['close_norm'] <= 0)
            ).sum()
            
            if negative_prices > 0:
                logger.warning(f"⚠️ {negative_prices} filas con precios <= 0, eliminando...")
                df = df[
                    (df['open_norm'] > 0) & 
                    (df['high_norm'] > 0) & 
                    (df['low_norm'] > 0) & 
                    (df['close_norm'] > 0)
                ].copy()
            
            # Verificar que tenemos suficientes datos
            if len(df) < 10:
                return False, f"Insuficientes datos válidos: {len(df)} filas", df
            
            # Detectar outliers extremos (cambios de precio > 50% en una vela)
            df['price_change_pct'] = abs(df['close_norm'].pct_change()) * 100
            extreme_changes = (df['price_change_pct'] > 50).sum()
            
            if extreme_changes > 0:
                self.stats['warnings'].append(f"Detected {extreme_changes} extreme price changes (>50%)")
            
            return True, f"Valid - {len(df)} rows", df
            
        except Exception as e:
            return False, f"Validation error: {str(e)}", df
    
    def save_ohlcv_batch(self, df: pd.DataFrame) -> int:
        """Guardar lote de datos OHLCV en la base de datos"""
        try:
            if df.empty:
                return 0
            
            cursor = self.db_conn.cursor()
            
            # Preparar datos para inserción
            insert_data = []
            for _, row in df.iterrows():
                insert_data.append((
                    row['timestamp_norm'].isoformat(),
                    row['symbol_norm'],
                    row['timeframe_norm'],
                    float(row['open_norm']),
                    float(row['high_norm']),
                    float(row['low_norm']),
                    float(row['close_norm']),
                    int(row['volume_norm']),
                    float(row['dividends_norm']),
                    float(row['stock_splits_norm']),
                    row['source_file']
                ))
            
            # Insertar usando INSERT OR IGNORE para evitar duplicados
            cursor.executemany('''
                INSERT OR IGNORE INTO ohlcv_data 
                (timestamp, symbol, timeframe, open_price, high_price, low_price, 
                 close_price, volume, dividends, stock_splits, source_file)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', insert_data)
            
            rows_inserted = cursor.rowcount
            self.db_conn.commit()
            
            return rows_inserted
            
        except Exception as e:
            logger.error(f"❌ Error guardando OHLCV batch: {e}")
            return 0
    
    def calculate_and_save_indicators(self, df: pd.DataFrame, symbol: str) -> int:
        """Calcular indicadores y guardarlos en indicators_data"""
        try:
            if len(df) < 50:  # Necesitamos suficiente contexto para indicadores
                logger.warning(f"⚠️ {symbol}: Insuficientes datos para indicadores ({len(df)} filas)")
                return 0
            
            # Preparar DataFrame para TechnicalIndicators
            df_indicators = df.set_index('timestamp_norm').sort_index()
            df_indicators = df_indicators.rename(columns={
                'open_norm': 'Open',
                'high_norm': 'High',
                'low_norm': 'Low',
                'close_norm': 'Close',
                'volume_norm': 'Volume'
            })
            
            # Calcular indicadores usando métodos individuales
            logger.info(f"📊 Calculando indicadores para {symbol}...")
            
            # RSI
            try:
                rsi_data = self.indicators_calc.calculate_rsi(df_indicators)
                current_rsi = rsi_data.get('rsi', 0) if rsi_data else 0
            except:
                current_rsi = 0
            
            # MACD
            try:
                macd_data = self.indicators_calc.calculate_macd(df_indicators)
                current_macd = macd_data.get('macd', 0) if macd_data else 0
                current_macd_signal = macd_data.get('signal', 0) if macd_data else 0
                current_macd_hist = macd_data.get('histogram', 0) if macd_data else 0
            except:
                current_macd = current_macd_signal = current_macd_hist = 0
            
            # VWAP
            try:
                vwap_data = self.indicators_calc.calculate_vwap(df_indicators)
                current_vwap = vwap_data.get('vwap', 0) if vwap_data else 0
                vwap_deviation = vwap_data.get('deviation_pct', 0) if vwap_data else 0
            except:
                current_vwap = vwap_deviation = 0
            
            # Bollinger Bands
            try:
                bb_data = self.indicators_calc.calculate_bollinger_bands(df_indicators)
                bb_upper = bb_data.get('upper_band', 0) if bb_data else 0
                bb_middle = bb_data.get('middle_band', 0) if bb_data else 0
                bb_lower = bb_data.get('lower_band', 0) if bb_data else 0
                bb_position = bb_data.get('bb_position', 0.5) if bb_data else 0.5
            except:
                bb_upper = bb_middle = bb_lower = 0
                bb_position = 0.5
            
            # Usar la última fila para el timestamp e insertar indicadores
            last_row = df_indicators.iloc[-1]
            timestamp = last_row.name.isoformat()
            
            cursor = self.db_conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO indicators_data 
                (timestamp, symbol, open_price, high_price, low_price, close_price, volume,
                 rsi_value, macd_line, macd_signal, macd_histogram, vwap_value, vwap_deviation_pct,
                 bb_upper, bb_middle, bb_lower, bb_position, market_regime, volatility_level)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                timestamp,
                symbol,
                float(last_row['Open']),
                float(last_row['High']),
                float(last_row['Low']),
                float(last_row['Close']),
                int(last_row['Volume']),
                current_rsi,
                current_macd,
                current_macd_signal,
                current_macd_hist,
                current_vwap,
                vwap_deviation,
                bb_upper,
                bb_middle,
                bb_lower,
                bb_position,
                'HISTORICAL',
                'NORMAL'
            ))
            
            self.db_conn.commit()
            return 1
            
        except Exception as e:
            logger.error(f"❌ Error calculando indicadores para {symbol}: {e}")
            return 0
    
    def process_csv_file(self, file_path: Path) -> bool:
        """Procesar un archivo CSV individual"""
        try:
            logger.info(f"📄 Procesando: {file_path.name}")
            
            # Parsear información del archivo
            file_info = self.parse_filename(file_path.name)
            if not file_info:
                logger.error(f"❌ {file_path.name}: Formato de nombre inválido")
                return False
            
            file_info['filename'] = file_path.name
            symbol = file_info['symbol']
            timeframe = file_info['timeframe']
            
            # Verificar si ya existe data (modo incremental)
            if not self.force_mode:
                cursor = self.db_conn.cursor()
                cursor.execute('''
                    SELECT COUNT(*) FROM ohlcv_data 
                    WHERE symbol = ? AND timeframe = ?
                ''', (symbol, timeframe))
                
                existing_count = cursor.fetchone()[0]
                if existing_count > 0:
                    logger.info(f"⏭️ {symbol} {timeframe}: {existing_count} registros existentes, saltando")
                    self.stats['files_skipped'] += 1
                    return True
            
            # Detectar formato del CSV
            csv_format = self.detect_csv_format(file_path)
            if not csv_format:
                logger.error(f"❌ {file_path.name}: Formato CSV no reconocido")
                return False
            
            logger.info(f"📋 Formato detectado: {csv_format}")
            
            # Leer CSV
            df_raw = pd.read_csv(file_path)
            self.stats['total_csv_rows'] += len(df_raw)
            
            # Normalizar DataFrame
            df_normalized = self.normalize_dataframe(df_raw, csv_format, file_info)
            if df_normalized.empty:
                logger.error(f"❌ {file_path.name}: Sin datos válidos después de normalización")
                return False
            
            # Validar datos OHLCV
            is_valid, validation_msg, df_clean = self.validate_ohlcv_data(df_normalized)
            if not is_valid:
                logger.error(f"❌ {file_path.name}: {validation_msg}")
                return False
            
            logger.info(f"✅ Validación: {validation_msg}")
            
            # Guardar datos OHLCV
            ohlcv_inserted = self.save_ohlcv_batch(df_clean)
            self.stats['ohlcv_rows_inserted'] += ohlcv_inserted
            
            if ohlcv_inserted > 0:
                logger.info(f"💾 OHLCV guardado: {ohlcv_inserted} filas")
                
                # Calcular y guardar indicadores
                indicators_inserted = self.calculate_and_save_indicators(df_clean, symbol)
                self.stats['indicators_rows_inserted'] += indicators_inserted
                
                if indicators_inserted > 0:
                    logger.info(f"📊 Indicadores guardados: {indicators_inserted} filas")
                
                # Actualizar estadísticas
                self.stats['symbols_processed'].add(symbol)
                self.stats['timeframes_processed'].add(timeframe)
                self.stats['files_processed'] += 1
                
                return True
            else:
                logger.warning(f"⚠️ {file_path.name}: No se insertaron datos (posibles duplicados)")
                return True
                
        except Exception as e:
            logger.error(f"❌ Error procesando {file_path.name}: {e}")
            self.stats['errors'].append(f"{file_path.name}: {str(e)}")
            self.stats['files_failed'] += 1
            return False
    
    def get_csv_files(self, symbol_filter: str = None) -> List[Path]:
        """Obtener lista de archivos CSV a procesar"""
        try:
            if not self.csv_dir.exists():
                logger.error(f"❌ Directorio no existe: {self.csv_dir}")
                return []
            
            csv_files = list(self.csv_dir.glob("*.csv"))
            
            if symbol_filter:
                csv_files = [f for f in csv_files if f.name.upper().startswith(symbol_filter.upper())]
            
            # Ordenar por tamaño (archivos pequeños primero para testing)
            csv_files.sort(key=lambda x: x.stat().st_size)
            
            logger.info(f"📁 Encontrados {len(csv_files)} archivos CSV")
            return csv_files
            
        except Exception as e:
            logger.error(f"❌ Error obteniendo archivos CSV: {e}")
            return []
    
    def run(self, symbol_filter: str = None, test_mode: bool = False, validate_only: bool = False) -> Dict:
        """Ejecutar el proceso completo de población"""
        logger.info("🚀 INICIANDO POBLACIÓN DE DATOS HISTÓRICOS")
        logger.info("=" * 60)
        
        # Inicializar sistema
        if not self.initialize():
            return self.get_final_stats()
        
        # Obtener archivos CSV
        csv_files = self.get_csv_files(symbol_filter)
        if not csv_files:
            logger.warning("⚠️ No se encontraron archivos CSV")
            return self.get_final_stats()
        
        # Filtrar para modo test
        if test_mode:
            csv_files = csv_files[:2]
            logger.info(f"🧪 MODO TEST: Solo procesando {len(csv_files)} archivos")
        
        # Procesar archivos
        for i, csv_file in enumerate(csv_files, 1):
            try:
                progress = (i / len(csv_files)) * 100
                logger.info(f"\n📊 [{i}/{len(csv_files)}] ({progress:.1f}%) - {csv_file.name}")
                
                if validate_only:
                    # Solo validar formato
                    csv_format = self.detect_csv_format(csv_file)
                    if csv_format:
                        logger.info(f"✅ {csv_file.name}: Formato {csv_format} válido")
                    else:
                        logger.error(f"❌ {csv_file.name}: Formato inválido")
                else:
                    # Procesar completamente
                    success = self.process_csv_file(csv_file)
                    if success:
                        logger.info(f"✅ {csv_file.name}: Completado")
                    else:
                        logger.error(f"❌ {csv_file.name}: Falló")
                
                # Pausa pequeña para no sobrecargar
                time.sleep(0.1)
                
            except KeyboardInterrupt:
                logger.info("🛑 Proceso interrumpido por usuario")
                break
            except Exception as e:
                logger.error(f"❌ Error inesperado con {csv_file.name}: {e}")
                continue
        
        return self.get_final_stats()
    
    def get_final_stats(self) -> Dict:
        """Obtener estadísticas finales"""
        elapsed_time = time.time() - self.stats['start_time']
        
        return {
            'files_processed': self.stats['files_processed'],
            'files_skipped': self.stats['files_skipped'],
            'files_failed': self.stats['files_failed'],
            'total_csv_rows': self.stats['total_csv_rows'],
            'ohlcv_rows_inserted': self.stats['ohlcv_rows_inserted'],
            'indicators_rows_inserted': self.stats['indicators_rows_inserted'],
            'symbols_processed': list(self.stats['symbols_processed']),
            'timeframes_processed': list(self.stats['timeframes_processed']),
            'elapsed_time': elapsed_time,
            'errors': self.stats['errors'],
            'warnings': self.stats['warnings']
        }
    
    def print_final_report(self, stats: Dict):
        """Imprimir reporte final"""
        print("\n" + "=" * 60)
        print("📋 REPORTE FINAL DE POBLACIÓN")
        print("=" * 60)
        
        print(f"⏱️  Tiempo total: {stats['elapsed_time']:.1f} segundos")
        print(f"📁 Archivos procesados: {stats['files_processed']}")
        print(f"⏭️  Archivos saltados: {stats['files_skipped']}")
        print(f"❌ Archivos fallidos: {stats['files_failed']}")
        
        print(f"\n📊 DATOS:")
        print(f"   CSV rows leídas: {stats['total_csv_rows']:,}")
        print(f"   OHLCV insertadas: {stats['ohlcv_rows_inserted']:,}")
        print(f"   Indicadores insertados: {stats['indicators_rows_inserted']:,}")
        
        if stats['symbols_processed']:
            print(f"\n📈 Símbolos: {', '.join(sorted(stats['symbols_processed']))}")
        
        if stats['timeframes_processed']:
            print(f"⏰ Timeframes: {', '.join(sorted(stats['timeframes_processed']))}")
        
        # Calcular success rate
        total_attempts = stats['files_processed'] + stats['files_failed']
        if total_attempts > 0:
            success_rate = (stats['files_processed'] / total_attempts) * 100
            print(f"✅ Success rate: {success_rate:.1f}%")
        
        # Mostrar errores
        if stats['errors']:
            print(f"\n❌ ERRORES ({len(stats['errors'])}):")
            for error in stats['errors'][:5]:
                print(f"   • {error}")
            if len(stats['errors']) > 5:
                print(f"   ... y {len(stats['errors']) - 5} más")
        
        # Mostrar warnings
        if stats['warnings']:
            print(f"\n⚠️  WARNINGS ({len(stats['warnings'])}):")
            for warning in stats['warnings'][:3]:
                print(f"   • {warning}")
        
        # Próximos pasos
        print(f"\n🚀 PRÓXIMOS PASOS:")
        if stats['ohlcv_rows_inserted'] > 0:
            print("   1. ✅ Datos poblados exitosamente")
            print("   2. Crear motor de backtesting")
            print("   3. Ejecutar análisis de performance")
        else:
            print("   1. ❌ No se insertaron datos")
            print("   2. Revisar errores mostrados arriba")
            print("   3. Verificar archivos CSV en raw_data/")

def main():
    """Función principal con argumentos CLI"""
    parser = argparse.ArgumentParser(
        description='Poblador de datos históricos V3.0',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python populate_db.py                     # Procesar todos los CSVs
  python populate_db.py --force              # Sobrescribir datos existentes
  python populate_db.py --test              # Solo primeros 2 archivos  
  python populate_db.py --symbol AAPL       # Solo archivos de AAPL
  python populate_db.py --validate-only     # Solo validar formato
        """
    )
    
    parser.add_argument('--force', action='store_true',
                       help='Sobrescribir datos existentes')
    parser.add_argument('--test', action='store_true', 
                       help='Modo test: solo primeros 2 archivos')
    parser.add_argument('--symbol', type=str, metavar='SYMBOL',
                       help='Procesar solo archivos de un símbolo específico')
    parser.add_argument('--validate-only', action='store_true',
                       help='Solo validar formato de CSVs sin poblar')
    parser.add_argument('--batch-size', type=int, default=100,
                       help='Tamaño de lote para inserción (default: 100)')
    
    args = parser.parse_args()
    
    # Crear populator
    populator = DataPopulator(
        force_mode=args.force,
        batch_size=args.batch_size
    )
    
    # Ejecutar proceso
    try:
        stats = populator.run(
            symbol_filter=args.symbol,
            test_mode=args.test,
            validate_only=args.validate_only
        )
        
        # Mostrar reporte final
        populator.print_final_report(stats)
        
        # Cerrar conexión DB
        if populator.db_conn:
            populator.db_conn.close()
        
        # Exit code basado en éxito
        if stats['files_failed'] == 0:
            print("\n🎉 ¡PROCESO COMPLETADO EXITOSAMENTE!")
            sys.exit(0)
        else:
            print(f"\n⚠️ Proceso completado con {stats['files_failed']} errores")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n🛑 Proceso cancelado por usuario")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Error fatal: {e}")
        print(f"\n💥 Error fatal: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()