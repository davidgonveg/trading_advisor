#!/usr/bin/env python3
"""
📊 SISTEMA DE INDICADORES TÉCNICOS V3.2 - REAL DATA GAP FILLING
========================================================================

🆕 V3.2 CORRECCIONES CRÍTICAS:
- Gap filling con datos REALES de yfinance
- Worst-case scenario conservador si no hay datos
- NO inventa precios (High/Low reales para stops/targets)
- Backward compatible con V3.1

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
# import yfinance as yf (Removed in V3.3)
try:
    import talib
    HAS_TALIB = True
except ImportError:
    HAS_TALIB = False
    print("⚠️ TA-Lib not found. Using Pandas fallbacks.")
import logging
from typing import Dict, Tuple, Optional, Union, List
from datetime import datetime, timedelta
import warnings
import pytz
import time

# Importar configuración
try:
    import config
    # Usar configuración extended si está disponible
    USE_EXTENDED_HOURS = getattr(config, 'CONTINUOUS_DATA_CONFIG', {}).get('ENABLE_EXTENDED_HOURS', True)
    USE_GAP_DETECTION = getattr(config, 'CONTINUOUS_DATA_CONFIG', {}).get('AUTO_FILL_GAPS', True)
    FORCE_PREPOST = getattr(config, 'YFINANCE_EXTENDED_CONFIG', {}).get('PREPOST_REQUIRED', True)
    
    GAP_CONFIG = getattr(config, 'GAP_DETECTION_CONFIG', {
        'MIN_GAP_MINUTES': 60,
        'OVERNIGHT_GAP_HOURS': [20, 4],
        'FILL_STRATEGIES': {
            'SMALL_GAP': 'REAL_DATA',
            'OVERNIGHT_GAP': 'REAL_DATA',
            'WEEKEND_GAP': 'REAL_DATA',   # Changed from PRESERVE_GAP to ensure continuity
            'HOLIDAY_GAP': 'REAL_DATA',    # Changed from PRESERVE_GAP
            'UNKNOWN_GAP': 'REAL_DATA'    # Force fill unknown gaps to prevent persistency issues
        }
    })
    
    REAL_DATA_CONFIG = getattr(config, 'GAP_DETECTION_CONFIG', {}).get('REAL_DATA_CONFIG', {
        'USE_YFINANCE': True,
        'INCLUDE_PREPOST': True,
        'FALLBACK_TO_CONSERVATIVE': True,
        'MAX_GAP_TO_FILL_HOURS': 168,
        'RETRY_ATTEMPTS': 3,
        'RETRY_DELAY_SECONDS': 2
    })
    
    WORST_CASE_CONFIG = getattr(config, 'GAP_DETECTION_CONFIG', {}).get('WORST_CASE_CONFIG', {
        'ENABLED': True,
        'METHOD': 'CONSERVATIVE_RANGE',
        'PRICE_MOVEMENT_ESTIMATE': 0.02,
        'USE_ATR_IF_AVAILABLE': True
    })
    
    logger = logging.getLogger(__name__)
    logger.info("✅ Extended Hours V3.2 configurado con REAL DATA")
    
except ImportError:
    # Fallback a configuración básica
    USE_EXTENDED_HOURS = True
    USE_GAP_DETECTION = True
    FORCE_PREPOST = True
    GAP_CONFIG = {
        'MIN_GAP_MINUTES': 60,
        'OVERNIGHT_GAP_HOURS': [20, 4],
        'FILL_STRATEGIES': {
            'SMALL_GAP': 'REAL_DATA',
            'OVERNIGHT_GAP': 'REAL_DATA',
            'WEEKEND_GAP': 'REAL_DATA',
            'UNKNOWN_GAP': 'REAL_DATA'
        }
    }
    REAL_DATA_CONFIG = {
        'USE_YFINANCE': True,
        'INCLUDE_PREPOST': True,
        'FALLBACK_TO_CONSERVATIVE': True,
        'MAX_GAP_TO_FILL_HOURS': 168,
        'RETRY_ATTEMPTS': 3
    }
    WORST_CASE_CONFIG = {
        'ENABLED': True,
        'METHOD': 'CONSERVATIVE_RANGE',
        'PRICE_MOVEMENT_ESTIMATE': 0.02
    }
    logger = logging.getLogger(__name__)
    logger.warning("⚠️ Config no disponible, usando configuración básica V3.2")

# Configurar logging
logging.basicConfig(level=logging.INFO)

# Suprimir warnings de yfinance
warnings.filterwarnings('ignore', category=FutureWarning)

class TechnicalIndicators:
    """
    Clase principal para calcular todos los indicadores técnicos con Gap Filling REAL
    """
    
    def __init__(self):
        """Inicializar la clase de indicadores"""
        self.last_update = {}  # Cache para evitar recálculos innecesarios
        self.gap_stats = {
            'gaps_detected': 0, 
            'gaps_filled': 0, 
            'gaps_with_real_data': 0,  # 🆕 Contador datos reales
            'gaps_worst_case': 0,       # 🆕 Contador worst-case
            'gaps_preserved': 0,        # 🆕 Contador gaps preservados
            'last_check': None
        }
        
        logger.info("🔍 TechnicalIndicators V3.2 inicializado")
        logger.info(f"🕐 Extended Hours: {'✅ Habilitado' if USE_EXTENDED_HOURS else '❌ Deshabilitado'}")
        logger.info(f"🔧 Gap Detection: {'✅ Habilitado' if USE_GAP_DETECTION else '❌ Deshabilitado'}")
        logger.info(f"📊 Real Data Filling: {'✅ Habilitado' if REAL_DATA_CONFIG.get('USE_YFINANCE') else '❌ Deshabilitado'}")
    
    # get_market_data removed in V3.3 - Use DataManager instead

    # Deprecated data fetching methods removed (V3.3)

    
    def get_gap_statistics(self) -> Dict:
        """
        🆕 V3.2: Obtener estadísticas mejoradas de gaps
        """
        total_filled = self.gap_stats['gaps_filled']
        
        return {
            'gaps_detected': self.gap_stats['gaps_detected'],
            'gaps_filled': total_filled,
            'gaps_with_real_data': self.gap_stats['gaps_with_real_data'],
            'gaps_worst_case': self.gap_stats['gaps_worst_case'],
            'gaps_preserved': self.gap_stats['gaps_preserved'],
            'last_check': self.gap_stats['last_check'],
            'fill_rate': (
                total_filled / max(1, self.gap_stats['gaps_detected']) * 100
            ),
            'real_data_rate': (
                self.gap_stats['gaps_with_real_data'] / max(1, total_filled) * 100
                if total_filled > 0 else 0
            )
        }

    # =============================================================================
    # 📊 MÉTODOS DE INDICADORES TÉCNICOS (SIN CAMBIOS - BACKWARD COMPATIBLE)
    # =============================================================================
    
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
            
            # Calcular MACD
            if HAS_TALIB:
                macd_line, signal_line, histogram = talib.MACD(close, fast, slow, signal)
            else:
                # Pandas fallback
                ema_fast = pd.Series(close).ewm(span=fast, adjust=False).mean()
                ema_slow = pd.Series(close).ewm(span=slow, adjust=False).mean()
                macd_line = (ema_fast - ema_slow).values
                signal_line = pd.Series(macd_line).ewm(span=signal, adjust=False).mean().values
                histogram = macd_line - signal_line
            
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
            
            # Calcular RSI
            if HAS_TALIB:
                rsi = talib.RSI(close, timeperiod=period)
            else:
                delta = pd.Series(close).diff()
                gain = (delta.where(delta > 0, 0)).fillna(0)
                loss = (-delta.where(delta < 0, 0)).fillna(0)
                # Calculate average gain and loss using rolling mean
                # The original code used 'PERIOD' which is not defined, assuming it should be 'period'
                avg_gain = gain.rolling(window=period, min_periods=period).mean()
                avg_loss = loss.rolling(window=period, min_periods=period).mean()
                
                # Avoid division by zero
                rs = avg_gain / avg_loss.replace(0, np.nan)
                rsi = (100 - (100 / (1 + rs))).fillna(50).values
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
            
            # Calcular ROC
            if HAS_TALIB:
                roc = talib.ROC(close, timeperiod=period)
            else:
                roc = pd.Series(close).pct_change(periods=period).fillna(0).values * 100
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
            
            # Calcular Bollinger Bands
            if HAS_TALIB:
                upper_band, middle_band, lower_band = talib.BBANDS(close, timeperiod=period, nbdevup=std_dev, nbdevdn=std_dev, matype=0)
            else:
                middle_series = pd.Series(close).rolling(window=period).mean()
                std_series = pd.Series(close).rolling(window=period).std()
                upper_band = (middle_series + (std_series * std_dev)).values
                lower_band = (middle_series - (std_series * std_dev)).values
                middle_band = middle_series.values
            
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
            volume = data['Volume'].values.astype(np.float64)
            
            # Calcular EMAs del volumen
            if HAS_TALIB:
                ema_fast = talib.EMA(volume, fast)
                ema_slow = talib.EMA(volume, slow)
            else:
                ema_fast = pd.Series(volume).ewm(span=fast, adjust=False).mean().values
                ema_slow = pd.Series(volume).ewm(span=slow, adjust=False).mean().values
            
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
            
            # Calcular ATR
            if HAS_TALIB:
                atr = talib.ATR(high, low, close, timeperiod=period)
            else:
                high_s = pd.Series(high)
                low_s = pd.Series(low)
                close_s = pd.Series(close)
                tr1 = high_s - low_s
                tr2 = abs(high_s - close_s.shift(1))
                tr3 = abs(low_s - close_s.shift(1))
                tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
                atr = tr.rolling(window=period).mean().values
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

    def calculate_all_indicators(self, data: pd.DataFrame, symbol: str) -> Dict:
        """
        🆕 V3.3: Calcular todos los indicadores sobre un DF dado.
        
        Args:
            data: DataFrame con datos OHLCV ya limpios y completos.
            symbol: Símbolo para metadatos.
            
        Returns:
            Dict con todos los indicadores.
        """
        try:
            logger.info(f"🔍 Calculando indicadores V3.3 para {symbol}")
            
            if data is None or data.empty:
                raise ValueError(f"Datos vacíos proporcionados para {symbol}")
            
            if len(data) < 30:
                raise ValueError(f"Datos insuficientes para {symbol}: {len(data)} barras")
            
            # Extraer datos OHLCV de la última vela
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
                
                # Incluir TODOS los precios OHLC
                'current_price': current_close,
                'open_price': current_open,
                'high_price': current_high,
                'low_price': current_low,
                'close_price': current_close,
                'current_volume': current_volume,
                
                # Indicadores técnicos
                'macd': self.calculate_macd(data),
                'rsi': self.calculate_rsi(data),
                'vwap': self.calculate_vwap(data),
                'roc': self.calculate_roc(data),
                'bollinger': self.calculate_bollinger_bands(data),
                'volume_osc': self.calculate_volume_oscillator(data),
                'atr': self.calculate_atr(data),
                
                # Conservar datos OHLCV para targets adaptativos
                'market_data': data,
                
                # 🆕 V3.2: Metadatos de gap filling
                'extended_hours_used': USE_EXTENDED_HOURS,
                'real_data_filling_used': REAL_DATA_CONFIG.get('USE_YFINANCE', False),
                'gap_stats': self.get_gap_statistics()
            }
            
            logger.info(f"✅ {symbol}: Indicadores V3.2 calculados exitosamente")
            
            # Guardar en base de datos
            try:
                from database.connection import save_indicators_data
                save_indicators_data(indicators)
            except Exception as db_error:
                logger.warning(f"⚠️ Error guardando indicadores en DB: {db_error}")

            return indicators
            
        except Exception as e:
            logger.error(f"❌ Error calculando indicadores V3.2 para {symbol}: {str(e)}")
            raise
    
    def print_indicators_summary(self, indicators: Dict) -> None:
        """
        🆕 V3.2: Imprimir resumen con estadísticas de gap filling real
        
        Args:
            indicators: Dict con todos los indicadores
        """
        try:
            symbol = indicators['symbol']
            price = indicators['current_price']
            
            print(f"\n📊 INDICADORES TÉCNICOS V3.2 - {symbol} (${price:.2f})")
            print("=" * 60)
            
            # 🆕 V3.2: Info de gap filling con datos reales
            if indicators.get('extended_hours_used', False):
                print(f"🕐 Extended Hours: ✅ ACTIVO")
                
                if indicators.get('real_data_filling_used', False):
                    print(f"📊 Real Data Filling: ✅ HABILITADO")
                
                gap_stats = indicators.get('gap_stats', {})
                if gap_stats.get('gaps_detected', 0) > 0:
                    print(f"🔧 Gap Stats:")
                    print(f"   • Detectados: {gap_stats['gaps_detected']}")
                    print(f"   • Rellenados: {gap_stats['gaps_filled']}")
                    print(f"   • Con datos reales: {gap_stats['gaps_with_real_data']} "
                          f"({gap_stats.get('real_data_rate', 0):.1f}%)")
                    print(f"   • Worst-case: {gap_stats['gaps_worst_case']}")
                    print(f"   • Preservados: {gap_stats['gaps_preserved']}")
            else:
                print(f"🕐 Extended Hours: ❌ DESHABILITADO")
            print("-" * 60)
            
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
    
    # Métodos auxiliares para manejo de errores (sin cambios)
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
# 🧪 FUNCIONES DE TESTING Y DEMO V3.2
# =============================================================================

def test_real_data_gap_filling(symbol: str = "SPY"):
    """
    🆕 V3.2: Test específico para REAL DATA gap filling
    """
    print(f"🧪 TESTING REAL DATA GAP FILLING V3.2 - {symbol}")
    print("=" * 60)
    
    try:
        # Crear instancia
        indicators = TechnicalIndicators()
        
        print("1️⃣ Testeando descarga con real data gap filling...")
        result = indicators.get_all_indicators(symbol)
        
        print(f"✅ Datos obtenidos: {result['data_points']} barras")
        print(f"🕐 Extended hours: {result.get('extended_hours_used', 'N/A')}")
        print(f"📊 Real data filling: {result.get('real_data_filling_used', 'N/A')}")
        
        # Mostrar estadísticas detalladas de gaps
        gap_stats = result.get('gap_stats', {})
        print(f"\n📊 ESTADÍSTICAS DETALLADAS DE GAPS:")
        print(f"   Detectados: {gap_stats.get('gaps_detected', 0)}")
        print(f"   Rellenados: {gap_stats.get('gaps_filled', 0)}")
        print(f"   └─ Con datos REALES: {gap_stats.get('gaps_with_real_data', 0)} "
              f"({gap_stats.get('real_data_rate', 0):.1f}%)")
        print(f"   └─ Worst-case: {gap_stats.get('gaps_worst_case', 0)}")
        print(f"   Preservados (weekend/holiday): {gap_stats.get('gaps_preserved', 0)}")
        print(f"   Tasa éxito: {gap_stats.get('fill_rate', 0):.1f}%")
        
        # Validar calidad de datos para backtesting
        market_data = result.get('market_data')
        if market_data is not None and not market_data.empty:
            # Verificar barras flat (H=L=C) que son problemáticas
            flat_bars = market_data[market_data['High'] == market_data['Low']]
            flat_pct = (len(flat_bars) / len(market_data)) * 100
            
            print(f"\n🔍 VALIDACIÓN CALIDAD PARA BACKTESTING:")
            print(f"   Total barras: {len(market_data)}")
            print(f"   Barras flat (H=L): {len(flat_bars)} ({flat_pct:.1f}%)")
            
            if flat_pct > 10:
                print(f"   ⚠️ ADVERTENCIA: >10% barras flat, revisar gap filling")
            elif flat_pct > 5:
                print(f"   ⚠️ Aceptable pero revisar: 5-10% barras flat")
            else:
                print(f"   ✅ Excelente: <5% barras flat")
        
        # Imprimir resumen
        indicators.print_indicators_summary(result)
        
        print("\n✅ Test Real Data Gap Filling exitoso!")
        return result
        
    except Exception as e:
        print(f"❌ Error en test: {str(e)}")
        import traceback
        traceback.print_exc()
        return None

def test_single_indicator(symbol: str = "SPY"):
    """
    Test de un solo símbolo para verificar funcionamiento
    """
    print(f"🧪 TESTING INDICADORES V3.2 - {symbol}")
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
    
    print("🧪 TESTING MÚLTIPLES SÍMBOLOS V3.2")
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
    
    # Mostrar estadísticas finales agregadas
    print(f"\n📊 ESTADÍSTICAS FINALES AGREGADAS:")
    gap_stats = indicators.get_gap_statistics()
    print(f"   Total gaps detectados: {gap_stats['gaps_detected']}")
    print(f"   Total gaps rellenados: {gap_stats['gaps_filled']}")
    print(f"   Con datos REALES: {gap_stats['gaps_with_real_data']} ({gap_stats['real_data_rate']:.1f}%)")
    print(f"   Worst-case: {gap_stats['gaps_worst_case']}")
    print(f"   Preservados: {gap_stats['gaps_preserved']}")
    print(f"   Tasa éxito global: {gap_stats['fill_rate']:.1f}%")
    
    return results

def validate_backtesting_data_quality(symbol: str = "SPY", days: int = 30):
    """
    🆕 V3.2: Validar que los datos son aptos para backtesting
    
    Verifica que:
    - Tenemos suficientes datos reales (no sintéticos)
    - Las barras tienen High/Low diferentes (no flat)
    - Los gaps están bien manejados
    """
    print(f"🔍 VALIDACIÓN CALIDAD DATOS PARA BACKTESTING - {symbol}")
    print("=" * 60)
    
    try:
        indicators = TechnicalIndicators()
        
        # Obtener datos
        print(f"📊 Descargando {days} días de datos...")
        data = indicators.get_market_data(symbol, period='15m', days=days)
        
        print(f"\n✅ {len(data)} barras obtenidas")
        
        # 1. Verificar barras flat (H=L)
        flat_bars = data[data['High'] == data['Low']]
        flat_pct = (len(flat_bars) / len(data)) * 100
        
        print(f"\n1️⃣ BARRAS FLAT (H=L):")
        print(f"   Total: {len(flat_bars)} ({flat_pct:.2f}%)")
        
        if flat_pct > 10:
            print(f"   ❌ CRÍTICO: >10% barras flat - NO apto para backtesting")
            print(f"   ⚠️ Los stops/targets no se pueden verificar correctamente")
        elif flat_pct > 5:
            print(f"   ⚠️ ADVERTENCIA: 5-10% barras flat - revisar")
        else:
            print(f"   ✅ EXCELENTE: <5% barras flat - apto para backtesting")
        
        # 2. Verificar consistencia OHLC
        inconsistent = (
            (data['High'] < data['Low']) |
            (data['High'] < data['Open']) |
            (data['High'] < data['Close']) |
            (data['Low'] > data['Open']) |
            (data['Low'] > data['Close'])
        )
        inconsistent_pct = (inconsistent.sum() / len(data)) * 100
        
        print(f"\n2️⃣ CONSISTENCIA OHLC:")
        print(f"   Barras inconsistentes: {inconsistent.sum()} ({inconsistent_pct:.2f}%)")
        
        if inconsistent_pct > 1:
            print(f"   ❌ PROBLEMA: >1% inconsistencias")
        elif inconsistent_pct > 0:
            print(f"   ⚠️ Pocas inconsistencias detectadas")
        else:
            print(f"   ✅ Sin inconsistencias OHLC")
        
        # 3. Verificar gaps temporales
        time_diffs = data.index.to_series().diff()
        expected_interval = timedelta(minutes=15)
        
        # Gaps significativos (> 2 horas)
        significant_gaps = time_diffs[time_diffs > timedelta(hours=2)]
        
        print(f"\n3️⃣ ANÁLISIS DE GAPS:")
        print(f"   Gaps significativos (>2h): {len(significant_gaps)}")
        
        if len(significant_gaps) > 0:
            print(f"   Gaps encontrados:")
            for idx, gap in significant_gaps.items():
                gap_hours = gap.total_seconds() / 3600
                print(f"      • {idx}: {gap_hours:.1f} horas")
        
        # 4. Obtener estadísticas de gap filling
        gap_stats = indicators.get_gap_statistics()
        
        print(f"\n4️⃣ ESTADÍSTICAS GAP FILLING:")
        print(f"   Gaps detectados: {gap_stats['gaps_detected']}")
        print(f"   Gaps rellenados: {gap_stats['gaps_filled']}")
        print(f"   Con datos REALES: {gap_stats['gaps_with_real_data']} ({gap_stats['real_data_rate']:.1f}%)")
        print(f"   Worst-case usado: {gap_stats['gaps_worst_case']}")
        print(f"   Preservados: {gap_stats['gaps_preserved']}")
        
        # 5. Decisión final
        print(f"\n{'='*60}")
        print(f"📊 DECISIÓN FINAL:")
        
        backtest_ready = (
            flat_pct <= 10 and
            inconsistent_pct <= 1 and
            len(data) >= 1000 and
            gap_stats['real_data_rate'] >= 60  # Al menos 60% datos reales
        )
        
        if backtest_ready:
            print(f"✅ APTO PARA BACKTESTING")
            print(f"   • Calidad de datos: BUENA")
            print(f"   • Stops/targets verificables: SÍ")
            print(f"   • Datos reales suficientes: SÍ")
        else:
            print(f"❌ NO APTO PARA BACKTESTING")
            print(f"   Razones:")
            if flat_pct > 10:
                print(f"   • Demasiadas barras flat ({flat_pct:.1f}%)")
            if inconsistent_pct > 1:
                print(f"   • Inconsistencias OHLC ({inconsistent_pct:.1f}%)")
            if len(data) < 1000:
                print(f"   • Datos insuficientes ({len(data)} barras)")
            if gap_stats['real_data_rate'] < 60:
                print(f"   • Pocos datos reales ({gap_stats['real_data_rate']:.1f}%)")
        
        print(f"{'='*60}")
        
        return backtest_ready
        
    except Exception as e:
        print(f"❌ Error en validación: {e}")
        import traceback
        traceback.print_exc()
        return False

def compare_gap_filling_methods(symbol: str = "AAPL"):
    """
    🆕 V3.2: Comparar diferentes métodos de gap filling
    
    Demuestra la diferencia entre:
    - Forward fill (V3.1 - MALO)
    - Real data (V3.2 - BUENO)
    """
    print(f"🔬 COMPARACIÓN MÉTODOS GAP FILLING - {symbol}")
    print("=" * 60)
    
    try:
        indicators = TechnicalIndicators()
        
        # Obtener datos con método actual (V3.2)
        print("1️⃣ Método V3.2 (Real Data)...")
        data_v32 = indicators.get_market_data(symbol, period='15m', days=7)
        
        # Analizar barras flat
        flat_v32 = data_v32[data_v32['High'] == data_v32['Low']]
        flat_pct_v32 = (len(flat_v32) / len(data_v32)) * 100
        
        print(f"   Total barras: {len(data_v32)}")
        print(f"   Barras flat (H=L): {len(flat_v32)} ({flat_pct_v32:.1f}%)")
        
        # Gap stats
        gap_stats = indicators.get_gap_statistics()
        print(f"   Gaps con datos REALES: {gap_stats['gaps_with_real_data']}")
        print(f"   Gaps worst-case: {gap_stats['gaps_worst_case']}")
        
        print(f"\n📊 ANÁLISIS:")
        print(f"   Con V3.2 (Real Data):")
        print(f"   • {flat_pct_v32:.1f}% barras flat")
        print(f"   • {gap_stats['real_data_rate']:.1f}% datos reales en gaps")
        print(f"   • ✅ Stops/targets verificables en {100-flat_pct_v32:.1f}% casos")
        
        if flat_pct_v32 < 10:
            print(f"\n✅ V3.2 FUNCIONA CORRECTAMENTE")
            print(f"   Los gaps tienen High/Low reales para verificar stops")
        else:
            print(f"\n⚠️ Revisar configuración - muchas barras flat")
        
        return True
        
    except Exception as e:
        print(f"❌ Error en comparación: {e}")
        return False

if __name__ == "__main__":
    """Punto de entrada para testing"""
    print("🚀 SISTEMA DE INDICADORES TÉCNICOS V3.2 - REAL DATA GAP FILLING")
    print("=" * 70)
    
    import sys
    
    # Menú interactivo
    print("\n📋 OPCIONES DE TEST:")
    print("1. Test Real Data Gap Filling (SPY)")
    print("2. Test indicador único (SPY)")
    print("3. Test múltiples símbolos")
    print("4. Validar calidad para backtesting")
    print("5. Comparar métodos de gap filling")
    print("6. Test completo (todas las opciones)")
    print("0. Salir")
    
    try:
        choice = input("\n👉 Elige una opción (0-6): ").strip()
        
        if choice == '0':
            print("👋 ¡Hasta pronto!")
            sys.exit(0)
        
        elif choice == '1':
            print("\n" + "="*70)
            test_real_data_gap_filling("SPY")
        
        elif choice == '2':
            print("\n" + "="*70)
            test_single_indicator("SPY")
        
        elif choice == '3':
            print("\n" + "="*70)
            test_multiple_symbols()
        
        elif choice == '4':
            print("\n" + "="*70)
            symbol = input("Símbolo a validar (default: SPY): ").strip() or "SPY"
            days = input("Días de historial (default: 30): ").strip()
            days = int(days) if days else 30
            validate_backtesting_data_quality(symbol, days)
        
        elif choice == '5':
            print("\n" + "="*70)
            symbol = input("Símbolo para comparar (default: AAPL): ").strip() or "AAPL"
            compare_gap_filling_methods(symbol)
        
        elif choice == '6':
            print("\n🔬 EJECUTANDO SUITE COMPLETA DE TESTS...")
            
            print("\n" + "="*70)
            print("TEST 1: Real Data Gap Filling")
            print("="*70)
            test_real_data_gap_filling("SPY")
            
            print("\n" + "="*70)
            print("TEST 2: Indicador Único")
            print("="*70)
            test_single_indicator("SPY")
            
            print("\n" + "="*70)
            print("TEST 3: Múltiples Símbolos")
            print("="*70)
            test_multiple_symbols()
            
            print("\n" + "="*70)
            print("TEST 4: Validación Backtesting")
            print("="*70)
            validate_backtesting_data_quality("SPY", 30)
            
            print("\n" + "="*70)
            print("TEST 5: Comparación Métodos")
            print("="*70)
            compare_gap_filling_methods("AAPL")
            
            print("\n✅ SUITE COMPLETA DE TESTS FINALIZADA")
        
        else:
            print("❌ Opción no válida")
    
    except KeyboardInterrupt:
        print("\n\n👋 Test interrumpido por el usuario")
        sys.exit(0)
    
    except Exception as e:
        print(f"\n❌ Error en test: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    print("\n🏁 Tests V3.2 completados!")