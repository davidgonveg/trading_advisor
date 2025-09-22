#!/usr/bin/env python3
"""
📊 HISTORICAL INDICATORS CALCULATOR V3.0
========================================

Calcula TODOS los indicadores técnicos para datos históricos descargados.
Puebla indicators_data con datos calculados para backtesting realista.

🎯 PROCESO:
1. Lee OHLCV histórico desde database
2. Aplica TechnicalIndicators a ventanas deslizantes  
3. Calcula RSI, MACD, VWAP, ROC, Bollinger, etc.
4. Guarda en indicators_data con timestamps correctos
5. Valida calidad de datos calculados

🚀 USO:
python historical_indicators_calc.py --symbols AAPL MSFT --months 3
python historical_indicators_calc.py --all-symbols --months 2 --validate
"""

import os
import sys
import pandas as pd
import numpy as np
import logging
import argparse
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import time
from tqdm import tqdm

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

try:
    import config
    from database.connection import get_connection
    from indicators import TechnicalIndicators
    print("✅ Módulos importados correctamente")
except ImportError as e:
    print(f"❌ Error importing modules: {e}")
    print("💡 Ejecuta desde la carpeta raíz del proyecto")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class HistoricalIndicatorsCalculator:
    """Calcula indicadores técnicos para datos históricos"""
    
    def __init__(self):
        self.technical_indicators = TechnicalIndicators()
        self.processed_count = 0
        self.error_count = 0
        self.validation_results = {}
        
    def get_available_symbols(self) -> List[str]:
        """Obtener símbolos disponibles en OHLCV data"""
        try:
            conn = get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT DISTINCT symbol 
                FROM ohlcv_data 
                ORDER BY symbol
            """)
            
            symbols = [row[0] for row in cursor.fetchall()]
            conn.close()
            
            logger.info(f"📊 Símbolos disponibles: {len(symbols)}")
            return symbols
            
        except Exception as e:
            logger.error(f"❌ Error obteniendo símbolos: {e}")
            return []
    
    def get_historical_ohlcv(self, symbol: str, months_back: int = 3) -> Optional[pd.DataFrame]:
        """
        Obtener datos OHLCV históricos para un símbolo
        
        Args:
            symbol: Símbolo a procesar (ej: AAPL)
            months_back: Meses hacia atrás para obtener datos
            
        Returns:
            DataFrame con OHLCV o None si no hay datos
        """
        try:
            conn = get_connection()
            
            # Primero verificar qué tablas existen
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]
            logger.info(f"📊 Tablas disponibles: {tables}")
            
            # Buscar tabla OHLCV (puede tener nombres diferentes)
            ohlcv_table = None
            if 'ohlcv_data' in tables:
                ohlcv_table = 'ohlcv_data'
            elif 'market_data' in tables:
                ohlcv_table = 'market_data'
            elif 'stock_data' in tables:
                ohlcv_table = 'stock_data'
            else:
                logger.error(f"❌ No se encontró tabla OHLCV. Tablas: {tables}")
                conn.close()
                return None
            
            # Verificar estructura de la tabla
            cursor.execute(f"PRAGMA table_info({ohlcv_table})")
            columns_info = cursor.fetchall()
            columns = [col[1] for col in columns_info]
            logger.info(f"📋 Columnas en {ohlcv_table}: {columns}")
            
            # Calcular fecha de inicio con timezone
            from datetime import timezone
            end_date = datetime.now(timezone.utc)
            start_date = end_date - timedelta(days=months_back * 30)
            
            # Query más flexible
            query = f"""
                SELECT timestamp, open_price, high_price, low_price, close_price, volume
                FROM {ohlcv_table} 
                WHERE symbol = ? 
                ORDER BY timestamp ASC
            """
            
            # Ejecutar query sin filtro de fecha primero para ver qué hay
            cursor.execute(f"SELECT COUNT(*) FROM {ohlcv_table} WHERE symbol = ?", (symbol,))
            total_records = cursor.fetchone()[0]
            logger.info(f"📊 Total registros para {symbol}: {total_records}")
            
            if total_records == 0:
                logger.warning(f"⚠️ No hay datos para {symbol} en {ohlcv_table}")
                conn.close()
                return None
            
            # Obtener algunos timestamps de muestra para diagnosticar formato
            cursor.execute(f"SELECT timestamp FROM {ohlcv_table} WHERE symbol = ? LIMIT 3", (symbol,))
            sample_timestamps = [row[0] for row in cursor.fetchall()]
            logger.info(f"📅 Timestamps de muestra: {sample_timestamps}")
            
            # Ejecutar query principal
            df = pd.read_sql_query(query, conn, params=(symbol,))
            conn.close()
            
            if df.empty:
                logger.warning(f"⚠️ Query devolvió datos vacíos para {symbol}")
                return None
            
            # Renombrar columnas para compatibilidad con indicators
            df.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
            
            # Manejo robusto de timestamps
            logger.info(f"🕐 Procesando timestamps para {symbol}...")
            try:
                # Intentar varios métodos de parseo
                if df['timestamp'].dtype == 'object':
                    # Si son strings, intentar parsear
                    try:
                        df['timestamp'] = pd.to_datetime(df['timestamp'], format='ISO8601')
                    except:
                        try:
                            df['timestamp'] = pd.to_datetime(df['timestamp'], infer_datetime_format=True)
                        except:
                            # Fallback más agresivo
                            df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
                else:
                    # Si ya son datetime, convertir a timestamp
                    df['timestamp'] = pd.to_datetime(df['timestamp'])
                
                # Eliminar registros con timestamps inválidos
                df = df.dropna(subset=['timestamp'])
                
                if df.empty:
                    logger.error(f"❌ Todos los timestamps son inválidos para {symbol}")
                    return None
                
            except Exception as ts_error:
                logger.error(f"❌ Error procesando timestamps para {symbol}: {ts_error}")
                return None
            
            # Filtrar por fecha después del parseo - convertir fechas para comparación
            try:
                # Asegurar que ambas fechas tengan el mismo timezone handling
                if hasattr(df['timestamp'].iloc[0], 'tz'):
                    # Si los datos tienen timezone, convertir start/end dates
                    if start_date.tzinfo is None:
                        start_date = start_date.replace(tzinfo=timezone.utc)
                    if end_date.tzinfo is None:
                        end_date = end_date.replace(tzinfo=timezone.utc)
                else:
                    # Si los datos no tienen timezone, quitar timezone de start/end dates
                    start_date = start_date.replace(tzinfo=None)
                    end_date = end_date.replace(tzinfo=None)
                
                df = df[df['timestamp'] >= start_date]
                df = df[df['timestamp'] <= end_date]
                
            except Exception as filter_error:
                logger.warning(f"⚠️ Error filtrando fechas para {symbol}: {filter_error}")
                # Si hay error, usar todos los datos disponibles
                logger.info(f"💡 Usando todos los datos disponibles para {symbol}")
            
            if df.empty:
                logger.warning(f"⚠️ No hay datos en el rango de fechas para {symbol}")
                return None
            
            # Set index y ordenar
            df = df.set_index('timestamp').sort_index()
            
            logger.info(f"📈 {symbol}: {len(df)} registros desde {df.index[0].date()} hasta {df.index[-1].date()}")
            return df
            
        except Exception as e:
            logger.error(f"❌ Error obteniendo OHLCV para {symbol}: {e}")
            import traceback
            logger.error(f"🔍 Traceback: {traceback.format_exc()}")
            return None
    
    def calculate_indicators_for_symbol(self, symbol: str, months_back: int = 3) -> bool:
        """
        Calcular todos los indicadores para un símbolo específico
        
        Args:
            symbol: Símbolo a procesar
            months_back: Meses de datos históricos
            
        Returns:
            True si se procesó exitosamente
        """
        try:
            logger.info(f"🔄 Procesando {symbol}...")
            
            # 1. Obtener datos OHLCV históricos
            df = self.get_historical_ohlcv(symbol, months_back)
            if df is None or len(df) < 50:  # Mínimo 50 periodos para indicadores
                logger.warning(f"⚠️ {symbol}: Datos insuficientes para cálculos")
                return False
            
            # 2. Calcular indicadores usando TechnicalIndicators
            indicators_data = []
            
            # Necesitamos ventana mínima para indicadores (ej: MACD necesita ~26 periodos)
            min_window = 50
            
            for i in range(min_window, len(df)):
                # Obtener ventana de datos hasta el punto actual
                window_data = df.iloc[:i+1].copy()
                
                try:
                    # Calcular todos los indicadores para este timestamp
                    current_timestamp = df.index[i]
                    current_close = df.iloc[i]['close']
                    current_volume = df.iloc[i]['volume']
                    
                    # IMPORTANTE: Convertir columnas a formato esperado por TechnicalIndicators
                    window_data_formatted = window_data.copy()
                    window_data_formatted.columns = ['Open', 'High', 'Low', 'Close', 'Volume']
                    
                    # RSI
                    rsi_value = self.technical_indicators.calculate_rsi(window_data['close'])
                    
                    # MACD
                    macd_line, macd_signal, macd_histogram = self.technical_indicators.calculate_macd(window_data['close'])
                    
                    # VWAP y desviación
                    vwap_value, vwap_deviation = self.technical_indicators.calculate_vwap_deviation(window_data)
                    
                    # Rate of Change
                    roc_value = self.technical_indicators.calculate_roc(window_data['close'])
                    
                    # Bollinger Bands
                    bb_upper, bb_middle, bb_lower = self.technical_indicators.calculate_bollinger_bands(window_data['close'])
                    bb_position = self.technical_indicators.calculate_bb_position(current_close, bb_upper, bb_middle, bb_lower)
                    
                    # Volume Oscillator
                    volume_osc = self.technical_indicators.calculate_volume_oscillator(window_data['volume'])
                    
                    # ATR
                    atr_value, atr_percentage = self.technical_indicators.calculate_atr(window_data)
                    
                    # Crear registro de indicadores
                    indicator_record = {
                        'symbol': symbol,
                        'timestamp': current_timestamp.isoformat(),
                        'rsi_value': rsi_value,
                        'macd_line': macd_line,
                        'macd_signal': macd_signal,
                        'macd_histogram': macd_histogram,
                        'vwap_value': vwap_value,
                        'vwap_deviation_pct': vwap_deviation,
                        'roc_value': roc_value,
                        'bb_upper': bb_upper,
                        'bb_middle': bb_middle,
                        'bb_lower': bb_lower,
                        'bb_position': bb_position,
                        'volume_oscillator': volume_osc,
                        'atr_value': atr_value,
                        'atr_percentage': atr_percentage
                    }
                    
                    indicators_data.append(indicator_record)
                    
                except Exception as e:
                    logger.warning(f"⚠️ Error calculando indicadores para {symbol} en {current_timestamp}: {e}")
                    continue
            
            # 3. Guardar en base de datos
            if indicators_data:
                success = self.save_indicators_to_db(indicators_data)
                if success:
                    logger.info(f"✅ {symbol}: {len(indicators_data)} registros guardados")
                    self.processed_count += len(indicators_data)
                    return True
                else:
                    logger.error(f"❌ {symbol}: Error guardando en BD")
                    self.error_count += 1
                    return False
            else:
                logger.warning(f"⚠️ {symbol}: No se generaron indicadores válidos")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error procesando {symbol}: {e}")
            self.error_count += 1
            return False
    
    def save_indicators_to_db(self, indicators_data: List[Dict]) -> bool:
        """Guardar indicadores calculados en la base de datos"""
        try:
            conn = get_connection()
            cursor = conn.cursor()
            
            # Usar INSERT OR REPLACE para evitar duplicados
            insert_query = """
                INSERT OR REPLACE INTO indicators_data (
                    symbol, timestamp, rsi_value, macd_line, macd_signal, macd_histogram,
                    vwap_value, vwap_deviation_pct, roc_value, bb_upper, bb_middle, bb_lower,
                    bb_position, volume_oscillator, atr_value, atr_percentage
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            
            # Preparar datos para inserción
            records_to_insert = []
            for record in indicators_data:
                records_to_insert.append((
                    record['symbol'],
                    record['timestamp'],
                    record['rsi_value'],
                    record['macd_line'],
                    record['macd_signal'],
                    record['macd_histogram'],
                    record['vwap_value'],
                    record['vwap_deviation_pct'],
                    record['roc_value'],
                    record['bb_upper'],
                    record['bb_middle'],
                    record['bb_lower'],
                    record['bb_position'],
                    record['volume_oscillator'],
                    record['atr_value'],
                    record['atr_percentage']
                ))
            
            # Insertar en lotes para mejor rendimiento
            cursor.executemany(insert_query, records_to_insert)
            conn.commit()
            conn.close()
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error guardando en BD: {e}")
            return False
    
    def validate_calculated_indicators(self, symbol: str) -> Dict:
        """Validar calidad de indicadores calculados"""
        try:
            conn = get_connection()
            cursor = conn.cursor()
            
            # Obtener estadísticas de indicadores para el símbolo
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_records,
                    COUNT(rsi_value) as rsi_count,
                    COUNT(macd_line) as macd_count,
                    COUNT(vwap_value) as vwap_count,
                    COUNT(bb_upper) as bb_count,
                    AVG(rsi_value) as avg_rsi,
                    MIN(rsi_value) as min_rsi,
                    MAX(rsi_value) as max_rsi
                FROM indicators_data 
                WHERE symbol = ?
            """, (symbol,))
            
            stats = cursor.fetchone()
            conn.close()
            
            if stats[0] == 0:  # total_records
                return {'status': 'NO_DATA', 'details': 'No hay datos de indicadores'}
            
            # Calcular métricas de calidad
            total_records = stats[0]
            completeness = {
                'rsi': (stats[1] / total_records) * 100,
                'macd': (stats[2] / total_records) * 100,
                'vwap': (stats[3] / total_records) * 100,
                'bb': (stats[4] / total_records) * 100
            }
            
            # Validar rangos de RSI (debe estar entre 0-100)
            rsi_valid = 0 <= stats[5] <= 100 if stats[5] else False
            rsi_range_valid = 0 <= stats[6] <= 100 and 0 <= stats[7] <= 100
            
            # Calcular score de calidad
            avg_completeness = sum(completeness.values()) / len(completeness)
            quality_score = avg_completeness if rsi_valid and rsi_range_valid else avg_completeness * 0.5
            
            validation_result = {
                'status': 'VALID' if quality_score > 90 else 'PARTIAL' if quality_score > 70 else 'POOR',
                'quality_score': quality_score,
                'total_records': total_records,
                'completeness': completeness,
                'rsi_stats': {
                    'avg': stats[5],
                    'min': stats[6],
                    'max': stats[7],
                    'range_valid': rsi_range_valid
                }
            }
            
            self.validation_results[symbol] = validation_result
            return validation_result
            
        except Exception as e:
            logger.error(f"❌ Error validando {symbol}: {e}")
            return {'status': 'ERROR', 'details': str(e)}
    
    def process_symbols(self, symbols: List[str], months_back: int = 3, validate: bool = True) -> Dict:
        """
        Procesar múltiples símbolos
        
        Args:
            symbols: Lista de símbolos a procesar
            months_back: Meses de datos históricos
            validate: Si validar resultados
            
        Returns:
            Resumen de procesamiento
        """
        logger.info(f"🚀 Iniciando procesamiento de {len(symbols)} símbolos")
        logger.info(f"📅 Periodo: {months_back} meses hacia atrás")
        
        start_time = time.time()
        successful_symbols = []
        failed_symbols = []
        
        # Procesar cada símbolo con barra de progreso
        for symbol in tqdm(symbols, desc="Procesando símbolos"):
            success = self.calculate_indicators_for_symbol(symbol, months_back)
            
            if success:
                successful_symbols.append(symbol)
                
                # Validar si se solicita
                if validate:
                    validation = self.validate_calculated_indicators(symbol)
                    logger.info(f"📊 {symbol} validación: {validation['status']} ({validation.get('quality_score', 0):.1f}%)")
            else:
                failed_symbols.append(symbol)
        
        processing_time = time.time() - start_time
        
        # Resumen final
        summary = {
            'total_symbols': len(symbols),
            'successful': len(successful_symbols),
            'failed': len(failed_symbols),
            'processing_time_seconds': processing_time,
            'records_processed': self.processed_count,
            'errors': self.error_count,
            'successful_symbols': successful_symbols,
            'failed_symbols': failed_symbols,
            'validation_results': self.validation_results if validate else {}
        }
        
        return summary


def main():
    parser = argparse.ArgumentParser(description='Calcular indicadores técnicos históricos')
    parser.add_argument('--symbols', nargs='+', help='Símbolos específicos (ej: AAPL MSFT)')
    parser.add_argument('--all-symbols', action='store_true', help='Procesar todos los símbolos disponibles')
    parser.add_argument('--months', type=int, default=3, help='Meses de datos históricos (default: 3)')
    parser.add_argument('--validate', action='store_true', help='Validar calidad de indicadores calculados')
    parser.add_argument('--max-symbols', type=int, help='Limitar número de símbolos a procesar')
    
    args = parser.parse_args()
    
    # Crear calculadora
    calculator = HistoricalIndicatorsCalculator()
    
    # Determinar símbolos a procesar
    if args.all_symbols:
        symbols = calculator.get_available_symbols()
        if args.max_symbols:
            symbols = symbols[:args.max_symbols]
        logger.info(f"📊 Procesando todos los símbolos disponibles: {len(symbols)}")
    elif args.symbols:
        symbols = args.symbols
        logger.info(f"📊 Procesando símbolos específicos: {symbols}")
    else:
        # Default: algunos símbolos principales
        symbols = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA']
        logger.info(f"📊 Procesando símbolos por defecto: {symbols}")
    
    if not symbols:
        logger.error("❌ No hay símbolos para procesar")
        return 1
    
    # Procesar símbolos
    print(f"\n🚀 CALCULANDO INDICADORES HISTÓRICOS")
    print(f"📅 Periodo: {args.months} meses")
    print(f"📊 Símbolos: {len(symbols)}")
    print(f"🔍 Validación: {'Sí' if args.validate else 'No'}")
    print("=" * 50)
    
    summary = calculator.process_symbols(
        symbols=symbols,
        months_back=args.months,
        validate=args.validate
    )
    
    # Mostrar resumen final
    print(f"\n📋 RESUMEN DE PROCESAMIENTO")
    print("=" * 50)
    print(f"✅ Símbolos exitosos: {summary['successful']}/{summary['total_symbols']}")
    print(f"❌ Símbolos fallidos: {summary['failed']}")
    print(f"📊 Registros procesados: {summary['records_processed']:,}")
    print(f"⏱️ Tiempo total: {summary['processing_time_seconds']:.1f}s")
    
    if summary['failed_symbols']:
        print(f"\n❌ SÍMBOLOS FALLIDOS:")
        for symbol in summary['failed_symbols']:
            print(f"   • {symbol}")
    
    if args.validate and summary['validation_results']:
        print(f"\n🔍 VALIDACIÓN DE CALIDAD:")
        for symbol, validation in summary['validation_results'].items():
            status_emoji = "✅" if validation['status'] == 'VALID' else "⚠️" if validation['status'] == 'PARTIAL' else "❌"
            print(f"   {status_emoji} {symbol}: {validation['status']} ({validation.get('quality_score', 0):.1f}%)")
    
    print(f"\n💡 PRÓXIMOS PASOS:")
    if summary['successful'] > 0:
        print(f"   ✅ Datos de indicadores listos para backtesting")
        print(f"   🧪 Ejecuta: python historical_data/backtest_engine.py --symbols {' '.join(summary['successful_symbols'][:3])}")
        print(f"   📊 Valida datos: python historical_data/backtest_engine.py --validation")
    else:
        print(f"   ❌ Ningún símbolo procesado exitosamente")
        print(f"   💡 Verifica que existan datos OHLCV en la base de datos")
        print(f"   📥 Ejecuta primero: python historical_data/downloader.py")
    
    return 0 if summary['successful'] > 0 else 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)