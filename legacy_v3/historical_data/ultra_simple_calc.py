#!/usr/bin/env python3
"""
📊 ULTRA SIMPLE INDICATOR CALCULATOR
====================================

Usa TA-Lib directamente sin la clase TechnicalIndicators
para evitar problemas de compatibilidad.
"""

import os
import sys
import pandas as pd
import numpy as np
import talib
import logging
from tqdm import tqdm

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

try:
    from database.connection import get_connection
    print("✅ Conexión a BD importada correctamente")
except ImportError as e:
    print(f"❌ Error importing modules: {e}")
    sys.exit(1)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_ohlcv_data(symbol: str) -> pd.DataFrame:
    """Obtener datos OHLCV de la BD"""
    try:
        conn = get_connection()
        query = """
            SELECT timestamp, open_price, high_price, low_price, close_price, volume
            FROM ohlcv_data 
            WHERE symbol = ? 
            ORDER BY timestamp ASC
            LIMIT 2000
        """
        
        df = pd.read_sql_query(query, conn, params=(symbol,))
        conn.close()
        
        if df.empty:
            return None
        
        # Renombrar columnas
        df.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
        
        # Parsear timestamps de forma simple
        df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
        df = df.dropna(subset=['timestamp']).reset_index(drop=True)
        
        logger.info(f"📊 {symbol}: {len(df)} registros cargados")
        return df
        
    except Exception as e:
        logger.error(f"❌ Error obteniendo datos para {symbol}: {e}")
        return None

def calculate_indicators_talib(df: pd.DataFrame, symbol: str) -> list:
    """Calcular indicadores usando TA-Lib directamente"""
    try:
        if len(df) < 100:
            logger.warning(f"⚠️ {symbol}: Datos insuficientes ({len(df)} registros)")
            return []
        
        # Preparar arrays para TA-Lib
        open_prices = df['open'].values.astype(float)
        high_prices = df['high'].values.astype(float)
        low_prices = df['low'].values.astype(float)
        close_prices = df['close'].values.astype(float)
        volumes = df['volume'].values.astype(float)
        
        # Calcular indicadores con TA-Lib
        logger.info(f"🔢 Calculando indicadores para {symbol}...")
        
        # RSI
        rsi_values = talib.RSI(close_prices, timeperiod=14)
        
        # MACD
        macd_line, macd_signal, macd_histogram = talib.MACD(close_prices, 
                                                            fastperiod=12, 
                                                            slowperiod=26, 
                                                            signalperiod=9)
        
        # Bollinger Bands
        bb_upper, bb_middle, bb_lower = talib.BBANDS(close_prices, 
                                                     timeperiod=20, 
                                                     nbdevup=2, 
                                                     nbdevdn=2)
        
        # ROC
        roc_values = talib.ROC(close_prices, timeperiod=10)
        
        # ATR
        atr_values = talib.ATR(high_prices, low_prices, close_prices, timeperiod=14)
        
        # VWAP manual (simple)
        typical_prices = (high_prices + low_prices + close_prices) / 3
        vwap_values = []
        volume_oscillator_values = []
        
        for i in range(len(df)):
            if i < 20:  # Necesitamos al menos 20 periodos
                vwap_values.append(np.nan)
                volume_oscillator_values.append(np.nan)
                continue
            
            # VWAP desde inicio del día (simplificado - últimos 20 periodos)
            start_idx = max(0, i-20)
            tp_slice = typical_prices[start_idx:i+1]
            vol_slice = volumes[start_idx:i+1]
            
            if np.sum(vol_slice) > 0:
                vwap = np.sum(tp_slice * vol_slice) / np.sum(vol_slice)
                vwap_values.append(vwap)
            else:
                vwap_values.append(typical_prices[i])
            
            # Volume Oscillator (simple)
            if i >= 25:  # Necesitamos 5+20 periodos
                vol_ma5 = np.mean(volumes[i-4:i+1])
                vol_ma20 = np.mean(volumes[i-19:i+1])
                if vol_ma20 > 0:
                    vol_osc = ((vol_ma5 - vol_ma20) / vol_ma20) * 100
                    volume_oscillator_values.append(vol_osc)
                else:
                    volume_oscillator_values.append(0)
            else:
                volume_oscillator_values.append(0)
        
        vwap_values = np.array(vwap_values)
        volume_oscillator_values = np.array(volume_oscillator_values)
        
        # Calcular VWAP deviation
        vwap_deviation = ((close_prices - vwap_values) / vwap_values) * 100
        
        # Calcular Bollinger Band position
        bb_position = (close_prices - bb_lower) / (bb_upper - bb_lower)
        
        # ATR percentage
        atr_percentage = (atr_values / close_prices) * 100
        
        # Crear registros (desde índice 50 para tener suficientes datos)
        records = []
        for i in range(50, len(df)):
            if (not np.isnan(rsi_values[i]) and 
                not np.isnan(macd_line[i]) and 
                not np.isnan(bb_upper[i]) and
                not np.isnan(vwap_values[i])):
                
                record = {
                    'symbol': symbol,
                    'timestamp': df.iloc[i]['timestamp'].isoformat(),
                    'rsi_value': float(rsi_values[i]) if not np.isnan(rsi_values[i]) else 0,
                    'macd_line': float(macd_line[i]) if not np.isnan(macd_line[i]) else 0,
                    'macd_signal': float(macd_signal[i]) if not np.isnan(macd_signal[i]) else 0,
                    'macd_histogram': float(macd_histogram[i]) if not np.isnan(macd_histogram[i]) else 0,
                    'vwap_value': float(vwap_values[i]) if not np.isnan(vwap_values[i]) else 0,
                    'vwap_deviation_pct': float(vwap_deviation[i]) if not np.isnan(vwap_deviation[i]) else 0,
                    'roc_value': float(roc_values[i]) if not np.isnan(roc_values[i]) else 0,
                    'bb_upper': float(bb_upper[i]) if not np.isnan(bb_upper[i]) else 0,
                    'bb_middle': float(bb_middle[i]) if not np.isnan(bb_middle[i]) else 0,
                    'bb_lower': float(bb_lower[i]) if not np.isnan(bb_lower[i]) else 0,
                    'bb_position': float(bb_position[i]) if not np.isnan(bb_position[i]) else 0.5,
                    'volume_oscillator': float(volume_oscillator_values[i]),
                    'atr_value': float(atr_values[i]) if not np.isnan(atr_values[i]) else 0,
                    'atr_percentage': float(atr_percentage[i]) if not np.isnan(atr_percentage[i]) else 0
                }
                records.append(record)
        
        logger.info(f"✅ {symbol}: {len(records)} indicadores calculados")
        return records
        
    except Exception as e:
        logger.error(f"❌ Error calculando indicadores para {symbol}: {e}")
        import traceback
        logger.error(f"🔍 Traceback: {traceback.format_exc()}")
        return []

