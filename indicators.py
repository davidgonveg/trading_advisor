#!/usr/bin/env python3
"""
📊 SISTEMA DE INDICADORES TÉCNICOS - TRADING AUTOMATIZADO V2.0
============================================================

Este módulo contiene todos los indicadores técnicos utilizados para
detectar señales de trading de alta calidad.

Indicadores implementados:
- MACD (Moving Average Convergence Divergence)
- RSI (Relative Strength Index)
- VWAP (Volume Weighted Average Price)
- ROC (Rate of Change / Momentum)
- Bollinger Bands
- Oscilador de Volumen
- ATR (Average True Range)
"""

import pandas as pd
import numpy as np
import yfinance as yf
import talib
import logging
from typing import Dict, Tuple, Optional, Union
from datetime import datetime, timedelta
import warnings

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Suprimir warnings de yfinance
warnings.filterwarnings('ignore', category=FutureWarning)

class TechnicalIndicators:
    """
    Clase principal para calcular todos los indicadores técnicos
    """
    
    def __init__(self):
        """Inicializar la clase de indicadores"""
        self.last_update = {}  # Cache para evitar recálculos innecesarios
        
    def get_market_data(self, symbol: str, period: str = "15m", days: int = 30) -> pd.DataFrame:
        """
        Descargar datos de mercado desde Yahoo Finance
        
        Args:
            symbol: Símbolo a descargar (ej: "AAPL")
            period: Timeframe (1m, 5m, 15m, 30m, 1h, 1d)
            days: Días de historial a descargar
            
        Returns:
            DataFrame con OHLCV data
        """
        try:
            logger.info(f"📊 Descargando datos para {symbol} - {period} - {days} días")
            
            # Calcular fecha de inicio
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            
            # Descargar datos
            ticker = yf.Ticker(symbol)
            data = ticker.history(
                start=start_date,
                end=end_date,
                interval=period,
                auto_adjust=True,
                prepost=True
            )
            
            if data.empty:
                raise ValueError(f"No se pudieron obtener datos para {symbol}")
                
            # Limpiar datos
            data = data.dropna()
            
            # Verificar columnas disponibles y renombrar solo las necesarias
            logger.info(f"Columnas recibidas: {list(data.columns)}")
            
            # Mapear columnas independientemente del número total
            column_mapping = {}
            for col in data.columns:
                col_lower = col.lower()
                if 'open' in col_lower:
                    column_mapping[col] = 'Open'
                elif 'high' in col_lower:
                    column_mapping[col] = 'High'
                elif 'low' in col_lower:
                    column_mapping[col] = 'Low'
                elif 'close' in col_lower:
                    column_mapping[col] = 'Close'
                elif 'volume' in col_lower:
                    column_mapping[col] = 'Volume'
            
            # Renombrar solo las columnas que encontramos
            data = data.rename(columns=column_mapping)
            
            # Verificar que tenemos las columnas necesarias
            required_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
            missing_cols = [col for col in required_cols if col not in data.columns]
            
            if missing_cols:
                raise ValueError(f"Columnas faltantes: {missing_cols}")
            
            # Seleccionar solo las columnas que necesitamos
            data = data[required_cols]
            
            logger.info(f"✅ {symbol}: {len(data)} barras descargadas")
            return data
            
        except Exception as e:
            logger.error(f"❌ Error descargando {symbol}: {str(e)}")
            raise
    
    def calculate_macd(self, data: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> Dict:
        """
        Calcular MACD (Moving Average Convergence Divergence)
        
        Args:
            data: DataFrame con datos OHLCV
            fast: Período EMA rápida (default: 12)
            slow: Período EMA lenta (default: 26)
            signal: Período señal (default: 9)
            
        Returns:
            Dict con macd, signal, histogram y señales
        """
        try:
            close = data['Close'].values
            
            # Calcular MACD usando TA-Lib
            macd_line, signal_line, histogram = talib.MACD(close, fast, slow, signal)
            
            # Obtener valores actuales (últimas barras)
            current_macd = macd_line[-1] if not np.isnan(macd_line[-1]) else 0
            current_signal = signal_line[-1] if not np.isnan(signal_line[-1]) else 0
            current_histogram = histogram[-1] if not np.isnan(histogram[-1]) else 0
            previous_histogram = histogram[-2] if len(histogram) > 1 and not np.isnan(histogram[-2]) else 0
            
            # Detectar cruces
            bullish_cross = current_histogram > 0 and previous_histogram <= 0
            bearish_cross = current_histogram < 0 and previous_histogram >= 0
            
            # Evaluar señal
            if bullish_cross:
                signal_strength = min(abs(current_histogram) * 50, 20)  # Max 20 puntos
                signal_type = "BULLISH_CROSS"
            elif bearish_cross:
                signal_strength = min(abs(current_histogram) * 50, 20)  # Max 20 puntos
                signal_type = "BEARISH_CROSS"
            elif current_histogram > 0:
                signal_strength = min(abs(current_histogram) * 30, 15)  # Menos puntos si no hay cruce
                signal_type = "BULLISH"
            elif current_histogram < 0:
                signal_strength = min(abs(current_histogram) * 30, 15)
                signal_type = "BEARISH"
            else:
                signal_strength = 0
                signal_type = "NEUTRAL"
            
            return {
                'macd': current_macd,
                'signal': current_signal,
                'histogram': current_histogram,
                'signal_type': signal_type,
                'signal_strength': signal_strength,
                'bullish_cross': bullish_cross,
                'bearish_cross': bearish_cross
            }
            
        except Exception as e:
            logger.error(f"❌ Error calculando MACD: {str(e)}")
            return self._get_empty_macd()
    
    def calculate_rsi(self, data: pd.DataFrame, period: int = 14) -> Dict:
        """
        Calcular RSI (Relative Strength Index)
        
        Args:
            data: DataFrame con datos OHLCV
            period: Período para cálculo (default: 14)
            
        Returns:
            Dict con RSI y señales
        """
        try:
            close = data['Close'].values
            
            # Calcular RSI usando TA-Lib
            rsi = talib.RSI(close, period)
            current_rsi = rsi[-1] if not np.isnan(rsi[-1]) else 50
            
            # Evaluar señales según umbrales
            if current_rsi < 30:
                signal_type = "OVERSOLD"
                signal_strength = 20  # Max puntos para RSI
            elif current_rsi < 40:
                signal_type = "OVERSOLD_MILD"
                signal_strength = 15
            elif current_rsi > 70:
                signal_type = "OVERBOUGHT"
                signal_strength = 20
            elif current_rsi > 60:
                signal_type = "OVERBOUGHT_MILD"
                signal_strength = 15
            else:
                signal_type = "NEUTRAL"
                signal_strength = 0
            
            return {
                'rsi': current_rsi,
                'signal_type': signal_type,
                'signal_strength': signal_strength,
                'oversold': current_rsi < 40,
                'overbought': current_rsi > 60
            }
            
        except Exception as e:
            logger.error(f"❌ Error calculando RSI: {str(e)}")
            return self._get_empty_rsi()
    
    def calculate_vwap(self, data: pd.DataFrame) -> Dict:
        """
        Calcular VWAP (Volume Weighted Average Price)
        
        Args:
            data: DataFrame con datos OHLCV
            
        Returns:
            Dict con VWAP y señales
        """
        try:
            # Precio típico (HLC/3)
            typical_price = (data['High'] + data['Low'] + data['Close']) / 3
            
            # VWAP = suma(precio_típico * volumen) / suma(volumen)
            cumulative_pv = (typical_price * data['Volume']).cumsum()
            cumulative_volume = data['Volume'].cumsum()
            
            vwap = cumulative_pv / cumulative_volume
            current_vwap = vwap.iloc[-1]
            current_price = data['Close'].iloc[-1]
            
            # Calcular desviación del VWAP
            deviation_pct = ((current_price - current_vwap) / current_vwap) * 100
            
            # Evaluar señales
            if abs(deviation_pct) <= 0.5:
                signal_type = "NEAR_VWAP"
                signal_strength = 15  # Max puntos para VWAP
            elif -1.0 <= deviation_pct <= -0.5:
                signal_type = "BELOW_VWAP"
                signal_strength = 10
            elif 0.5 <= deviation_pct <= 1.0:
                signal_type = "ABOVE_VWAP"
                signal_strength = 10
            elif deviation_pct < -1.0:
                signal_type = "FAR_BELOW_VWAP"
                signal_strength = 5
            elif deviation_pct > 1.0:
                signal_type = "FAR_ABOVE_VWAP"
                signal_strength = 15 if deviation_pct > 1.0 else 5  # Bueno para shorts
            else:
                signal_type = "NEUTRAL"
                signal_strength = 0
            
            return {
                'vwap': current_vwap,
                'current_price': current_price,
                'deviation_pct': deviation_pct,
                'signal_type': signal_type,
                'signal_strength': signal_strength,
                'near_vwap': abs(deviation_pct) <= 0.5,
                'above_vwap': deviation_pct > 1.0
            }
            
        except Exception as e:
            logger.error(f"❌ Error calculando VWAP: {str(e)}")
            return self._get_empty_vwap()
    
    def calculate_roc(self, data: pd.DataFrame, period: int = 10) -> Dict:
        """
        Calcular ROC (Rate of Change / Momentum)
        
        Args:
            data: DataFrame con datos OHLCV
            period: Período para cálculo (default: 10)
            
        Returns:
            Dict con ROC y señales
        """
        try:
            close = data['Close'].values
            
            # Calcular ROC usando TA-Lib
            roc = talib.ROC(close, period)
            current_roc = roc[-1] if not np.isnan(roc[-1]) else 0
            
            # Evaluar momentum
            if current_roc > 2.5:
                signal_type = "STRONG_BULLISH"
                signal_strength = 20  # Max puntos para ROC
            elif current_roc > 1.5:
                signal_type = "BULLISH"
                signal_strength = 15
            elif current_roc < -2.5:
                signal_type = "STRONG_BEARISH"
                signal_strength = 20
            elif current_roc < -1.5:
                signal_type = "BEARISH"
                signal_strength = 15
            elif -0.5 <= current_roc <= 0.5:
                signal_type = "SIDEWAYS"
                signal_strength = 0
            else:
                signal_type = "NEUTRAL"
                signal_strength = 5
            
            return {
                'roc': current_roc,
                'signal_type': signal_type,
                'signal_strength': signal_strength,
                'bullish_momentum': current_roc > 1.5,
                'bearish_momentum': current_roc < -1.5
            }
            
        except Exception as e:
            logger.error(f"❌ Error calculando ROC: {str(e)}")
            return self._get_empty_roc()
    
    def calculate_bollinger_bands(self, data: pd.DataFrame, period: int = 20, std_dev: float = 2.0) -> Dict:
        """
        Calcular Bollinger Bands
        
        Args:
            data: DataFrame con datos OHLCV
            period: Período para media móvil (default: 20)
            std_dev: Desviaciones estándar (default: 2.0)
            
        Returns:
            Dict con Bollinger Bands y señales
        """
        try:
            close = data['Close'].values
            
            # Calcular Bollinger Bands usando TA-Lib
            upper_band, middle_band, lower_band = talib.BBANDS(close, period, std_dev, std_dev)
            
            current_price = close[-1]
            current_upper = upper_band[-1] if not np.isnan(upper_band[-1]) else current_price * 1.02
            current_middle = middle_band[-1] if not np.isnan(middle_band[-1]) else current_price
            current_lower = lower_band[-1] if not np.isnan(lower_band[-1]) else current_price * 0.98
            
            # Calcular posición relativa dentro de las bandas
            band_width = current_upper - current_lower
            if band_width > 0:
                bb_position = (current_price - current_lower) / band_width
            else:
                bb_position = 0.5
            
            # Evaluar señales
            if bb_position <= 0.2:
                signal_type = "NEAR_LOWER_BAND"
                signal_strength = 15  # Max puntos para BB
            elif bb_position >= 0.8:
                signal_type = "NEAR_UPPER_BAND"
                signal_strength = 15
            elif 0.4 <= bb_position <= 0.6:
                signal_type = "MIDDLE_BAND"
                signal_strength = 5
            else:
                signal_type = "NEUTRAL"
                signal_strength = 0
            
            return {
                'upper_band': current_upper,
                'middle_band': current_middle,
                'lower_band': current_lower,
                'bb_position': bb_position,
                'signal_type': signal_type,
                'signal_strength': signal_strength,
                'near_lower': bb_position <= 0.2,
                'near_upper': bb_position >= 0.8
            }
            
        except Exception as e:
            logger.error(f"❌ Error calculando Bollinger Bands: {str(e)}")
            return self._get_empty_bb()
    
    def calculate_volume_oscillator(self, data: pd.DataFrame, fast: int = 5, slow: int = 20) -> Dict:
        """
        Calcular Oscilador de Volumen
        """
        try:
            volume = data['Volume'].values.astype(np.float64)  # ← CAMBIO AQUÍ
            
            # Calcular EMAs del volumen usando TA-Lib
            ema_fast = talib.EMA(volume, fast)
            ema_slow = talib.EMA(volume, slow)
            
            current_fast = ema_fast[-1] if not np.isnan(ema_fast[-1]) else volume[-1]
            current_slow = ema_slow[-1] if not np.isnan(ema_slow[-1]) else volume[-1]
            
            # Calcular oscilador
            if current_slow > 0:
                volume_oscillator = ((current_fast - current_slow) / current_slow) * 100
            else:
                volume_oscillator = 0
            
            # Evaluar señales
            if volume_oscillator > 75:
                signal_type = "VERY_HIGH_VOLUME"
                signal_strength = 10  # Bonus points
            elif volume_oscillator > 50:
                signal_type = "HIGH_VOLUME"
                signal_strength = 8
            elif volume_oscillator > 25:
                signal_type = "ELEVATED_VOLUME"
                signal_strength = 5
            elif volume_oscillator < -25:
                signal_type = "LOW_VOLUME"
                signal_strength = 0
            else:
                signal_type = "NORMAL_VOLUME"
                signal_strength = 3
            
            return {
                'volume_oscillator': volume_oscillator,
                'ema_fast': current_fast,
                'ema_slow': current_slow,
                'signal_type': signal_type,
                'signal_strength': signal_strength,
                'high_volume': volume_oscillator > 50
            }
            
        except Exception as e:
            logger.error(f"❌ Error calculando Oscilador de Volumen: {str(e)}")
            return self._get_empty_volume()
    
    def calculate_atr(self, data: pd.DataFrame, period: int = 14) -> Dict:
        """
        Calcular ATR (Average True Range)
        
        Args:
            data: DataFrame con datos OHLCV
            period: Período para cálculo (default: 14)
            
        Returns:
            Dict con ATR y métricas de volatilidad
        """
        try:
            high = data['High'].values
            low = data['Low'].values
            close = data['Close'].values
            
            # Calcular ATR usando TA-Lib
            atr = talib.ATR(high, low, close, period)
            current_atr = atr[-1] if not np.isnan(atr[-1]) else 0
            current_price = close[-1]
            
            # Calcular ATR como porcentaje del precio
            if current_price > 0:
                atr_percentage = (current_atr / current_price) * 100
            else:
                atr_percentage = 0
            
            # Clasificar volatilidad
            if atr_percentage < 1.0:
                volatility_level = "LOW"
            elif atr_percentage < 2.0:
                volatility_level = "NORMAL"
            elif atr_percentage < 3.0:
                volatility_level = "HIGH"
            else:
                volatility_level = "VERY_HIGH"
            
            return {
                'atr': current_atr,
                'atr_percentage': atr_percentage,
                'volatility_level': volatility_level,
                'current_price': current_price
            }
            
        except Exception as e:
            logger.error(f"❌ Error calculando ATR: {str(e)}")
            return self._get_empty_atr()
    

    def get_all_indicators(self, symbol: str, period: str = "15m", days: int = 30) -> Dict:
        """
        Calcular todos los indicadores para un símbolo - FIXED OHLC VERSION
        
        Args:
            symbol: Símbolo a analizar
            period: Timeframe (default: "15m")
            days: Días de historial (default: 30)
            
        Returns:
            Dict con todos los indicadores + datos OHLC completos
        """
        try:
            logger.info(f"🔍 Calculando indicadores para {symbol}")
            
            # Obtener datos de mercado
            data = self.get_market_data(symbol, period, days)
            
            if len(data) < 30:
                raise ValueError(f"Datos insuficientes para {symbol}: {len(data)} barras")
            
            # ✅ FIXED: Extraer datos OHLCV de la última vela
            last_candle = data.iloc[-1]
            current_open = float(last_candle['Open'])
            current_high = float(last_candle['High'])
            current_low = float(last_candle['Low'])
            current_close = float(last_candle['Close'])
            current_volume = int(last_candle['Volume'])
            
            # Calcular todos los indicadores
            indicators = {
                'symbol': symbol,
                'timestamp': datetime.now(),
                'data_points': len(data),
                
                # ✅ FIXED: Incluir TODOS los precios OHLC
                'current_price': current_close,  # Este es el close_price
                'open_price': current_open,      # ✅ NUEVO
                'high_price': current_high,      # ✅ NUEVO
                'low_price': current_low,        # ✅ NUEVO
                'close_price': current_close,    # Explícito para claridad
                'current_volume': current_volume,
                
                # Indicadores técnicos
                'macd': self.calculate_macd(data),
                'rsi': self.calculate_rsi(data),
                'vwap': self.calculate_vwap(data),
                'roc': self.calculate_roc(data),
                'bollinger': self.calculate_bollinger_bands(data),
                'volume_osc': self.calculate_volume_oscillator(data),
                'atr': self.calculate_atr(data),
                
                # 🆕 NUEVO: Conservar datos OHLCV para targets adaptativos
                'market_data': data  # Datos completos para análisis técnico
            }
            
            logger.info(f"✅ {symbol}: Indicadores calculados exitosamente")
            
            # 🆕 GUARDAR EN BASE DE DATOS con OHLC completo
            try:
                from database.connection import save_indicators_data
                save_indicators_data(indicators)
            except Exception as db_error:
                logger.warning(f"⚠️ Error guardando indicadores en DB: {db_error}")

            return indicators
            
        except Exception as e:
            logger.error(f"❌ Error calculando indicadores para {symbol}: {str(e)}")
            raise
    
    def print_indicators_summary(self, indicators: Dict) -> None:
        """
        Imprimir resumen de indicadores para debugging
        
        Args:
            indicators: Dict con todos los indicadores
        """
        try:
            symbol = indicators['symbol']
            price = indicators['current_price']
            
            print(f"\n📊 INDICADORES TÉCNICOS - {symbol} (${price:.2f})")
            print("=" * 60)
            
            # MACD
            macd_data = indicators['macd']
            print(f"MACD: {macd_data['histogram']:.4f} | {macd_data['signal_type']} | {macd_data['signal_strength']} pts")
            
            # RSI
            rsi_data = indicators['rsi']
            print(f"RSI: {rsi_data['rsi']:.1f} | {rsi_data['signal_type']} | {rsi_data['signal_strength']} pts")
            
            # VWAP
            vwap_data = indicators['vwap']
            print(f"VWAP: ${vwap_data['vwap']:.2f} ({vwap_data['deviation_pct']:+.2f}%) | {vwap_data['signal_type']} | {vwap_data['signal_strength']} pts")
            
            # ROC
            roc_data = indicators['roc']
            print(f"ROC: {roc_data['roc']:+.2f}% | {roc_data['signal_type']} | {roc_data['signal_strength']} pts")
            
            # Bollinger Bands
            bb_data = indicators['bollinger']
            print(f"BB: Posición {bb_data['bb_position']:.2f} | {bb_data['signal_type']} | {bb_data['signal_strength']} pts")
            
            # Volume Oscillator
            vol_data = indicators['volume_osc']
            print(f"VOL: {vol_data['volume_oscillator']:+.1f}% | {vol_data['signal_type']} | {vol_data['signal_strength']} pts")
            
            # ATR
            atr_data = indicators['atr']
            print(f"ATR: ${atr_data['atr']:.2f} ({atr_data['atr_percentage']:.2f}%) | {atr_data['volatility_level']}")
            
            print("=" * 60)
            
        except Exception as e:
            logger.error(f"❌ Error imprimiendo resumen: {str(e)}")
    
    # Métodos auxiliares para manejo de errores
    def _get_empty_macd(self) -> Dict:
        return {
            'macd': 0, 'signal': 0, 'histogram': 0,
            'signal_type': 'ERROR', 'signal_strength': 0,
            'bullish_cross': False, 'bearish_cross': False
        }
    
    def _get_empty_rsi(self) -> Dict:
        return {
            'rsi': 50, 'signal_type': 'ERROR', 'signal_strength': 0,
            'oversold': False, 'overbought': False
        }
    
    def _get_empty_vwap(self) -> Dict:
        return {
            'vwap': 0, 'current_price': 0, 'deviation_pct': 0,
            'signal_type': 'ERROR', 'signal_strength': 0,
            'near_vwap': False, 'above_vwap': False
        }
    
    def _get_empty_roc(self) -> Dict:
        return {
            'roc': 0, 'signal_type': 'ERROR', 'signal_strength': 0,
            'bullish_momentum': False, 'bearish_momentum': False
        }
    
    def _get_empty_bb(self) -> Dict:
        return {
            'upper_band': 0, 'middle_band': 0, 'lower_band': 0,
            'bb_position': 0.5, 'signal_type': 'ERROR', 'signal_strength': 0,
            'near_lower': False, 'near_upper': False
        }
    
    def _get_empty_volume(self) -> Dict:
        return {
            'volume_oscillator': 0, 'ema_fast': 0, 'ema_slow': 0,
            'signal_type': 'ERROR', 'signal_strength': 0,
            'high_volume': False
        }
    
    def _get_empty_atr(self) -> Dict:
        return {
            'atr': 0, 'atr_percentage': 0,
            'volatility_level': 'UNKNOWN', 'current_price': 0
        }


# =============================================================================
# 🧪 FUNCIONES DE TESTING Y DEMO
# =============================================================================

def test_single_indicator(symbol: str = "SPY"):
    """
    Test de un solo símbolo para verificar funcionamiento
    """
    print(f"🧪 TESTING INDICADORES - {symbol}")
    print("=" * 50)
    
    try:
        # Crear instancia
        indicators = TechnicalIndicators()
        
        # Calcular indicadores
        result = indicators.get_all_indicators(symbol)
        
        # Imprimir resumen
        indicators.print_indicators_summary(result)
        
        print("✅ Test exitoso!")
        return result
        
    except Exception as e:
        print(f"❌ Error en test: {str(e)}")
        return None

def test_multiple_symbols():
    """
    Test con múltiples símbolos
    """
    symbols = ["SPY", "AAPL", "NVDA"]
    
    print("🧪 TESTING MÚLTIPLES SÍMBOLOS")
    print("=" * 50)
    
    indicators = TechnicalIndicators()
    results = {}
    
    for symbol in symbols:
        try:
            print(f"\n🔍 Procesando {symbol}...")
            result = indicators.get_all_indicators(symbol)
            results[symbol] = result
            print(f"✅ {symbol} completado")
            
        except Exception as e:
            print(f"❌ {symbol} falló: {str(e)}")
            results[symbol] = None
    
    return results

if __name__ == "__main__":
    # Ejecutar tests si se ejecuta directamente
    print("🚀 SISTEMA DE INDICADORES TÉCNICOS V2.0")
    print("=" * 50)
    
    # Test básico
    test_result = test_single_indicator("SPY")
    
    if test_result:
        print("\n🎯 ¿Quieres probar con más símbolos? (y/n)")
        response = input().lower().strip()
        
        if response == 'y':
            test_multiple_symbols()
    
    print("\n🏁 Tests completados!")