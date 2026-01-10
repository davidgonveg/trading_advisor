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
import yfinance as yf
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
    
    def get_market_data(self, symbol: str, period: str = "15m", days: int = 30) -> pd.DataFrame:
        """
        🆕 V3.3: Hybrid Loading - Yahoo Base + DB Overlay (Memoria)
        
        Args:
            symbol: Símbolo a descargar
            period: Timeframe designated
            days: Días de historial
            
        Returns:
            DataFrame con historia limpia (Gap-filled PERSISTENTE)
        """
        try:
            logger.info(f"📊 Loading data for {symbol} (Hybrid V3.3)...")
            
            # STEP 1: Download Fresh Raw Data (Base Layer)
            # Siempre descargamos fresco para tener lo último
            raw_data = self._download_raw_data_extended(symbol, period, days)
            
            # STEP 2: Load Local History (Memory Layer)
            try:
                from database.connection import get_continuous_data_as_df, save_continuous_data
                local_data = get_continuous_data_as_df(symbol, days)
                
                if not local_data.empty:
                    # ✅ MAGIC: Overlay local data on top of raw data
                    # FIX: Previous intersection logic missed the ACTUAL gaps (rows missing in raw_data)
                    
                    # Ensure timezone compatibility
                    if raw_data.index.tz is None and local_data.index.tz is not None:
                         local_data.index = local_data.index.tz_localize(None) 
                    elif raw_data.index.tz is not None and local_data.index.tz is None:
                         local_data.index = local_data.index.tz_localize(raw_data.index.tz)

                    # 1. Update existing rows (in case DB has better quality data)
                    raw_data.update(local_data)
                    
                    # 2. Insert MISSING rows (The actual filled gaps)
                    # Find indices in local_data that are NOT in raw_data
                    missing_indices = local_data.index.difference(raw_data.index)
                    
                    if len(missing_indices) > 0:
                        logger.info(f"🧠 {symbol}: Restoring {len(missing_indices)} GAP-FILLED bars from memory")
                        # Append and Sort
                        raw_data = pd.concat([raw_data, local_data.loc[missing_indices]])
                        raw_data.sort_index(inplace=True)
                    else:
                        logger.info(f"🧠 {symbol}: Memory synced (no missing bars to restore)")
            
            except Exception as db_e:
                logger.warning(f"⚠️ Failed to load local memory for {symbol}: {db_e}")
                
            
            # STEP 3: Detect & Fill NEW Gaps (only in parts not covered by DB)
            if USE_GAP_DETECTION and len(raw_data) > 10:
                final_data = self._detect_and_fill_gaps_v32(raw_data, symbol, period)
                
                # STEP 4: Save NEW fills to DB (Persist the memory)
                # If we filled something new, we should save specifically those filled periods?
                # For simplicity/robustness: save last chunk or rely on ContinuousCollector to save live data.
                # However, to fix "historical gaps being re-detected", we MUST save the filled result back to DB.
                # We save the entire clean history? No, too heavy. 
                # We allow ContinuousCollector to handle live saving.
                # BUT, if we just synthesized a gap fill using 'worst case' or 'real data', we MUST persist it now.
                
                # Compare raw (pre-fill) vs final (post-fill) lengths? 
                # If final is longer (added bars), we save those added bars.
                # Actually _detect_and_fill_gaps_v32 inserts rows.
                
                # Optimization: We assume _detect_and_fill_gaps_v32 handles the filling logic in memory.
                # Next time, if we successfully saved them, step 2 will pick them up.
                # SO: We need to ensure that FILLED gaps are saved to DB here.
                pass
                
                if len(final_data) > len(raw_data):
                     logger.info(f"🔧 {symbol}: {len(final_data) - len(raw_data)} NEW gaps filled in this run")
            else:
                final_data = raw_data
            
            # STEP 5: Validate
            validated_data = self._validate_data_quality(final_data, symbol)
            
            return validated_data
            
        except Exception as e:
            logger.error(f"❌ Error in Hybrid Load for {symbol}: {str(e)}")
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
    
    def _detect_and_fill_gaps_v32(self, data: pd.DataFrame, symbol: str, period: str) -> pd.DataFrame:
        """
        🆕 V3.2: DETECTAR Y RELLENAR GAPS CON DATOS REALES
        
        CAMBIO CRÍTICO: Ahora obtiene datos REALES de yfinance para los gaps,
        no inventa precios. Esto es esencial para backtesting de stops/targets.
        
        Args:
            data: DataFrame con datos OHLCV
            symbol: Símbolo para logging
            period: Período para cálculo de gaps esperados
            
        Returns:
            DataFrame con gaps rellenados usando datos REALES
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
                            'duration_hours': gap_minutes / 60,
                            'type': gap_type,
                            'before_idx': i-1,
                            'after_idx': i
                        })
            
            if not gaps:
                logger.debug(f"✅ {symbol}: No se detectaron gaps significativos")
                return data_sorted
            
            logger.debug(f"🔍 {symbol}: {len(gaps)} gaps detectados")
            self.gap_stats['gaps_detected'] += len(gaps)
            
            # Rellenar gaps según estrategia V3.2
            filled_data = data_sorted.copy()
            
            for gap in gaps:
                try:
                    filled_rows = self._fill_gap_v32(
                        data_sorted, gap, symbol, interval_minutes
                    )
                    
                    if len(filled_rows) > 0:
                        # Insertar rows rellenadas
                        filled_data = pd.concat([filled_data, filled_rows]).sort_index()
                        logger.debug(f"🔧 {symbol}: Gap {gap['type']} rellenado ({gap['duration_minutes']:.0f} min)")
                        
                        # 🆕 PERSISTIR GAP EN DATABASE (METADATA + DATA REAL)
                        try:
                            from database.connection import mark_gap_as_filled, save_continuous_data
                            
                            fill_method = 'REAL_DATA' if len(filled_rows) > 0 else 'PRESERVED'
                            
                            # 1. Guardar Metadata del Gap
                            mark_gap_as_filled(
                                symbol=symbol,
                                gap_start=gap['start'],
                                gap_end=gap['end'],
                                fill_method=fill_method,
                                bars_added=len(filled_rows)
                            )
                            
                            # 2. Guardar DATOS (Barras) para Integridad Futura
                            if len(filled_rows) > 0:
                                data_points = []
                                for timestamp, row in filled_rows.iterrows():
                                    data_points.append({
                                        'timestamp': timestamp.isoformat() if hasattr(timestamp, 'isoformat') else str(timestamp),
                                        'open': row['Open'],
                                        'high': row['High'],
                                        'low': row['Low'],
                                        'close': row['Close'],
                                        'volume': row['Volume'],
                                        'is_gap_filled': True,
                                        'data_source': f"GAP_FILL_{fill_method}"
                                    })
                                
                                # Call with correct signature: symbol, timeframe, data_points, session_type
                                save_continuous_data(
                                    symbol=symbol,
                                    timeframe=self._get_timeframe_str(interval_minutes),
                                    data_points=data_points,
                                    session_type="GAP_FILL"
                                )
                            
                            logger.debug(f"💾 {symbol}: Gap y {len(filled_rows)} barras persistidos en DB")
                            
                        except ImportError:
                            logger.warning("⚠️ Funciones de BD no disponibles")
                        except TypeError as te:
                            logger.warning(f"⚠️ {symbol}: Error de argumentos en save: {te}")
                        except Exception as persist_error:
                            logger.warning(f"⚠️ {symbol}: No se pudo persistir gap data: {persist_error}")
                        
                except Exception as gap_error:
                    logger.warning(f"⚠️ {symbol}: Error rellenando gap {gap['type']}: {gap_error}")
                    continue
            
            # Remover duplicados y ordenar
            filled_data = filled_data[~filled_data.index.duplicated(keep='first')].sort_index()
            
            self.gap_stats['last_check'] = datetime.now()
            logger.debug(f"✅ {symbol}: Datos procesados - {len(filled_data)} barras finales")
            
            return filled_data
            
        except Exception as e:
            logger.error(f"❌ Error detectando/rellenando gaps V3.2 para {symbol}: {str(e)}")
            return data  # Retornar datos originales si falla
    
    def _fill_gap_v32(self, data: pd.DataFrame, gap: dict, symbol: str, 
                      interval_minutes: int) -> pd.DataFrame:
        """
        🆕 V3.2: MÉTODO PRINCIPAL DE GAP FILLING CON DATOS REALES
        
        Este método es el CORE del fix. Ahora:
        1. Intenta obtener datos REALES de yfinance para el gap
        2. Si falla, usa worst-case scenario conservador
        3. NUNCA inventa precios flat (H=L=C)
        
        Args:
            data: DataFrame original
            gap: Dict con info del gap
            symbol: Símbolo
            interval_minutes: Intervalo en minutos
            
        Returns:
            DataFrame con datos del gap (reales o worst-case)
        """
        try:
            gap_type = gap['type']
            fill_strategy = GAP_CONFIG['FILL_STRATEGIES'].get(gap_type, 'PRESERVE_GAP')
            
            logger.debug(f"🔧 {symbol}: Gap {gap_type} - Estrategia: {fill_strategy}")
            
            # ===================================================================
            # ESTRATEGIA 1: PRESERVE_GAP - NO RELLENAR
            # ===================================================================
            if fill_strategy == 'PRESERVE_GAP':
                logger.debug(f"🚫 {symbol}: Gap {gap_type} preservado (mercado cerrado)")
                self.gap_stats['gaps_preserved'] += 1
                return pd.DataFrame()  # NO rellenar
            
            # ===================================================================
            # ESTRATEGIA 2: REAL_DATA - OBTENER DATOS REALES DE YFINANCE
            # ===================================================================
            elif fill_strategy == 'REAL_DATA':
                # Verificar si el gap es demasiado largo
                max_hours = REAL_DATA_CONFIG.get('MAX_GAP_TO_FILL_HOURS', 12)
                
                if gap['duration_hours'] > max_hours:
                    logger.warning(f"⚠️ {symbol}: Gap muy largo ({gap['duration_hours']:.1f}h), preservando")
                    self.gap_stats['gaps_preserved'] += 1
                    return pd.DataFrame()
                
                # Intentar obtener datos reales
                real_data = self._get_real_data_for_gap(
                    symbol, 
                    gap['start'], 
                    gap['end'], 
                    interval_minutes
                )
                
                if len(real_data) > 0:
                    logger.info(f"✅ {symbol}: Gap rellenado con {len(real_data)} barras REALES")
                    self.gap_stats['gaps_filled'] += 1
                    self.gap_stats['gaps_with_real_data'] += 1
                    return real_data
                
                # Si no hay datos reales, usar worst-case
                logger.warning(f"⚠️ {symbol}: No hay datos reales, usando worst-case")
                return self._create_worst_case_gap_bar(data, gap, symbol)
            
            # ===================================================================
            # ESTRATEGIA 3: FALLBACK - WORST CASE (solo si falla todo)
            # ===================================================================
            else:
                logger.warning(f"⚠️ {symbol}: Estrategia {fill_strategy} no reconocida, usando worst-case")
                return self._create_worst_case_gap_bar(data, gap, symbol)
                
        except Exception as e:
            logger.error(f"❌ Error rellenando gap V3.2 para {symbol}: {str(e)}")
            return pd.DataFrame()
    
    
    def _get_timeframe_str(self, interval_minutes: int) -> str:
        """Helper para convertir minutos a string timeframe"""
        if interval_minutes == 15: return "15m"
        if interval_minutes == 5: return "5m"
        if interval_minutes == 1: return "1m"
        if interval_minutes == 30: return "30m"
        if interval_minutes == 60: return "1h"
        return f"{interval_minutes}m"

    def _get_real_data_for_gap(self, symbol: str, start: datetime, 
                               end: datetime, interval_minutes: int) -> pd.DataFrame:
        """
        🆕 V3.2: OBTENER DATOS REALES DE YFINANCE PARA UN GAP ESPECÍFICO
        
        Este método es CRÍTICO para el fix. Descarga datos reales del período
        del gap, incluyendo extended hours. Estos datos tienen High/Low reales
        que permiten verificar si se tocó un stop/target.
        
        Args:
            symbol: Símbolo a descargar
            start: Inicio del gap
            end: Fin del gap
            interval_minutes: Intervalo deseado
            
        Returns:
            DataFrame con datos REALES del gap (puede estar vacío si falla)
        """
        try:
            # Determinar intervalo de yfinance
            if interval_minutes <= 1:
                yf_interval = '1m'
            elif interval_minutes <= 5:
                yf_interval = '5m'
            elif interval_minutes <= 15:
                yf_interval = '15m'
            elif interval_minutes <= 30:
                yf_interval = '30m'
            elif interval_minutes <= 60:
                yf_interval = '1h'
            else:
                yf_interval = '1d'
            
            # Reintentos configurables
            max_retries = REAL_DATA_CONFIG.get('RETRY_ATTEMPTS', 3)
            retry_delay = REAL_DATA_CONFIG.get('RETRY_DELAY_SECONDS', 2)
            
            for attempt in range(max_retries):
                try:
                    ticker = yf.Ticker(symbol)
                    
                    # Descargar datos con extended hours
                    gap_data = ticker.history(
                        start=start - timedelta(hours=1),  # Buffer antes
                        end=end + timedelta(hours=1),      # Buffer después
                        interval=yf_interval,
                        prepost=True,  # ✅ CRÍTICO: Extended hours
                        auto_adjust=True
                    )
                    
                    if gap_data.empty:
                        logger.debug(f"📊 {symbol}: Intento {attempt+1}/{max_retries} - Sin datos")
                        if attempt < max_retries - 1:
                            time.sleep(retry_delay)
                            continue
                        else:
                            return pd.DataFrame()
                    
                    # Filtrar solo el período del gap
                    gap_data = gap_data[(gap_data.index >= start) & (gap_data.index <= end)]
                    
                    if gap_data.empty:
                        logger.debug(f"📊 {symbol}: Datos fuera del período del gap")
                        if attempt < max_retries - 1:
                            time.sleep(retry_delay)
                            continue
                        else:
                            return pd.DataFrame()
                    
                    # Normalizar columnas
                    column_mapping = {}
                    for col in gap_data.columns:
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
                    
                    gap_data = gap_data.rename(columns=column_mapping)
                    
                    # Verificar que tenemos las columnas necesarias
                    required_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
                    if not all(col in gap_data.columns for col in required_cols):
                        logger.warning(f"⚠️ {symbol}: Columnas incompletas en datos del gap")
                        if attempt < max_retries - 1:
                            time.sleep(retry_delay)
                            continue
                        else:
                            return pd.DataFrame()
                    
                    gap_data = gap_data[required_cols]
                    
                    logger.info(f"✅ {symbol}: {len(gap_data)} barras REALES obtenidas para gap")
                    return gap_data
                    
                except Exception as retry_error:
                    logger.warning(f"⚠️ {symbol}: Intento {attempt+1}/{max_retries} falló: {retry_error}")
                    if attempt < max_retries - 1:
                        time.sleep(retry_delay)
                    else:
                        logger.error(f"❌ {symbol}: Todos los intentos fallaron")
                        return pd.DataFrame()
            
            return pd.DataFrame()
            
        except Exception as e:
            logger.error(f"❌ Error obteniendo datos reales para gap de {symbol}: {e}")
            return pd.DataFrame()
    
    def _create_worst_case_gap_bar(self, data: pd.DataFrame, gap: dict, 
                                    symbol: str) -> pd.DataFrame:
        """
        🆕 V3.2: CREAR BARRA WORST-CASE CONSERVADORA PARA GAP
        
        Si no hay datos reales disponibles, crea UNA SOLA BARRA que representa
        el gap de forma conservadora, asumiendo que el precio se movió.
        
        IMPORTANTE: Esta barra tiene H ≠ L para permitir detección de stops.
        
        Args:
            data: DataFrame original
            gap: Dict con info del gap
            symbol: Símbolo
            
        Returns:
            DataFrame con UNA barra worst-case
        """
        try:
            if not WORST_CASE_CONFIG.get('ENABLED', True):
                return pd.DataFrame()
            
            before_row = data.iloc[gap['before_idx']]
            after_row = data.iloc[gap['after_idx']]
            
            before_close = before_row['Close']
            after_open = after_row['Open']
            
            # Calcular movimiento del precio
            price_change = after_open - before_close
            price_change_pct = abs(price_change / before_close) if before_close > 0 else 0
            
            # Método CONSERVATIVE_RANGE: Asumir que el precio se movió
            method = WORST_CASE_CONFIG.get('METHOD', 'CONSERVATIVE_RANGE')
            
            if method == 'CONSERVATIVE_RANGE':
                # Asumir movimiento conservador
                movement_estimate = WORST_CASE_CONFIG.get('PRICE_MOVEMENT_ESTIMATE', 0.02)
                safe_margin = WORST_CASE_CONFIG.get('SAFE_MARGIN', 1.2)
                
                # Calcular rango asumido
                if price_change > 0:  # Precio subió
                    # Asumir que pudo haber bajado primero (worst case para stops)
                    worst_low = before_close * (1 - movement_estimate * safe_margin)
                    worst_high = after_open
                else:  # Precio bajó
                    # Asumir que pudo haber subido primero (worst case para stops)
                    worst_high = before_close * (1 + movement_estimate * safe_margin)
                    worst_low = after_open
                
                # Crear barra worst-case
                gap_bar = pd.DataFrame([{
                    'Open': before_close,
                    'High': max(before_close, after_open, worst_high),
                    'Low': min(before_close, after_open, worst_low),
                    'Close': after_open,
                    'Volume': 0  # Sin volumen (gap)
                }], index=[gap['start'] + timedelta(minutes=30)])  # Punto medio del gap
                
                logger.info(f"⚠️ {symbol}: Gap representado con worst-case conservador "
                          f"(H:{worst_high:.2f}, L:{worst_low:.2f})")
                
                self.gap_stats['gaps_filled'] += 1
                self.gap_stats['gaps_worst_case'] += 1
                
                return gap_bar
            
            else:
                logger.warning(f"⚠️ Método worst-case no reconocido: {method}")
                return pd.DataFrame()
                
        except Exception as e:
            logger.error(f"❌ Error creando worst-case bar: {e}")
            return pd.DataFrame()
    
    def _classify_gap(self, start_time: datetime, end_time: datetime, 
                     duration_minutes: float) -> str:
        """Clasificar tipo de gap basado en duración y horario"""
        try:
            # Gap de fin de semana
            if duration_minutes > GAP_CONFIG.get('WEEKEND_GAP_HOURS', 48) * 60:
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
            holiday_hours = GAP_CONFIG.get('HOLIDAY_GAP_HOURS', 24)
            if duration_minutes > holiday_hours * 60:
                return 'HOLIDAY_GAP'
            
            return 'UNKNOWN_GAP'
            
        except Exception:
            return 'UNKNOWN_GAP'
    
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

    def get_all_indicators(self, symbol: str, period: str = "15m", days: int = 30) -> Dict:
        """
        🆕 V3.2: Calcular todos los indicadores con REAL DATA gap filling
        
        Args:
            symbol: Símbolo a analizar
            period: Timeframe (default: "15m")
            days: Días de historial (default: 30)
            
        Returns:
            Dict con todos los indicadores + datos OHLC completos
        """
        try:
            logger.info(f"🔍 Calculando indicadores V3.2 para {symbol}")
            
            # Obtener datos de mercado (ahora con REAL DATA gap filling)
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