def save_indicators(records: list) -> bool:
    """Guardar indicadores en la base de datos"""
    try:
        if not records:
            return False
        
        conn = get_connection()
        cursor = conn.cursor()
        
        insert_query = """
            INSERT OR REPLACE INTO indicators_data (
                symbol, timestamp, rsi_value, macd_line, macd_signal, macd_histogram,
                vwap_value, vwap_deviation_pct, roc_value, bb_upper, bb_middle, bb_lower,
                bb_position, volume_oscillator, atr_value, atr_percentage
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        
        data_tuples = []
        for record in records:
            data_tuples.append((
                record['symbol'], record['timestamp'], record['rsi_value'],
                record['macd_line'], record['macd_signal'], record['macd_histogram'],
                record['vwap_value'], record['vwap_deviation_pct'], record['roc_value'],
                record['bb_upper'], record['bb_middle'], record['bb_lower'],
                record['bb_position'], record['volume_oscillator'],
                record['atr_value'], record['atr_percentage']
            ))
        
        cursor.executemany(insert_query, data_tuples)
        conn.commit()
        conn.close()
        
        logger.info(f"💾 {len(records)} registros guardados en BD")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error guardando en BD: {e}")
        return False

def main():
    """Función principal"""
    symbols = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'NVDA', 'META']
    
    print("🚀 CALCULADORA ULTRA-SIMPLE DE INDICADORES")
    print("=" * 50)
    print("📊 Usando TA-Lib directamente")
    print(f"🎯 Símbolos: {len(symbols)}")
    print()
    
    successful = 0
    total_records = 0
    
    for symbol in tqdm(symbols, desc="Procesando símbolos"):
        # Obtener datos
        df = get_ohlcv_data(symbol)
        if df is None:
            logger.warning(f"❌ {symbol}: Sin datos")
            continue
        
        # Calcular indicadores
        records = calculate_indicators_talib(df, symbol)
        if not records:
            logger.warning(f"❌ {symbol}: Sin indicadores")
            continue
        
        # Guardar en BD
        if save_indicators(records):
            successful += 1
            total_records += len(records)
            logger.info(f"✅ {symbol}: Completado ({len(records)} registros)")
        else:
            logger.error(f"❌ {symbol}: Error guardando")
    
    print(f"\n📋 RESUMEN FINAL:")
    print(f"✅ Símbolos procesados: {successful}/{len(symbols)}")
    print(f"📊 Total registros: {total_records:,}")
    
    if successful > 0:
        print(f"\n🎉 ¡Indicadores calculados exitosamente!")
        print(f"💡 Ahora puedes ejecutar backtesting:")
        print(f"   python historical_data/backtest_engine.py --symbols AAPL MSFT")
    else:
        print(f"\n❌ No se procesaron símbolos exitosamente")

if __name__ == "__main__":
    main()