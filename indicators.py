#!/usr/bin/env python3
"""
📊 SISTEMA DE INDICADORES TÉCNICOS V3.1 - EXTENDED HOURS + GAP DETECTION
========================================================================

Este módulo contiene todos los indicadores técnicos utilizados para
detectar señales de trading de alta calidad.

🆕 V3.1 NUEVAS FUNCIONALIDADES:
- Extended Hours automático (pre/post/overnight)
- Gap detection y auto-filling inteligente
- Datos continuos para backtesting robusto
- Wrapper transparente (backward compatible)

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
from typing import Dict, Tuple, Optional, Union, List
from datetime import datetime, timedelta
import warnings
import pytz

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
            'SMALL_GAP': 'INTERPOLATE',
            'OVERNIGHT_GAP': 'FORWARD_FILL',
            'WEEKEND_GAP': 'FORWARD_FILL'
        }
    })
    
    logger = logging.getLogger(__name__)
    logger.info("✅ Extended Hours V3.1 configurado desde config.py")
    
except ImportError:
    # Fallback a configuración básica
    USE_EXTENDED_HOURS = True
    USE_GAP_DETECTION = True
    FORCE_PREPOST = True
    GAP_CONFIG = {
        'MIN_GAP_MINUTES': 60,
        'OVERNIGHT_GAP_HOURS': [20, 4],
        'FILL_STRATEGIES': {
            'SMALL_GAP': 'INTERPOLATE',
            'OVERNIGHT_GAP': 'FORWARD_FILL',
            'WEEKEND_GAP': 'FORWARD_FILL'
        }
    }
    logger = logging.getLogger(__name__)
    logger.warning("⚠️ Config no disponible, usando configuración básica extended hours")

# Configurar logging
logging.basicConfig(level=logging.INFO)

# Suprimir warnings de yfinance
warnings.filterwarnings('ignore', category=FutureWarning)

class TechnicalIndicators:
    """
    Clase principal para calcular todos los indicadores técnicos con soporte Extended Hours
    """
    
    def __init__(self):
        """Inicializar la clase de indicadores"""
        self.last_update = {}  # Cache para evitar recálculos innecesarios
        self.gap_stats = {'gaps_detected': 0, 'gaps_filled': 0, 'last_check': None}
        
        logger.info("🔍 TechnicalIndicators V3.1 inicializado")
        logger.info(f"🕐 Extended Hours: {'✅ Habilitado' if USE_EXTENDED_HOURS else '❌ Deshabilitado'}")
        logger.info(f"🔧 Gap Detection: {'✅ Habilitado' if USE_GAP_DETECTION else '❌ Deshabilitado'}")
    
    def get_market_data(self, symbol: str, period: str = "15m", days: int = 30) -> pd.DataFrame:
        """
        🆕 WRAPPER MEJORADO: Descargar datos con Extended Hours + Gap Detection
        
        Args:
            symbol: Símbolo a descargar (ej: "AAPL")
            period: Timeframe (1m, 5m, 15m, 30m, 1h, 1d)
            days: Días de historial a descargar
            
        Returns:
            DataFrame con OHLCV data sin gaps
        """
        try:
            logger.info(f"📊 Descargando datos V3.1 para {symbol} - {period} - {days} días")
            
            # STEP 1: Descargar datos raw con extended hours
            raw_data = self._download_raw_data_extended(symbol, period, days)
            
            # STEP 2: Gap detection y filling (si está habilitado)
            if USE_GAP_DETECTION and len(raw_data) > 10:
                processed_data = self._detect_and_fill_gaps(raw_data, symbol, period)
                if len(processed_data) > len(raw_data):
                    logger.info(f"🔧 {symbol}: {len(processed_data) - len(raw_data)} gaps rellenados")
            else:
                processed_data = raw_data
            
            # STEP 3: Validación final
            validated_data = self._validate_data_quality(processed_data, symbol)
            
            logger.info(f"✅ {symbol}: {len(validated_data)} barras finales (extended hours incluido)")
            return validated_data
            
        except Exception as e:
            logger.error(f"❌ Error en get_market_data V3.1 para {symbol}: {str(e)}")
            # Fallback a método original si falla extended
            return self._get_market_data_fallback(symbol, period, days)
    
    def _download_raw_data_extended(self, symbol: str, period: str, days: int) -> pd.DataFrame:
        """Descargar datos raw con extended hours forzado"""
        try:
            # Calcular fecha de inicio
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            
            # Descargar datos con extended hours FORZADO
            ticker = yf.Ticker(symbol)
            data = ticker.history(
                start=start_date,
                end=end_date,
                interval=period,
                auto_adjust=True,
                prepost=FORCE_PREPOST  # ✅ CRÍTICO: Forzar extended hours
            )
            
            if data.empty:
                raise ValueError(f"No se pudieron obtener datos para {symbol}")
            
            # Limpiar y procesar datos
            data = data.dropna()
            
            # Mapear columnas (mantener lógica original)
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
            
            data = data.rename(columns=column_mapping)
            
            # Verificar columnas requeridas
            required_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
            missing_cols = [col for col in required_cols if col not in data.columns]
            
            if missing_cols:
                raise ValueError(f"Columnas faltantes: {missing_cols}")
            
            data = data[required_cols]
            
            logger.debug(f"📊 {symbol}: Datos raw descargados - {len(data)} barras con extended hours")
            return data
            
        except Exception as e:
            logger.error(f"❌ Error descargando datos extended para {symbol}: {str(e)}")
            raise
    
    def _detect_and_fill_gaps(self, data: pd.DataFrame, symbol: str, period: str) -> pd.DataFrame:
        """
        🆕 DETECTAR Y RELLENAR GAPS AUTOMÁTICAMENTE
        
        Args:
            data: DataFrame con datos OHLCV
            symbol: Símbolo para logging
            period: Período para cálculo de gaps esperados
            
        Returns:
            DataFrame con gaps rellenados
        """
        try:
            if len(data) < 5:
                return data
            
            # Calcular intervalo esperado en minutos
            interval_minutes = self._get_interval_minutes(period)
            min_gap_minutes = GAP_CONFIG['MIN_GAP_MINUTES']
            
            # Detectar gaps temporales
            data_sorted = data.sort_index()
            time_diffs = data_sorted.index.to_series().diff()
            
            # Identificar gaps significativos
            gaps = []
            for i, diff in enumerate(time_diffs[1:], 1):
                if pd.notna(diff):
                    gap_minutes = diff.total_seconds() / 60
                    if gap_minutes > min_gap_minutes:
                        gap_start = data_sorted.index[i-1]
                        gap_end = data_sorted.index[i]
                        gap_type = self._classify_gap(gap_start, gap_end, gap_minutes)
                        
                        gaps.append({
                            'start': gap_start,
                            'end': gap_end,
                            'duration_minutes': gap_minutes,
                            'type': gap_type,
                            'before_idx': i-1,
                            'after_idx': i
                        })
            
            if not gaps:
                logger.debug(f"✅ {symbol}: No se detectaron gaps significativos")
                return data_sorted
            
            logger.info(f"🔍 {symbol}: {len(gaps)} gaps detectados")
            self.gap_stats['gaps_detected'] += len(gaps)
            
            # Rellenar gaps según estrategia
            filled_data = data_sorted.copy()
            
            for gap in gaps:
                try:
                    filled_rows = self._fill_gap(
                        data_sorted, gap, symbol, interval_minutes
                    )
                    
                    if len(filled_rows) > 0:
                        # Insertar rows rellenadas
                        filled_data = pd.concat([filled_data, filled_rows]).sort_index()
                        self.gap_stats['gaps_filled'] += 1
                        logger.debug(f"🔧 {symbol}: Gap {gap['type']} rellenado ({gap['duration_minutes']:.0f} min)")
                        
                except Exception as gap_error:
                    logger.warning(f"⚠️ {symbol}: Error rellenando gap {gap['type']}: {gap_error}")
                    continue
            
            # Remover duplicados y ordenar
            filled_data = filled_data[~filled_data.index.duplicated(keep='first')].sort_index()
            
            self.gap_stats['last_check'] = datetime.now()
            logger.debug(f"✅ {symbol}: Datos procesados - {len(filled_data)} barras finales")
            
            return filled_data
            
        except Exception as e:
            logger.error(f"❌ Error detectando/rellenando gaps para {symbol}: {str(e)}")
            return data  # Retornar datos originales si falla
    
    def _classify_gap(self, start_time: datetime, end_time: datetime, duration_minutes: float) -> str:
        """Clasificar tipo de gap basado en duración y horario"""
        try:
            # Gap de fin de semana
            if duration_minutes > 48 * 60:  # > 48 horas
                return 'WEEKEND_GAP'
            
            # Gap overnight (8PM - 4AM)
            start_hour = start_time.hour
            end_hour = end_time.hour
            overnight_hours = GAP_CONFIG['OVERNIGHT_GAP_HOURS']
            
            if (start_hour >= overnight_hours[0] or start_hour <= overnight_hours[1]) and \
               (end_hour >= overnight_hours[0] or end_hour <= overnight_hours[1]):
                return 'OVERNIGHT_GAP'
            
            # Gap pequeño
            if duration_minutes < 4 * 60:  # < 4 horas
                return 'SMALL_GAP'
            
            # Gap durante día laborable (posible festivo)
            return 'HOLIDAY_GAP'
            
        except Exception:
            return 'UNKNOWN_GAP'
    
    def _fill_gap(self, data: pd.DataFrame, gap: dict, symbol: str, interval_minutes: int) -> pd.DataFrame:
        """Rellenar un gap específico según su tipo"""
        try:
            gap_type = gap['type']
            fill_strategy = GAP_CONFIG['FILL_STRATEGIES'].get(gap_type, 'FORWARD_FILL')
            
            before_row = data.iloc[gap['before_idx']]
            after_row = data.iloc[gap['after_idx']]
            
            # Generar timestamps para rellenar
            start_time = gap['start']
            end_time = gap['end']
            
            # Calcular número de intervalos necesarios
            total_minutes = (end_time - start_time).total_seconds() / 60
            num_intervals = max(1, int(total_minutes / interval_minutes) - 1)
            
            # Limitar número de intervalos para evitar exceso de datos
            max_intervals = 200  # máximo ~50 horas de datos de 15min
            if num_intervals > max_intervals:
                num_intervals = max_intervals
            
            if num_intervals <= 0:
                return pd.DataFrame()
            
            # Generar timestamps
            time_range = pd.date_range(
                start=start_time + timedelta(minutes=interval_minutes),
                end=end_time - timedelta(minutes=interval_minutes/2),
                periods=num_intervals
            )
            
            # Crear datos según estrategia
            filled_rows = []
            
            for i, timestamp in enumerate(time_range):
                if fill_strategy == 'FORWARD_FILL':
                    # Usar último precio válido
                    new_row = {
                        'Open': before_row['Close'],
                        'High': before_row['Close'],
                        'Low': before_row['Close'],
                        'Close': before_row['Close'],
                        'Volume': 0  # Sin volumen durante gaps
                    }
                
                elif fill_strategy == 'INTERPOLATE':
                    # Interpolar entre antes y después (solo para gaps pequeños)
                    progress = (i + 1) / (num_intervals + 1)
                    interpolated_price = before_row['Close'] + (after_row['Open'] - before_row['Close']) * progress
                    
                    new_row = {
                        'Open': interpolated_price,
                        'High': interpolated_price,
                        'Low': interpolated_price,
                        'Close': interpolated_price,
                        'Volume': int(before_row['Volume'] * 0.1)  # Volumen reducido
                    }
                
                else:
                    # Default: forward fill
                    new_row = {
                        'Open': before_row['Close'],
                        'High': before_row['Close'],
                        'Low': before_row['Close'],
                        'Close': before_row['Close'],
                        'Volume': 0
                    }
                
                filled_rows.append(new_row)
            
            if filled_rows:
                filled_df = pd.DataFrame(filled_rows, index=time_range)
                return filled_df
            else:
                return pd.DataFrame()
                
        except Exception as e:
            logger.error(f"❌ Error rellenando gap específico: {str(e)}")
            return pd.DataFrame()
    
    def _get_interval_minutes(self, period: str) -> int:
        """Convertir período string a minutos"""
        period_map = {
            '1m': 1, '2m': 2, '5m': 5, '15m': 15, '30m': 30,
            '60m': 60, '90m': 90, '1h': 60, '1d': 1440
        }
        return period_map.get(period, 15)
    
    def _validate_data_quality(self, data: pd.DataFrame, symbol: str) -> pd.DataFrame:
        """Validar calidad de datos finales"""
        try:
            if len(data) == 0:
                raise ValueError(f"DataFrame vacío para {symbol}")
            
            # Verificar precios válidos
            price_cols = ['Open', 'High', 'Low', 'Close']
            for col in price_cols:
                if col in data.columns:
                    invalid_prices = (data[col] <= 0) | data[col].isna()
                    if invalid_prices.any():
                        logger.warning(f"⚠️ {symbol}: {invalid_prices.sum()} precios inválidos en {col}")
                        # Rellenar con forward fill
                        data[col] = data[col].replace(0, np.nan).fillna(method='ffill')
            
            # Verificar consistencia OHLC
            inconsistent = (
                (data['High'] < data['Low']) |
                (data['High'] < data['Open']) |
                (data['High'] < data['Close']) |
                (data['Low'] > data['Open']) |
                (data['Low'] > data['Close'])
            )
            
            if inconsistent.any():
                logger.warning(f"⚠️ {symbol}: {inconsistent.sum()} barras con inconsistencia OHLC")
                # Corregir inconsistencias básicas
                data.loc[inconsistent, 'High'] = data.loc[inconsistent, [
                    'Open', 'High', 'Low', 'Close'
                ]].max(axis=1)
                data.loc[inconsistent, 'Low'] = data.loc[inconsistent, [
                    'Open', 'High', 'Low', 'Close'
                ]].min(axis=1)
            
            # Verificar volumen
            if 'Volume' in data.columns:
                negative_volume = data['Volume'] < 0
                if negative_volume.any():
                    logger.warning(f"⚠️ {symbol}: {negative_volume.sum()} volúmenes negativos corregidos")
                    data.loc[negative_volume, 'Volume'] = 0
            
            logger.debug(f"✅ {symbol}: Validación de calidad completada")
            return data
            
        except Exception as e:
            logger.error(f"❌ Error validando calidad de datos para {symbol}: {str(e)}")
            return data
    
    def _get_market_data_fallback(self, symbol: str, period: str, days: int) -> pd.DataFrame:
        """Método fallback usando lógica original"""
        try:
            logger.warning(f"🔄 {symbol}: Usando método fallback (sin extended hours)")
            
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            
            ticker = yf.Ticker(symbol)
            data = ticker.history(
                start=start_date,
                end=end_date,
                interval=period,
                auto_adjust=True,
                prepost=False  # Sin extended hours en fallback
            )
            
            if data.empty:
                raise ValueError(f"No se pudieron obtener datos para {symbol}")
            
            data = data.dropna()
            
            # Mapear columnas (lógica original)
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
            
            data = data.rename(columns=column_mapping)
            
            required_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
            missing_cols = [col for col in required_cols if col not in data.columns]
            
            if missing_cols:
                raise ValueError(f"Columnas faltantes: {missing_cols}")
            
            data = data[required_cols]
            
            logger.info(f"✅ {symbol}: {len(data)} barras (fallback)")
            return data
            
        except Exception as e:
            logger.error(f"❌ Error en fallback para {symbol}: {str(e)}")
            raise
    
    def get_gap_statistics(self) -> Dict:
        """Obtener estadísticas de gaps detectados y rellenados"""
        return {
            'gaps_detected': self.gap_stats['gaps_detected'],
            'gaps_filled': self.gap_stats['gaps_filled'],
            'last_check': self.gap_stats['last_check'],
            'fill_rate': (
                self.gap_stats['gaps_filled'] / max(1, self.gap_stats['gaps_detected']) * 100
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
            volume = data['Volume'].values.astype(np.float64)
            
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
        🆕 MEJORADO: Calcular todos los indicadores con extended hours
        
        Args:
            symbol: Símbolo a analizar
            period: Timeframe (default: "15m")
            days: Días de historial (default: 30)
            
        Returns:
            Dict con todos los indicadores + datos OHLC completos
        """
        try:
            logger.info(f"🔍 Calculando indicadores V3.1 para {symbol}")
            
            # Obtener datos de mercado (ahora con extended hours + gap filling)
            data = self.get_market_data(symbol, period, days)
            
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
                
                # 🆕 Metadatos extended hours
                'extended_hours_used': USE_EXTENDED_HOURS,
                'gaps_filled': len(data) > (days * 6.5 * 4) if USE_GAP_DETECTION else False  # Estimación
            }
            
            logger.info(f"✅ {symbol}: Indicadores V3.1 calculados exitosamente")
            
            # Guardar en base de datos
            try:
                from database.connection import save_indicators_data
                save_indicators_data(indicators)
            except Exception as db_error:
                logger.warning(f"⚠️ Error guardando indicadores en DB: {db_error}")

            return indicators
            
        except Exception as e:
            logger.error(f"❌ Error calculando indicadores V3.1 para {symbol}: {str(e)}")
            raise
    
    def print_indicators_summary(self, indicators: Dict) -> None:
        """
        🆕 MEJORADO: Imprimir resumen con info extended hours
        
        Args:
            indicators: Dict con todos los indicadores
        """
        try:
            symbol = indicators['symbol']
            price = indicators['current_price']
            
            print(f"\n📊 INDICADORES TÉCNICOS V3.1 - {symbol} (${price:.2f})")
            print("=" * 60)
            
            # 🆕 Info extended hours
            if indicators.get('extended_hours_used', False):
                print(f"🕐 Extended Hours: ✅ ACTIVO")
                if indicators.get('gaps_filled', False):
                    print(f"🔧 Gaps rellenados: ✅ SÍ")
                gap_stats = self.get_gap_statistics()
                if gap_stats['gaps_detected'] > 0:
                    print(f"📊 Gaps stats: {gap_stats['gaps_filled']}/{gap_stats['gaps_detected']} rellenados ({gap_stats['fill_rate']:.1f}%)")
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
# 🧪 FUNCIONES DE TESTING Y DEMO V3.1
# =============================================================================

