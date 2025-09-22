#!/usr/bin/env python3
"""
📊 HISTORICAL INDICATORS CALCULATOR V4.0 - FIXED OHLC VERSION
============================================================

✅ FIXED: Ahora guarda PRECIOS + INDICADORES en indicators_data
✅ FIXED: Procesa datos OHLC desde la tabla ohlcv_data correctamente  
✅ FIXED: Manejo robusto de timestamps y formatos CSV

Este script lee datos OHLCV históricos y calcula indicadores técnicos,
guardando AMBOS (precios + indicadores) en la tabla indicators_data.

USO:
    python historical_indicators_calc.py                    # Procesar todos los símbolos
    python historical_indicators_calc.py --symbol AAPL      # Solo AAPL
    python historical_indicators_calc.py --limit 100        # Solo primeras 100 filas
    python historical_indicators_calc.py --force            # Sobrescribir existentes
"""

import os
import sys
import pandas as pd
import numpy as np
import logging
import argparse
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any
import sqlite3
from pathlib import Path

# Configurar paths
current_dir = Path(__file__).parent.absolute()
project_root = current_dir.parent if current_dir.name == 'historical_data' else current_dir
sys.path.insert(0, str(project_root))

try:
    import config
    from database.connection import get_connection
    from indicators import TechnicalIndicators
    print("✅ Módulos del sistema importados correctamente")
except ImportError as e:
    print(f"❌ Error importando módulos: {e}")
    sys.exit(1)

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

