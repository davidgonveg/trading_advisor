#!/usr/bin/env python3
"""
📊 DATABASE POPULATOR V4.0 - TRADING SYSTEM
===========================================

Pobla la base de datos con datos históricos + indicadores técnicos calculados
- Lee archivos CSV de historical_data/raw_data/
- Calcula indicadores usando TechnicalIndicators existente
- Guarda todo en database usando save_indicators_data()

CORREGIDO: Rutas, imports y compatibilidad con estructura del proyecto
"""

import os
import sys
import pandas as pd
import logging
import argparse
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import time

# Agregar paths necesarios - desde historical_data/ subir un nivel al proyecto principal
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.insert(0, project_root)

# Imports de nuestro sistema
try:
    import config
    from database.connection import get_connection, save_indicators_data
    from indicators import TechnicalIndicators
    print("✅ Config cargado")
    print("✅ Database connection disponible") 
    print("✅ Technical indicators disponibles")
except ImportError as e:
    print(f"❌ Error importing modules: {e}")
    print("💡 Asegúrate de estar en historical_data/ y que todos los módulos estén disponibles")
    sys.exit(1)

# Configurar logging
logging.basicConfig(
    level=getattr(logging, getattr(config, 'LOG_LEVEL', 'INFO'), 'INFO'),
    format='%(levelname)s:%(name)s:%(message)s'
)
logger = logging.getLogger(__name__)