def test_extended_hours_functionality(symbol: str = "SPY"):
    """
    🆕 Test específico para funcionalidad Extended Hours
    """
    print(f"🧪 TESTING EXTENDED HOURS V3.1 - {symbol}")
    print("=" * 60)
    
    try:
        # Crear instancia
        indicators = TechnicalIndicators()
        
        print("1️⃣ Testeando descarga con extended hours...")
        result = indicators.get_all_indicators(symbol)
        
        print(f"✅ Datos obtenidos: {result['data_points']} barras")
        print(f"🕐 Extended hours usado: {result.get('extended_hours_used', 'N/A')}")
        print(f"🔧 Gaps rellenados: {result.get('gaps_filled', 'N/A')}")
        
        # Mostrar estadísticas de gaps
        gap_stats = indicators.get_gap_statistics()
        print(f"\n📊 ESTADÍSTICAS DE GAPS:")
        print(f"   Detectados: {gap_stats['gaps_detected']}")
        print(f"   Rellenados: {gap_stats['gaps_filled']}")
        print(f"   Tasa éxito: {gap_stats['fill_rate']:.1f}%")
        
        # Imprimir resumen
        indicators.print_indicators_summary(result)
        
        print("✅ Test Extended Hours exitoso!")
        return result
        
    except Exception as e:
        print(f"❌ Error en test extended hours: {str(e)}")
        return None