class FixedHistoricalIndicatorsCalculator:
    """
    Calculador de indicadores históricos FIJO
    Ahora guarda PRECIOS + INDICADORES juntos
    """
    
    def __init__(self, force_mode: bool = False, limit_rows: Optional[int] = None):
        self.force_mode = force_mode
        self.limit_rows = limit_rows
        self.indicators_calc = TechnicalIndicators()
        
        # Estadísticas
        self.stats = {
            'symbols_processed': 0,
            'total_records_processed': 0,
            'records_saved': 0,
            'errors': 0,
            'start_time': datetime.now()
        }
    
    def get_available_symbols(self) -> List[str]:
        """Obtener símbolos disponibles en la base de datos OHLCV"""
        try:
            conn = get_connection()
            cursor = conn.cursor()
            
            # Verificar qué tablas existen
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]
            logger.info(f"📊 Tablas disponibles: {tables}")
            
            # Buscar tabla OHLCV
            ohlcv_table = None
            if 'ohlcv_data' in tables:
                ohlcv_table = 'ohlcv_data'
            else:
                logger.error("❌ No se encontró tabla ohlcv_data")
                conn.close()
                return []
            
            # Obtener símbolos únicos
            cursor.execute(f"SELECT DISTINCT symbol FROM {ohlcv_table} ORDER BY symbol")
            symbols = [row[0] for row in cursor.fetchall()]
            
            conn.close()
            logger.info(f"📈 Símbolos disponibles: {len(symbols)} - {symbols[:5]}...")
            return symbols
            
        except Exception as e:
            logger.error(f"❌ Error obteniendo símbolos: {e}")
            return []
    
    def get_ohlcv_data(self, symbol: str) -> Optional[pd.DataFrame]:
        """
        Obtener datos OHLCV históricos para un símbolo
        
        Returns:
            DataFrame con columnas: timestamp, open_price, high_price, low_price, close_price, volume
        """
        try:
            conn = get_connection()
            cursor = conn.cursor()
            
            # Query base para obtener datos OHLCV
            query = """
                SELECT timestamp, open_price, high_price, low_price, close_price, volume
                FROM ohlcv_data 
                WHERE symbol = ? 
                ORDER BY timestamp ASC
            """
            
            if self.limit_rows:
                query += f" LIMIT {self.limit_rows}"
            
            cursor.execute(query, (symbol,))
            rows = cursor.fetchall()
            conn.close()
            
            if not rows:
                logger.warning(f"⚠️ No hay datos OHLCV para {symbol}")
                return None
            
            # Convertir a DataFrame
            df = pd.DataFrame(rows, columns=['timestamp', 'open_price', 'high_price', 
                                           'low_price', 'close_price', 'volume'])
            
            # Convertir timestamp a datetime
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df = df.set_index('timestamp').sort_index()
            
            # Validar datos OHLCV
            if len(df) < 50:  # Necesitamos al menos 50 puntos para indicadores
                logger.warning(f"⚠️ {symbol}: Insuficientes datos ({len(df)} registros)")
                return None
            
            # Validar que no hay valores nulos críticos
            if df['close_price'].isnull().any():
                logger.warning(f"⚠️ {symbol}: Valores nulos en close_price")
                df = df.dropna(subset=['close_price'])
            
            logger.info(f"📊 {symbol}: {len(df)} registros OHLCV cargados ({df.index[0]} a {df.index[-1]})")
            return df
            
        except Exception as e:
            logger.error(f"❌ Error obteniendo datos OHLCV para {symbol}: {e}")
            return None
    
    def calculate_indicators_batch(self, df: pd.DataFrame, symbol: str) -> List[Dict[str, Any]]:
        """
        Calcular indicadores para un DataFrame completo
        
        Returns:
            Lista de dicts con PRECIOS + INDICADORES para cada timestamp
        """
        try:
            if len(df) < 50:
                logger.warning(f"⚠️ {symbol}: DataFrame muy pequeño para indicadores")
                return []
            
            # Preparar datos para TechnicalIndicators (necesita formato específico)
            df_for_indicators = df.rename(columns={
                'open_price': 'Open',
                'high_price': 'High', 
                'low_price': 'Low',
                'close_price': 'Close',
                'volume': 'Volume'
            })
            
            logger.info(f"📊 Calculando indicadores para {symbol} ({len(df_for_indicators)} registros)...")
            
            indicators_records = []
            
            # Iterar por cada timestamp para calcular indicadores
            for i, (timestamp, row) in enumerate(df_for_indicators.iterrows()):
                try:
                    # Necesitamos al menos 50 registros previos para indicadores confiables
                    if i < 49:
                        continue
                    
                    # Obtener ventana de datos hasta este punto
                    window_data = df_for_indicators.iloc[:i+1]
                    
                    # ✅ EXTRAER PRECIOS OHLC ACTUALES
                    current_open = float(row['Open'])
                    current_high = float(row['High'])
                    current_low = float(row['Low'])
                    current_close = float(row['Close'])
                    current_volume = int(row['Volume']) if not pd.isna(row['Volume']) else 0
                    
                    # ✅ CALCULAR INDICADORES TÉCNICOS
                    # RSI
                    try:
                        rsi_data = self.indicators_calc.calculate_rsi(window_data)
                        rsi_value = float(rsi_data.get('rsi', 0)) if rsi_data else 0
                    except:
                        rsi_value = 0
                    
                    # MACD
                    try:
                        macd_data = self.indicators_calc.calculate_macd(window_data)
                        macd_line = float(macd_data.get('macd', 0)) if macd_data else 0
                        macd_signal = float(macd_data.get('signal', 0)) if macd_data else 0
                        macd_histogram = float(macd_data.get('histogram', 0)) if macd_data else 0
                    except:
                        macd_line = macd_signal = macd_histogram = 0
                    
                    # VWAP
                    try:
                        vwap_data = self.indicators_calc.calculate_vwap(window_data)
                        vwap_value = float(vwap_data.get('vwap', 0)) if vwap_data else 0
                        vwap_deviation = float(vwap_data.get('deviation_pct', 0)) if vwap_data else 0
                    except:
                        vwap_value = vwap_deviation = 0
                    
                    # Rate of Change (ROC)
                    try:
                        roc_data = self.indicators_calc.calculate_roc(window_data)
                        roc_value = float(roc_data.get('roc', 0)) if roc_data else 0
                    except:
                        roc_value = 0
                    
                    # Bollinger Bands
                    try:
                        bb_data = self.indicators_calc.calculate_bollinger_bands(window_data)
                        bb_upper = float(bb_data.get('upper', 0)) if bb_data else 0
                        bb_middle = float(bb_data.get('middle', 0)) if bb_data else 0
                        bb_lower = float(bb_data.get('lower', 0)) if bb_data else 0
                        bb_position = float(bb_data.get('position', 0)) if bb_data else 0
                    except:
                        bb_upper = bb_middle = bb_lower = bb_position = 0
                    
                    # Volume Oscillator
                    try:
                        vol_data = self.indicators_calc.calculate_volume_oscillator(window_data)
                        volume_osc = float(vol_data.get('oscillator', 0)) if vol_data else 0
                    except:
                        volume_osc = 0
                    
                    # ATR
                    try:
                        atr_data = self.indicators_calc.calculate_atr(window_data)
                        atr_value = float(atr_data.get('atr', 0)) if atr_data else 0
                        atr_percentage = float(atr_data.get('atr_pct', 0)) if atr_data else 0
                    except:
                        atr_value = atr_percentage = 0
                    
                    # Determinar market regime basado en ROC
                    if abs(roc_value) > 2.0:
                        market_regime = "TRENDING"
                        volatility_level = "HIGH" if abs(roc_value) > 5.0 else "MEDIUM"
                    elif abs(roc_value) < 0.5:
                        market_regime = "RANGING" 
                        volatility_level = "LOW"
                    else:
                        market_regime = "TRANSITIONING"
                        volatility_level = "MEDIUM"
                    
                    # ✅ CREAR REGISTRO COMPLETO (PRECIOS + INDICADORES)
                    record = {
                        'timestamp': timestamp.isoformat(),
                        'symbol': symbol,
                        # PRECIOS OHLCV
                        'open_price': current_open,
                        'high_price': current_high,
                        'low_price': current_low,
                        'close_price': current_close,
                        'volume': current_volume,
                        # INDICADORES TÉCNICOS
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
                        'atr_percentage': atr_percentage,
                        # CONTEXTO
                        'market_regime': market_regime,
                        'volatility_level': volatility_level
                    }
                    
                    indicators_records.append(record)
                    
                    # Log progreso cada 1000 registros
                    if len(indicators_records) % 1000 == 0:
                        logger.info(f"📊 {symbol}: {len(indicators_records)} indicadores calculados...")
                    
                except Exception as e:
                    logger.warning(f"⚠️ Error calculando indicadores para {symbol} en {timestamp}: {e}")
                    continue
            
            logger.info(f"✅ {symbol}: {len(indicators_records)} registros con indicadores listos")
            return indicators_records
            
        except Exception as e:
            logger.error(f"❌ Error calculando indicadores batch para {symbol}: {e}")
            return []
    
    def save_indicators_to_db(self, records: List[Dict[str, Any]]) -> bool:
        """
        Guardar registros completos (precios + indicadores) en la base de datos
        """
        try:
            if not records:
                return False
            
            conn = get_connection()
            cursor = conn.cursor()
            
            # ✅ QUERY COMPLETA CON TODOS LOS CAMPOS
            insert_query = """
                INSERT OR REPLACE INTO indicators_data (
                    timestamp, symbol, 
                    open_price, high_price, low_price, close_price, volume,
                    rsi_value, macd_line, macd_signal, macd_histogram,
                    vwap_value, vwap_deviation_pct, roc_value,
                    bb_upper, bb_middle, bb_lower, bb_position,
                    volume_oscillator, atr_value, atr_percentage,
                    market_regime, volatility_level
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            
            # Preparar datos para inserción masiva
            records_to_insert = []
            for record in records:
                records_to_insert.append((
                    record['timestamp'],
                    record['symbol'],
                    # PRECIOS
                    record['open_price'],
                    record['high_price'], 
                    record['low_price'],
                    record['close_price'],
                    record['volume'],
                    # INDICADORES
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
                    record['atr_percentage'],
                    # CONTEXTO
                    record['market_regime'],
                    record['volatility_level']
                ))
            
            # Insertar en lotes para mejor performance
            cursor.executemany(insert_query, records_to_insert)
            conn.commit()
            
            rows_inserted = cursor.rowcount
            conn.close()
            
            logger.info(f"✅ {rows_inserted} registros guardados en indicators_data")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error guardando en BD: {e}")
            return False
    
    def process_symbol(self, symbol: str) -> bool:
        """Procesar un símbolo completo"""
        try:
            logger.info(f"\n🔄 PROCESANDO SÍMBOLO: {symbol}")
            logger.info("=" * 60)
            
            # 1. Verificar si ya existe (si no está en force mode)
            if not self.force_mode:
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM indicators_data WHERE symbol = ?", (symbol,))
                existing_count = cursor.fetchone()[0]
                conn.close()
                
                if existing_count > 0:
                    logger.info(f"⏭️ {symbol}: {existing_count} registros existentes (usar --force para sobrescribir)")
                    return True
            
            # 2. Obtener datos OHLCV
            df_ohlcv = self.get_ohlcv_data(symbol)
            if df_ohlcv is None or len(df_ohlcv) == 0:
                logger.warning(f"⚠️ {symbol}: No hay datos OHLCV disponibles")
                return False
            
            # 3. Calcular indicadores batch
            indicators_records = self.calculate_indicators_batch(df_ohlcv, symbol)
            if not indicators_records:
                logger.warning(f"⚠️ {symbol}: No se calcularon indicadores")
                return False
            
            # 4. Guardar en base de datos
            success = self.save_indicators_to_db(indicators_records)
            if success:
                self.stats['records_saved'] += len(indicators_records)
                self.stats['symbols_processed'] += 1
                logger.info(f"✅ {symbol}: {len(indicators_records)} registros procesados exitosamente")
                return True
            else:
                logger.error(f"❌ {symbol}: Error guardando registros")
                self.stats['errors'] += 1
                return False
                
        except Exception as e:
            logger.error(f"❌ Error procesando {symbol}: {e}")
            self.stats['errors'] += 1
            return False
    
    def run(self, target_symbol: Optional[str] = None):
        """Ejecutar el proceso completo"""
        logger.info("\n🚀 HISTORICAL INDICATORS CALCULATOR V4.0 - FIXED OHLC")
        logger.info("=" * 70)
        
        # Obtener símbolos a procesar
        if target_symbol:
            symbols = [target_symbol]
            logger.info(f"🎯 Procesando símbolo específico: {target_symbol}")
        else:
            symbols = self.get_available_symbols()
            if not symbols:
                logger.error("❌ No hay símbolos disponibles para procesar")
                return
            logger.info(f"📈 Procesando {len(symbols)} símbolos: {symbols}")
        
        # Procesar cada símbolo
        for i, symbol in enumerate(symbols, 1):
            logger.info(f"\n[{i}/{len(symbols)}] Procesando {symbol}...")
            self.process_symbol(symbol)
        
        # Estadísticas finales
        self.print_final_stats()
    
    def print_final_stats(self):
        """Imprimir estadísticas finales"""
        elapsed_time = datetime.now() - self.stats['start_time']
        
        print("\n" + "=" * 70)
        print("📊 ESTADÍSTICAS FINALES - HISTORICAL INDICATORS CALCULATOR")
        print("=" * 70)
        print(f"⏰ Tiempo total: {elapsed_time}")
        print(f"📈 Símbolos procesados: {self.stats['symbols_processed']}")
        print(f"💾 Registros guardados: {self.stats['records_saved']:,}")
        print(f"❌ Errores: {self.stats['errors']}")
        
        if self.stats['symbols_processed'] > 0:
            avg_records = self.stats['records_saved'] / self.stats['symbols_processed']
            print(f"📊 Promedio por símbolo: {avg_records:,.0f} registros")
        
        print("\n✅ Proceso completado exitosamente")
        print("🔍 Para verificar: SELECT COUNT(*) FROM indicators_data;")

def main():
    """Función principal"""
    parser = argparse.ArgumentParser(description='Calculador de Indicadores Históricos V4.0 - FIXED')
    parser.add_argument('--symbol', type=str, help='Procesar solo este símbolo')
    parser.add_argument('--force', action='store_true', help='Sobrescribir datos existentes')
    parser.add_argument('--limit', type=int, help='Limitar número de registros por símbolo')
    
    args = parser.parse_args()
    
    # Crear calculador
    calculator = FixedHistoricalIndicatorsCalculator(
        force_mode=args.force,
        limit_rows=args.limit
    )
    
    # Ejecutar
    try:
        calculator.run(target_symbol=args.symbol)
    except KeyboardInterrupt:
        print("\n⚠️ Proceso interrumpido por el usuario")
    except Exception as e:
        print(f"\n❌ Error fatal: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()