class HistoricalDataPopulator:
    """Clase para poblar la base de datos con datos históricos"""
    
    def __init__(self):
        """Inicializar el populador"""
        self.db_conn = None
        self.indicators_calculator = None
        self.stats = {
            'files_completed': 0,
            'files_failed': 0,
            'files_skipped': 0,
            'symbols_processed': set(),
            'timeframes_processed': set(),
            'rows_processed': 0,
            'rows_inserted': 0,
            'start_time': time.time()
        }
        self.errors = []
        
    def initialize(self) -> bool:
        """
        Inicializar conexiones y dependencias
        
        Returns:
            bool: True si todo está listo
        """
        try:
            # Test database connection
            self.db_conn = get_connection()
            if self.db_conn is None:
                logger.error("❌ No se pudo conectar a la base de datos")
                return False
            self.db_conn.close()  # Cerrar conexión de test
            print("✅ Database connection disponible")
            
            # Initialize technical indicators
            self.indicators_calculator = TechnicalIndicators()
            print("✅ Technical indicators disponibles")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error en inicialización: {e}")
            return False
    
    def find_csv_files(self, data_dir: str = "raw_data") -> List[Tuple[str, str, float]]:
        """
        Encontrar todos los archivos CSV en el directorio
        
        Args:
            data_dir: Directorio donde buscar archivos CSV (relativo a historical_data/)
            
        Returns:
            List de tuplas (filename, full_path, size_kb)
        """
        csv_files = []
        
        # Asegurar que el directorio es relativo a historical_data/
        full_data_dir = os.path.join(current_dir, data_dir)
        
        if not os.path.exists(full_data_dir):
            logger.warning(f"⚠️ Directorio {full_data_dir} no existe")
            return csv_files
        
        for filename in os.listdir(full_data_dir):
            if filename.endswith('.csv'):
                full_path = os.path.join(full_data_dir, filename)
                size_kb = os.path.getsize(full_path) / 1024
                csv_files.append((filename, full_path, size_kb))
        
        # Ordenar por tamaño (archivos más pequeños primero para testing)
        csv_files.sort(key=lambda x: x[2])
        
        return csv_files
    
    def parse_filename(self, filename: str) -> Optional[Dict[str, str]]:
        """
        Parsear información del nombre del archivo
        
        Formato esperado: SYMBOL_TIMEFRAME_YYYYMMDD_HHMMSS.csv
        Ejemplo: AAPL_1d_20250914_152039.csv
        
        Args:
            filename: Nombre del archivo
            
        Returns:
            Dict con symbol, timeframe, date, time o None si no se puede parsear
        """
        try:
            # Remover extensión .csv
            name_parts = filename.replace('.csv', '').split('_')
            
            if len(name_parts) < 4:
                logger.warning(f"⚠️ Filename format not recognized: {filename}")
                return None
                
            return {
                'symbol': name_parts[0],
                'timeframe': name_parts[1],
                'date': name_parts[2],
                'time': name_parts[3]
            }
            
        except Exception as e:
            logger.error(f"❌ Error parsing filename {filename}: {e}")
            return None
    
    def validate_csv_data(self, df: pd.DataFrame, symbol: str) -> Tuple[bool, str]:
        """
        Validar que el CSV tenga el formato correcto
        
        Args:
            df: DataFrame con datos CSV
            symbol: Símbolo del archivo
            
        Returns:
            Tuple (is_valid, error_message)
        """
        try:
            # Verificar columnas requeridas (coincide con el formato del CSV real)
            required_columns = ['open', 'high', 'low', 'close', 'volume']
            missing_columns = [col for col in required_columns if col not in df.columns]
            
            if missing_columns:
                return False, f"Missing columns: {missing_columns}"
            
            # Verificar que no esté vacío
            if len(df) == 0:
                return False, "Empty DataFrame"
            
            # Verificar tipos de datos numéricos
            numeric_columns = ['open', 'high', 'low', 'close', 'volume']
            for col in numeric_columns:
                if not pd.api.types.is_numeric_dtype(df[col]):
                    try:
                        df[col] = pd.to_numeric(df[col], errors='coerce')
                    except:
                        return False, f"Column {col} is not numeric"
            
            # Verificar rangos básicos
            if (df['high'] < df['low']).any():
                return False, "Invalid OHLC data: High < Low"
            
            if (df['close'] <= 0).any():
                return False, "Invalid prices: Close <= 0"
                
            if (df['volume'] < 0).any():
                return False, "Invalid volume: Negative values"
            
            return True, "OK"
            
        except Exception as e:
            return False, f"Validation error: {str(e)}"
    
    def prepare_dataframe_for_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Preparar DataFrame para que funcione con TechnicalIndicators
        
        El CSV tiene columnas: Date,open,high,low,close,volume,Dividends,Stock Splits,symbol,timeframe,timestamp
        TechnicalIndicators espera: Open,High,Low,Close,Volume con índice de tiempo
        
        Args:
            df: DataFrame original del CSV
            
        Returns:
            DataFrame con formato compatible
        """
        # Crear copia
        data = df.copy()
        
        # Renombrar columnas al formato esperado por TechnicalIndicators
        column_mapping = {
            'open': 'Open',
            'high': 'High', 
            'low': 'Low',
            'close': 'Close',
            'volume': 'Volume'
        }
        
        data = data.rename(columns=column_mapping)
        
        # Usar Date como índice si está disponible, sino usar timestamp
        if 'Date' in data.columns:
            data['Date'] = pd.to_datetime(data['Date'])
            data.set_index('Date', inplace=True)
        elif 'timestamp' in data.columns:
            data['timestamp'] = pd.to_datetime(data['timestamp'])
            data.set_index('timestamp', inplace=True)
        
        # Ordenar por timestamp
        data.sort_index(inplace=True)
        
        return data
    
    def calculate_indicators_from_dataframe(self, df: pd.DataFrame, symbol: str) -> Optional[Dict]:
        """
        Calcular indicadores usando DataFrame preparado
        
        Args:
            df: DataFrame con datos OHLCV preparados
            symbol: Símbolo del activo
            
        Returns:
            Dict con indicadores o None si error
        """
        try:
            # Verificar que tenemos suficientes datos
            if len(df) < 30:
                logger.warning(f"⚠️ {symbol}: Datos insuficientes ({len(df)} filas)")
                return None
            
            logger.info(f"📊 Calculando indicadores para {symbol}...")
            
            # Calcular indicadores individuales usando los datos del CSV
            # En lugar de usar get_all_indicators que descarga de Yahoo,
            # calculamos cada indicador individualmente con nuestros datos
            
            indicators = {
                'symbol': symbol,
                'timestamp': datetime.now(),
                'current_price': float(df['Close'].iloc[-1]),
                'current_volume': int(df['Volume'].iloc[-1]),
                'data_points': len(df),
                
                # Calcular cada indicador individualmente
                'macd': self.indicators_calculator.calculate_macd(df),
                'rsi': self.indicators_calculator.calculate_rsi(df),
                'vwap': self.indicators_calculator.calculate_vwap(df),
                'roc': self.indicators_calculator.calculate_roc(df),
                'bollinger': self.indicators_calculator.calculate_bollinger_bands(df),
                'volume_osc': self.indicators_calculator.calculate_volume_oscillator(df),
                'atr': self.indicators_calculator.calculate_atr(df)
            }
            
            return indicators
            
        except Exception as e:
            logger.error(f"❌ Error calculando indicadores para {symbol}: {str(e)}")
            return None
    
    def _safe_calculate_indicator(self, calc_func, df: pd.DataFrame, indicator_name: str) -> Dict:
        """
        Calcular un indicador de forma segura con manejo de errores
        
        Args:
            calc_func: Función de cálculo del indicador
            df: DataFrame con datos
            indicator_name: Nombre del indicador para logging
            
        Returns:
            Dict con resultado del indicador o valores por defecto
        """
        try:
            result = calc_func(df)
            logger.debug(f"✅ {indicator_name}: calculado exitosamente")
            return result
        except Exception as e:
            logger.warning(f"⚠️ {indicator_name}: Error en cálculo - {e}")
            # Devolver valores por defecto según el indicador
            return self._get_default_indicator_values(indicator_name)
    
    def _get_default_indicator_values(self, indicator_name: str) -> Dict:
        """Obtener valores por defecto para indicadores que fallaron"""
        defaults = {
            'MACD': {'macd': 0, 'signal': 0, 'histogram': 0, 'signal_type': 'NEUTRAL', 'signal_strength': 0},
            'RSI': {'rsi': 50, 'signal_type': 'NEUTRAL', 'signal_strength': 0},
            'VWAP': {'vwap': 0, 'deviation_pct': 0, 'signal_type': 'NEUTRAL', 'signal_strength': 0},
            'ROC': {'roc': 0, 'signal_type': 'NEUTRAL', 'signal_strength': 0},
            'BB': {'upper_band': 0, 'middle_band': 0, 'lower_band': 0, 'bb_position': 0.5, 'signal_type': 'NEUTRAL', 'signal_strength': 0},
            'VOL': {'volume_oscillator': 0, 'signal_type': 'NEUTRAL', 'signal_strength': 0},
            'ATR': {'atr': 0, 'atr_percentage': 0, 'volatility_level': 'NORMAL'}
        }
        return defaults.get(indicator_name, {})
    
    def save_historical_indicators(self, indicators: Dict, original_df: pd.DataFrame) -> bool:
        """
        Guardar indicadores históricos en la base de datos
        
        Args:
            indicators: Dict con todos los indicadores calculados
            original_df: DataFrame original con datos por timestamp
            
        Returns:
            bool: True si se guardó exitosamente
        """
        try:
            # Para datos históricos, guardamos solo el último punto (más reciente)
            # que es como funciona el sistema en tiempo real
            
            # Usar la función existente del sistema
            success = save_indicators_data(indicators)
            
            if success:
                self.stats['rows_inserted'] += 1
                logger.info(f"✅ Guardado en database: {indicators['symbol']} @ {indicators['current_price']}")
            else:
                logger.error(f"❌ Error guardando en database: {indicators['symbol']}")
            
            return success
            
        except Exception as e:
            logger.error(f"❌ Error guardando indicadores históricos: {e}")
            return False
    
    def process_csv_file(self, filename: str, filepath: str) -> bool:
        """
        Procesar un archivo CSV individual
        
        Args:
            filename: Nombre del archivo
            filepath: Path completo al archivo
            
        Returns:
            bool: True si se procesó exitosamente
        """
        try:
            logger.info(f"📄 Procesando: {filename}")
            
            # Parsear información del filename
            file_info = self.parse_filename(filename)
            if not file_info:
                self.errors.append(f"{filename}: Invalid filename format")
                return False
            
            symbol = file_info['symbol']
            timeframe = file_info['timeframe']
            
            # Leer CSV
            try:
                df = pd.read_csv(filepath)
                self.stats['rows_processed'] += len(df)
            except Exception as e:
                self.errors.append(f"{filename}: Failed to read CSV - {e}")
                return False
            
            # Validar datos
            is_valid, validation_msg = self.validate_csv_data(df, symbol)
            if not is_valid:
                logger.error(f"❌ {symbol} {timeframe}: Validation failed - {validation_msg}")
                self.errors.append(f"{filename}: {validation_msg}")
                return False
            
            logger.info(f"✅ {symbol} {timeframe}: Validation passed - {len(df)} rows")
            
            # Preparar datos para indicadores
            prepared_df = self.prepare_dataframe_for_indicators(df)
            
            # Calcular indicadores
            indicators = self.calculate_indicators_from_dataframe(prepared_df, symbol)
            if not indicators:
                self.errors.append(f"{filename}: Failed to calculate indicators")
                return False
            
            # Guardar en base de datos
            if self.save_historical_indicators(indicators, df):
                logger.info(f"✅ {symbol} {timeframe}: Saved to database successfully")
                self.stats['symbols_processed'].add(symbol)
                self.stats['timeframes_processed'].add(timeframe)
                return True
            else:
                self.errors.append(f"{filename}: Failed to save to database")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error procesando {filename}: {str(e)}")
            self.errors.append(f"{filename}: {str(e)}")
            return False
    
    def run(self, data_dir: str = "raw_data", test_mode: bool = False, max_files: Optional[int] = None) -> Dict:
        """
        Ejecutar el proceso completo de población de datos
        
        Args:
            data_dir: Directorio con archivos CSV (relativo a historical_data/)
            test_mode: Si True, solo procesa el primer archivo
            max_files: Máximo número de archivos a procesar (None = todos)
            
        Returns:
            Dict con estadísticas del proceso
        """
        print("💾 DATABASE POPULATOR V4.0")
        print("=" * 50)
        logger.info("💾 Database Populator V4.0 inicializado")
        
        # Inicializar
        if not self.initialize():
            return self.get_final_stats()
        
        # Encontrar archivos CSV
        csv_files = self.find_csv_files(data_dir)
        if not csv_files:
            logger.warning(f"⚠️ No se encontraron archivos CSV en {data_dir}")
            return self.get_final_stats()
        
        logger.info(f"📁 Encontrados {len(csv_files)} archivos CSV")
        for i, (filename, _, size_kb) in enumerate(csv_files, 1):
            logger.info(f"   {i}. {filename} ({size_kb:.1f} KB)")
        
        # Aplicar filtros
        files_to_process = csv_files
        
        if test_mode:
            files_to_process = csv_files[:1]
            print("🧪 MODO TEST: Solo procesando primer archivo")
        elif max_files:
            files_to_process = csv_files[:max_files]
            print(f"📊 Procesando primeros {max_files} archivos")
        
        logger.info(f"🚀 Procesando {len(files_to_process)} archivos CSV...")
        
        # Procesar archivos
        for i, (filename, filepath, _) in enumerate(files_to_process, 1):
            try:
                progress_pct = (i / len(files_to_process)) * 100
                logger.info(f"\n📊 Progreso: {i}/{len(files_to_process)} ({progress_pct:.1f}%)")
                
                if self.process_csv_file(filename, filepath):
                    self.stats['files_completed'] += 1
                else:
                    self.stats['files_failed'] += 1
                    
            except KeyboardInterrupt:
                logger.info("🛑 Proceso interrumpido por usuario")
                break
            except Exception as e:
                logger.error(f"❌ Error inesperado procesando {filename}: {e}")
                self.stats['files_failed'] += 1
                continue
        
        return self.get_final_stats()
    
    def get_final_stats(self) -> Dict:
        """Obtener estadísticas finales del proceso"""
        elapsed_time = time.time() - self.stats['start_time']
        
        success_rate = 0
        if (self.stats['files_completed'] + self.stats['files_failed']) > 0:
            success_rate = (self.stats['files_completed'] / 
                          (self.stats['files_completed'] + self.stats['files_failed'])) * 100
        
        return {
            'files_completed': self.stats['files_completed'],
            'files_failed': self.stats['files_failed'],
            'files_skipped': self.stats['files_skipped'],
            'success_rate': success_rate,
            'elapsed_time': elapsed_time,
            'symbols_processed': list(self.stats['symbols_processed']),
            'timeframes_processed': list(self.stats['timeframes_processed']),
            'rows_processed': self.stats['rows_processed'],
            'rows_inserted': self.stats['rows_inserted'],
            'errors': self.errors
        }
    
    def print_final_report(self, stats: Dict):
        """Imprimir reporte final"""
        print("=" * 50)
        print("📊 RESULTADOS FINALES")
        print("=" * 50)
        print(f"✅ Archivos completados: {stats['files_completed']}")
        print(f"❌ Archivos fallidos: {stats['files_failed']}")
        print(f"⏭️ Archivos omitidos: {stats['files_skipped']}")
        print(f"📊 Tasa éxito: {stats['success_rate']:.1f}%")
        print(f"⏱️ Tiempo total: {stats['elapsed_time']:.1f}s")
        
        print(f"📈 ESTADÍSTICAS DE DATOS:")
        print(f"   Símbolos procesados: {len(stats['symbols_processed'])} ({', '.join(stats['symbols_processed'])})")
        print(f"   Timeframes procesados: {', '.join(stats['timeframes_processed'])}")
        print(f"   Filas procesadas: {stats['rows_processed']}")
        print(f"   Filas insertadas: {stats['rows_inserted']}")
        
        if stats['errors']:
            print(f"❌ ARCHIVOS CON ERRORES:")
            for error in stats['errors']:
                print(f"   {error}")
        
        if stats['files_completed'] == 0:
            print("⚠️ No se procesaron archivos exitosamente")
            print("💡 Revisa los errores y verifica los archivos CSV")
        else:
            print(f"🎉 ¡Proceso completado! {stats['rows_inserted']} registros guardados")

def main():
    """Función principal"""
    parser = argparse.ArgumentParser(description='Poblar base de datos con datos históricos')
    parser.add_argument('--data-dir', default='raw_data', help='Directorio con archivos CSV (relativo a historical_data/)')
    parser.add_argument('--test', action='store_true', help='Modo test: solo procesar primer archivo')
    parser.add_argument('--max-files', type=int, help='Máximo número de archivos a procesar')
    
    args = parser.parse_args()
    
    # Crear y ejecutar populator
    populator = HistoricalDataPopulator()
    
    try:
        stats = populator.run(
            data_dir=args.data_dir,
            test_mode=args.test,
            max_files=args.max_files
        )
        
        populator.print_final_report(stats)
        
    except KeyboardInterrupt:
        print("\n🛑 Proceso cancelado por usuario")
    except Exception as e:
        logger.error(f"❌ Error fatal: {e}")
        print(f"❌ Error fatal: {e}")

if __name__ == "__main__":
    main()