def test_single_indicator(symbol: str = "SPY"):
    """
    Test de un solo símbolo para verificar funcionamiento
    """
    print(f"🧪 TESTING INDICADORES V3.1 - {symbol}")
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
    
    print("🧪 TESTING MÚLTIPLES SÍMBOLOS V3.1")
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
    
    # Mostrar estadísticas finales
    print(f"\n📊 ESTADÍSTICAS FINALES DE GAPS:")
    gap_stats = indicators.get_gap_statistics()
    print(f"   Total detectados: {gap_stats['gaps_detected']}")
    print(f"   Total rellenados: {gap_stats['gaps_filled']}")
    print(f"   Tasa éxito global: {gap_stats['fill_rate']:.1f}%")
    
    return results

if __name__ == "__main__":
    # Ejecutar tests si se ejecuta directamente
    print("🚀 SISTEMA DE INDICADORES TÉCNICOS V3.1 - EXTENDED HOURS")
    print("=" * 70)
    
    # Test extended hours específico
    print("\n1️⃣ Testing funcionalidad Extended Hours...")
    test_extended_result = test_extended_hours_functionality("SPY")
    
    if test_extended_result:
        print("\n🎯 ¿Quieres probar test básico de indicadores? (y/n)")
        response = input().lower().strip()
        
        if response == 'y':
            test_result = test_single_indicator("SPY")
            
            if test_result:
                print("\n🎯 ¿Quieres probar con múltiples símbolos? (y/n)")
                response2 = input().lower().strip()
                
                if response2 == 'y':
                    test_multiple_symbols()
    
    print("\n🏁 Tests V3.1 completados!")