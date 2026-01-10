#!/usr/bin/env python3
"""
🔍 SISTEMA DE DETECCIÓN DE SEÑALES - TRADING AUTOMATIZADO V2.0
===========================================================

Este módulo es el cerebro del sistema que:
- Combina todos los indicadores técnicos
- Evalúa señales de trading (0-100 puntos)
- Aplica filtros de calidad y tiempo
- Genera alertas con planes de posición

Lógica de Señales:
- LONG: MACD↑ + RSI<40 + VWAP±0.5% + ROC>1.5% + BB_lower + Volume
- SHORT: MACD↓ + RSI>60 + VWAP>1% + ROC<-1.5% + BB_upper + Volume
"""

import logging
import pandas as pd
import numpy as np
from datetime import datetime, time
import pytz
from typing import Dict, List, Tuple, Optional, Union
from dataclasses import dataclass
import warnings

# Importar nuestros módulos
from analysis.indicators import TechnicalIndicators
# from execution.position_calculator import PositionCalculatorV3, PositionPlan
import config


# Configurar logging
logging.basicConfig(level=getattr(logging, config.LOG_LEVEL, 'INFO'))
logger = logging.getLogger(__name__)


# 🆕 V3.0: Import calculador híbrido
# 🆕 V3.0: Import calculador híbrido
try:
    from execution.position_calculator import PositionCalculatorV3, PositionPlan
    USE_V3 = True
    logger.info("🎯 Scanner: Targets adaptativos V3.0 ACTIVADOS")
except ImportError as e:
    USE_V3 = False
    logger.info(f"⚠️ Scanner: V3.0 no disponible ({e}), usando V2.0")
    # Define dummy PositionPlan just in case to avoid NameError if import failed
    @dataclass
    class PositionPlan:
        pass
    

# Suprimir warnings
warnings.filterwarnings('ignore')

@dataclass
class TradingSignal:
    """Clase para representar una señal de trading completa"""
    symbol: str
    timestamp: datetime
    signal_type: str  # 'LONG', 'SHORT', 'NONE'
    signal_strength: int  # 0-100 puntos
    confidence_level: str  # 'LOW', 'MEDIUM', 'HIGH', 'VERY_HIGH'
    
    # Precio y contexto
    current_price: float
    entry_quality: str  # 'NO_TRADE', 'PARTIAL_ENTRY', 'FULL_ENTRY'
    
    # Breakdown de puntuación por indicador
    indicator_scores: Dict[str, int]
    indicator_signals: Dict[str, str]
    
    # Métricas adicionales
    risk_reward_ratio: float = 0.0
    expected_hold_time: str = ""
    market_context: str = ""
    
    # 🆕 NUEVO: Datos para análisis técnico
    market_data: Optional[pd.DataFrame] = None  # Datos OHLCV para targets adaptativos
    position_plan: Optional[PositionPlan] = None

class SignalScanner:
    """
    Scanner principal para detectar señales de trading de alta calidad
    """
    
    def __init__(self):
        """Inicializar el scanner con todos los componentes"""
        self.indicators = TechnicalIndicators()
        # Por esta:
        if USE_V3:
            self.position_calc = PositionCalculatorV3()
        else:
            from execution.position_calculator import PositionCalculatorV3 as PositionCalculatorV2
            self.position_calc = PositionCalculator()
        
        # Configurar zona horaria del mercado (desde config que lee .env)
        self.market_tz = pytz.timezone(config.MARKET_TIMEZONE)
        
        # Cache para evitar recálculos
        self.cache = {}
        self.cache_timeout = 300  # 5 minutos
        
        # Contadores para estadísticas
        self.scan_count = 0
        self.signals_generated = 0
        self.last_scan_time = None
        
        logger.info("🔍 SignalScanner inicializado correctamente")
    
    def is_market_open(self) -> bool:
        """
        Verificar si el mercado está abierto y en horario de trading
        """
        try:
            now = datetime.now(self.market_tz)
            current_time = now.time()
            weekday = now.weekday()
            
            # Verificar día de semana (0=Lunes, 4=Viernes)
            if weekday not in config.ALLOWED_WEEKDAYS:
                return False
            
            # Verificar horarios de sesión permitidos
            sessions = config.TRADING_SESSIONS
            
            morning_start = time.fromisoformat(sessions['MORNING']['START'])
            morning_end = time.fromisoformat(sessions['MORNING']['END'])
            
            afternoon_start = time.fromisoformat(sessions['AFTERNOON']['START'])
            afternoon_end = time.fromisoformat(sessions['AFTERNOON']['END'])
            
            # Verificar si está en alguna sesión permitida
            in_morning = morning_start <= current_time <= morning_end
            in_afternoon = afternoon_start <= current_time <= afternoon_end
            
            return in_morning or in_afternoon
            
        except Exception as e:
            logger.error(f"❌ Error verificando horario de mercado: {e}")
            return True  # Default a True para no bloquear en caso de error
    
    def evaluate_long_signal(self, indicators: Dict) -> Tuple[int, Dict[str, int], Dict[str, str]]:
        """
        Evaluar señal LONG basada en múltiples indicadores
        
        Reglas para LONG (100 puntos máximo):
        - MACD bullish cross/histogram > 0 (20 pts)
        - RSI < 40 zona sobreventa (20 pts)  
        - Precio cerca VWAP ±0.5% (15 pts)
        - ROC > +1.5% momentum alcista (20 pts)
        - Bollinger Bands zona inferior (15 pts)
        - Volume > +50% confirmación (10 pts BONUS)
        
        Returns:
            Tuple[puntuación_total, scores_por_indicador, señales_por_indicador]
        """
        try:
            total_score = 0
            scores = {}
            signals = {}
            
            # 1. MACD Analysis (20 pts max)
            macd_data = indicators.get('macd', {})
            if macd_data.get('bullish_cross', False):
                macd_score = 20  # Cruce alcista = puntuación completa
                macd_signal = "BULLISH_CROSS"
            elif macd_data.get('histogram', 0) > 0:
                macd_score = 15  # Histogram positivo sin cruce
                macd_signal = "BULLISH"
            elif macd_data.get('histogram', 0) > -0.01:
                macd_score = 10  # Casi neutral
                macd_signal = "NEUTRAL"
            else:
                macd_score = 0
                macd_signal = "BEARISH"
            
            scores['MACD'] = macd_score
            signals['MACD'] = macd_signal
            total_score += macd_score
            
            # 2. RSI Analysis (20 pts max)
            rsi_data = indicators.get('rsi', {})
            rsi_value = rsi_data.get('rsi', 50)
            
            if rsi_value < 30:
                rsi_score = 20  # Sobreventa extrema
                rsi_signal = "OVERSOLD_EXTREME"
            elif rsi_value < 40:
                rsi_score = 18  # Sobreventa moderada (objetivo)
                rsi_signal = "OVERSOLD"
            elif rsi_value < 50:
                rsi_score = 10  # Ligeramente bajista
                rsi_signal = "WEAK"
            elif rsi_value < 60:
                rsi_score = 5   # Neutral
                rsi_signal = "NEUTRAL"
            else:
                rsi_score = 0   # Sobrecomprado (malo para LONG)
                rsi_signal = "OVERBOUGHT"
            
            scores['RSI'] = rsi_score
            signals['RSI'] = rsi_signal
            total_score += rsi_score
            
            # 3. VWAP Analysis (15 pts max)
            vwap_data = indicators.get('vwap', {})
            deviation = abs(vwap_data.get('deviation_pct', 0))
            
            if deviation <= 0.5:
                vwap_score = 15  # Muy cerca del VWAP (ideal)
                vwap_signal = "NEAR_VWAP"
            elif deviation <= 1.0:
                vwap_score = 10  # Moderadamente cerca
                vwap_signal = "CLOSE_TO_VWAP"
            elif deviation <= 2.0:
                vwap_score = 5   # Un poco alejado
                vwap_signal = "AWAY_FROM_VWAP"
            else:
                vwap_score = 0   # Muy alejado
                vwap_signal = "FAR_FROM_VWAP"
            
            scores['VWAP'] = vwap_score
            signals['VWAP'] = vwap_signal
            total_score += vwap_score
            
            # 4. ROC/Momentum Analysis (20 pts max)
            roc_data = indicators.get('roc', {})
            roc_value = roc_data.get('roc', 0)
            
            if roc_value > 3.0:
                roc_score = 20  # Momentum muy fuerte
                roc_signal = "VERY_STRONG_BULLISH"
            elif roc_value > 1.5:
                roc_score = 18  # Momentum fuerte (objetivo)
                roc_signal = "STRONG_BULLISH"
            elif roc_value > 0.5:
                roc_score = 10  # Momentum moderado
                roc_signal = "MODERATE_BULLISH"
            elif roc_value > -0.5:
                roc_score = 5   # Neutral
                roc_signal = "NEUTRAL"
            else:
                roc_score = 0   # Momentum bajista
                roc_signal = "BEARISH"
            
            scores['ROC'] = roc_score
            signals['ROC'] = roc_signal
            total_score += roc_score
            
            # 5. Bollinger Bands Analysis (15 pts max)
            bb_data = indicators.get('bollinger', {})
            bb_position = bb_data.get('bb_position', 0.5)
            
            if bb_position <= 0.2:
                bb_score = 15  # Banda inferior (ideal para LONG)
                bb_signal = "LOWER_BAND"
            elif bb_position <= 0.4:
                bb_score = 10  # Zona baja
                bb_signal = "LOWER_ZONE"
            elif bb_position <= 0.6:
                bb_score = 5   # Zona media
                bb_signal = "MIDDLE_ZONE"
            else:
                bb_score = 0   # Zona alta (malo para LONG)
                bb_signal = "UPPER_ZONE"
            
            scores['BOLLINGER'] = bb_score
            signals['BOLLINGER'] = bb_signal
            total_score += bb_score
            
            # 6. Volume Analysis (10 pts BONUS)
            vol_data = indicators.get('volume_osc', {})
            vol_oscillator = vol_data.get('volume_oscillator', 0)
            
            if vol_oscillator > 75:
                vol_score = 10  # Volumen muy alto
                vol_signal = "VERY_HIGH"
            elif vol_oscillator > 50:
                vol_score = 8   # Volumen alto (bueno)
                vol_signal = "HIGH"
            elif vol_oscillator > 25:
                vol_score = 5   # Volumen elevado
                vol_signal = "ELEVATED"
            elif vol_oscillator > 0:
                vol_score = 3   # Volumen normal
                vol_signal = "NORMAL"
            else:
                vol_score = 0   # Volumen bajo
                vol_signal = "LOW"
            
            scores['VOLUME'] = vol_score
            signals['VOLUME'] = vol_signal
            total_score += vol_score
            
            return total_score, scores, signals
            
        except Exception as e:
            logger.error(f"❌ Error evaluando señal LONG: {e}")
            return 0, {}, {}
    
    def evaluate_short_signal(self, indicators: Dict) -> Tuple[int, Dict[str, int], Dict[str, str]]:
        """
        Evaluar señal SHORT basada en múltiples indicadores
        
        Reglas para SHORT (100 puntos máximo):
        - MACD bearish cross/histogram < 0 (20 pts)
        - RSI > 60 zona sobrecompra (20 pts)
        - Precio alejado VWAP >+1.0% (15 pts)
        - ROC < -1.5% momentum bajista (20 pts)
        - Bollinger Bands zona superior (15 pts)
        - Volume > +50% confirmación (10 pts BONUS)
        """
        try:
            total_score = 0
            scores = {}
            signals = {}
            
            # 1. MACD Analysis (20 pts max)
            macd_data = indicators.get('macd', {})
            if macd_data.get('bearish_cross', False):
                macd_score = 20  # Cruce bajista = puntuación completa
                macd_signal = "BEARISH_CROSS"
            elif macd_data.get('histogram', 0) < 0:
                macd_score = 15  # Histogram negativo sin cruce
                macd_signal = "BEARISH"
            elif macd_data.get('histogram', 0) < 0.01:
                macd_score = 10  # Casi neutral
                macd_signal = "NEUTRAL"
            else:
                macd_score = 0
                macd_signal = "BULLISH"
            
            scores['MACD'] = macd_score
            signals['MACD'] = macd_signal
            total_score += macd_score
            
            # 2. RSI Analysis (20 pts max)
            rsi_data = indicators.get('rsi', {})
            rsi_value = rsi_data.get('rsi', 50)
            
            if rsi_value > 70:
                rsi_score = 20  # Sobrecompra extrema
                rsi_signal = "OVERBOUGHT_EXTREME"
            elif rsi_value > 60:
                rsi_score = 18  # Sobrecompra moderada (objetivo)
                rsi_signal = "OVERBOUGHT"
            elif rsi_value > 50:
                rsi_score = 10  # Ligeramente alcista
                rsi_signal = "STRONG"
            elif rsi_value > 40:
                rsi_score = 5   # Neutral
                rsi_signal = "NEUTRAL"
            else:
                rsi_score = 0   # Sobreventa (malo para SHORT)
                rsi_signal = "OVERSOLD"
            
            scores['RSI'] = rsi_score
            signals['RSI'] = rsi_signal
            total_score += rsi_score
            
            # 3. VWAP Analysis (15 pts max) - Para SHORT queremos precio ALEJADO por arriba
            vwap_data = indicators.get('vwap', {})
            deviation_pct = vwap_data.get('deviation_pct', 0)
            
            if deviation_pct > 2.0:
                vwap_score = 15  # Muy por encima del VWAP (ideal para SHORT)
                vwap_signal = "FAR_ABOVE_VWAP"
            elif deviation_pct > 1.0:
                vwap_score = 12  # Moderadamente arriba (objetivo)
                vwap_signal = "ABOVE_VWAP"
            elif deviation_pct > 0.5:
                vwap_score = 8   # Ligeramente arriba
                vwap_signal = "SLIGHTLY_ABOVE"
            elif deviation_pct > -0.5:
                vwap_score = 3   # Cerca del VWAP
                vwap_signal = "NEAR_VWAP"
            else:
                vwap_score = 0   # Por debajo (malo para SHORT)
                vwap_signal = "BELOW_VWAP"
            
            scores['VWAP'] = vwap_score
            signals['VWAP'] = vwap_signal
            total_score += vwap_score
            
            # 4. ROC/Momentum Analysis (20 pts max)
            roc_data = indicators.get('roc', {})
            roc_value = roc_data.get('roc', 0)
            
            if roc_value < -3.0:
                roc_score = 20  # Momentum muy fuerte bajista
                roc_signal = "VERY_STRONG_BEARISH"
            elif roc_value < -1.5:
                roc_score = 18  # Momentum fuerte bajista (objetivo)
                roc_signal = "STRONG_BEARISH"
            elif roc_value < -0.5:
                roc_score = 10  # Momentum moderado bajista
                roc_signal = "MODERATE_BEARISH"
            elif roc_value < 0.5:
                roc_score = 5   # Neutral
                roc_signal = "NEUTRAL"
            else:
                roc_score = 0   # Momentum alcista
                roc_signal = "BULLISH"
            
            scores['ROC'] = roc_score
            signals['ROC'] = roc_signal
            total_score += roc_score
            
            # 5. Bollinger Bands Analysis (15 pts max)
            bb_data = indicators.get('bollinger', {})
            bb_position = bb_data.get('bb_position', 0.5)
            
            if bb_position >= 0.8:
                bb_score = 15  # Banda superior (ideal para SHORT)
                bb_signal = "UPPER_BAND"
            elif bb_position >= 0.6:
                bb_score = 10  # Zona alta
                bb_signal = "UPPER_ZONE"
            elif bb_position >= 0.4:
                bb_score = 5   # Zona media
                bb_signal = "MIDDLE_ZONE"
            else:
                bb_score = 0   # Zona baja (malo para SHORT)
                bb_signal = "LOWER_ZONE"
            
            scores['BOLLINGER'] = bb_score
            signals['BOLLINGER'] = bb_signal
            total_score += bb_score
            
            # 6. Volume Analysis (10 pts BONUS) - Igual que para LONG
            vol_data = indicators.get('volume_osc', {})
            vol_oscillator = vol_data.get('volume_oscillator', 0)
            
            if vol_oscillator > 75:
                vol_score = 10  # Volumen muy alto
                vol_signal = "VERY_HIGH"
            elif vol_oscillator > 50:
                vol_score = 8   # Volumen alto (bueno)
                vol_signal = "HIGH"
            elif vol_oscillator > 25:
                vol_score = 5   # Volumen elevado
                vol_signal = "ELEVATED"
            elif vol_oscillator > 0:
                vol_score = 3   # Volumen normal
                vol_signal = "NORMAL"
            else:
                vol_score = 0   # Volumen bajo
                vol_signal = "LOW"
            
            scores['VOLUME'] = vol_score
            signals['VOLUME'] = vol_signal
            total_score += vol_score
            
            return total_score, scores, signals
            
        except Exception as e:
            logger.error(f"❌ Error evaluando señal SHORT: {e}")
            return 0, {}, {}
    
    def determine_signal_quality(self, score: int, signal_type: str) -> Tuple[str, str]:
        """
        Determinar la calidad de entrada basada en la puntuación
        
        Returns:
            Tuple[entry_quality, confidence_level]
        """
        if score >= config.SIGNAL_THRESHOLDS['FULL_ENTRY']:
            return "FULL_ENTRY", "VERY_HIGH"
        elif score >= config.SIGNAL_THRESHOLDS['PARTIAL_ENTRY']:
            return "PARTIAL_ENTRY", "HIGH"
        elif score >= config.SIGNAL_THRESHOLDS['NO_TRADE']:
            return "PARTIAL_ENTRY", "MEDIUM"
        else:
            return "NO_TRADE", "LOW"
    
    def get_market_context(self, indicators: Dict) -> str:
        """
        Determinar el contexto general del mercado
        """
        try:
            # Analizar múltiples factores
            rsi = indicators.get('rsi', {}).get('rsi', 50)
            vwap_dev = indicators.get('vwap', {}).get('deviation_pct', 0)
            roc = indicators.get('roc', {}).get('roc', 0)
            bb_pos = indicators.get('bollinger', {}).get('bb_position', 0.5)
            vol_osc = indicators.get('volume_osc', {}).get('volume_oscillator', 0)
            
            contexts = []
            
            # Contexto de tendencia
            if roc > 2.0:
                contexts.append("STRONG_UPTREND")
            elif roc > 0.5:
                contexts.append("UPTREND")
            elif roc < -2.0:
                contexts.append("STRONG_DOWNTREND")
            elif roc < -0.5:
                contexts.append("DOWNTREND")
            else:
                contexts.append("SIDEWAYS")
            
            # Contexto de volatilidad
            atr_pct = indicators.get('atr', {}).get('atr_percentage', 1.5)
            if atr_pct > 3.0:
                contexts.append("HIGH_VOLATILITY")
            elif atr_pct < 1.0:
                contexts.append("LOW_VOLATILITY")
            
            # Contexto de volumen
            if vol_osc > 50:
                contexts.append("HIGH_VOLUME")
            elif vol_osc < 0:
                contexts.append("LOW_VOLUME")
            
            # Contexto de posición en rango
            if bb_pos > 0.8:
                contexts.append("RANGE_TOP")
            elif bb_pos < 0.2:
                contexts.append("RANGE_BOTTOM")
            
            return " | ".join(contexts[:3])  # Máximo 3 contextos
            
        except Exception as e:
            logger.error(f"Error determinando contexto: {e}")
            return "UNKNOWN"
    

    def scan_symbol(self, symbol: str) -> Optional[TradingSignal]:
        """
        Escanear un símbolo individual y generar señal si aplica
        
        Args:
            symbol: Símbolo a escanear (ej: "SPY")
            
        Returns:
            TradingSignal si se detecta señal válida, None si no
        """
        try:
            logger.info(f"🔍 Escaneando {symbol}...")
            
            # Obtener todos los indicadores
            indicators = self.indicators.get_all_indicators(
                symbol=symbol,
                period=config.TIMEFRAME,
                days=config.HISTORY_DAYS
            )
            
            current_price = indicators['current_price']
            timestamp = datetime.now(self.market_tz)
            
            # Evaluar señales LONG y SHORT
            long_score, long_scores, long_signals = self.evaluate_long_signal(indicators)
            short_score, short_scores, short_signals = self.evaluate_short_signal(indicators)
            
            # Determinar la mejor señal
            if long_score > short_score and long_score >= config.SIGNAL_THRESHOLDS['NO_TRADE']:
                signal_type = "LONG"
                final_score = long_score
                final_scores = long_scores
                final_signals = long_signals
            elif short_score >= config.SIGNAL_THRESHOLDS['NO_TRADE']:
                signal_type = "SHORT"
                final_score = short_score
                final_scores = short_scores
                final_signals = short_signals
            else:
                # No hay señal válida
                logger.info(f"❌ {symbol}: Sin señal válida (LONG: {long_score}, SHORT: {short_score})")
                return None
            
            # Determinar calidad y confianza
            entry_quality, confidence_level = self.determine_signal_quality(final_score, signal_type)
            
            # Obtener contexto de mercado
            market_context = self.get_market_context(indicators)
            
            # 🔧 FIXED: Calcular plan de posición con market_data parameter
            position_plan = None
            risk_reward = 0.0
            hold_time = ""
            
            if entry_quality != "NO_TRADE":
                try:
                    # ✅ STEP 1: Obtener market_data antes de llamar V3.0
                    market_data = None
                    try:
                        # Obtener datos OHLCV para análisis técnico adaptativo
                        market_data = self.indicators.get_market_data(symbol, period="15m", days=30)
                        logger.debug(f"✅ Market data obtenido para {symbol}: {len(market_data)} registros")
                    except Exception as data_error:
                        logger.warning(f"⚠️ Error obteniendo market data para {symbol}: {data_error}")
                        market_data = None
                    
                    # ✅ STEP 2: Llamar V3.0 con TODOS los parámetros necesarios
                    if USE_V3:
                        position_plan = self.position_calc.calculate_position_plan_v3(
                            symbol=symbol,
                            direction=signal_type,
                            current_price=current_price,
                            signal_strength=final_score,
                            indicators=indicators,
                            market_data=market_data,  # ✅ FIXED: Agregar market_data parameter
                            account_balance=10000     # ✅ FIXED: Agregar account_balance también
                        )
                    else:
                        # Fallback a método V2.0 si V3.0 no está disponible
                        position_plan = self.position_calc.calculate_position_plan(
                            symbol=symbol,
                            direction=signal_type,
                            current_price=current_price,
                            signal_strength=final_score,
                            indicators=indicators
                        )
                    
                    if position_plan:
                        risk_reward = position_plan.max_risk_reward
                        hold_time = position_plan.expected_hold_time
                        logger.debug(f"✅ Plan V3.0 calculado para {symbol}: {position_plan.strategy_type}")
                    
                except Exception as e:
                    logger.error(f"⚠️ Error calculando plan de posición para {symbol}: {e}")
                    # Continuar sin position_plan en caso de error
                    position_plan = None
            
            # Crear señal completa
            signal = TradingSignal(
                symbol=symbol,
                timestamp=timestamp,
                signal_type=signal_type,
                signal_strength=final_score,
                confidence_level=confidence_level,
                current_price=current_price,
                entry_quality=entry_quality,
                indicator_scores=final_scores,
                indicator_signals=final_signals,
                position_plan=position_plan,
                risk_reward_ratio=risk_reward,
                expected_hold_time=hold_time,
                market_context=market_context
            )
            
            logger.info(f"✅ {symbol}: {signal_type} señal detectada - {final_score} pts - {confidence_level}")
            self.signals_generated += 1

            # 🆕 GUARDAR SEÑAL EN BASE DE DATOS
            try:
                from database.connection import save_signal_data
                save_signal_data(signal)
            except Exception as db_error:
                logger.warning(f"⚠️ Error guardando señal en DB: {db_error}")

            return signal
            
        except Exception as e:
            logger.error(f"❌ Error escaneando {symbol}: {e}")
            return None
    
    def scan_multiple_symbols(self, symbols: List[str] = None) -> List[TradingSignal]:
        """
        Escanear múltiples símbolos y retornar todas las señales válidas
        
        Args:
            symbols: Lista de símbolos a escanear (usa config.SYMBOLS por defecto)
            
        Returns:
            Lista de TradingSignal válidas, ordenadas por fuerza de señal
        """
        try:
            if symbols is None:
                symbols = config.SYMBOLS
            
            logger.info(f"🔍 Iniciando escaneo de {len(symbols)} símbolos...")
            self.scan_count += 1
            self.last_scan_time = datetime.now(self.market_tz)
            
            # Verificar horario de mercado
            if not self.is_market_open():
                logger.warning("⚠️ Mercado cerrado - Escaneo fuera de horario")
                if not config.DEVELOPMENT_MODE:
                    return []
            
            signals = []
            
            for symbol in symbols:
                try:
                    signal = self.scan_symbol(symbol)
                    if signal:
                        signals.append(signal)
                        
                except Exception as e:
                    logger.error(f"❌ Error procesando {symbol}: {e}")
                    continue
            
            # Ordenar por fuerza de señal (mayor a menor)
            signals.sort(key=lambda x: x.signal_strength, reverse=True)
            
            logger.info(f"✅ Escaneo completado: {len(signals)} señales detectadas de {len(symbols)} símbolos")
            
            return signals
            
        except Exception as e:
            logger.error(f"❌ Error en escaneo múltiple: {e}")
            return []
    
    def format_signal_summary(self, signal: TradingSignal) -> str:
        """
        Formatear resumen de señal para logging/debug
        """
        try:
            summary = []
            summary.append(f"📊 SEÑAL {signal.signal_type} - {signal.symbol}")
            summary.append("=" * 50)
            summary.append(f"💪 Fuerza: {signal.signal_strength}/100 ({signal.confidence_level})")
            summary.append(f"💰 Precio: ${signal.current_price:.2f}")
            summary.append(f"🎯 Calidad: {signal.entry_quality}")
            summary.append(f"📈 R:R: 1:{signal.risk_reward_ratio:.1f}")
            summary.append(f"⏰ Tiempo: {signal.expected_hold_time}")
            summary.append(f"🌐 Contexto: {signal.market_context}")
            summary.append("")
            
            summary.append("📊 BREAKDOWN POR INDICADOR:")
            for indicator, score in signal.indicator_scores.items():
                signal_desc = signal.indicator_signals.get(indicator, "")
                summary.append(f"  {indicator}: {score} pts - {signal_desc}")
            
            summary.append("=" * 50)
            
            return "\n".join(summary)
            
        except Exception as e:
            logger.error(f"Error formateando resumen: {e}")
            return f"Error generando resumen para {signal.symbol}"
    
    def get_scanner_stats(self) -> Dict:
        """
        Obtener estadísticas del scanner
        """
        return {
            'total_scans': self.scan_count,
            'signals_generated': self.signals_generated,
            'last_scan': self.last_scan_time.isoformat() if self.last_scan_time else None,
            'success_rate': f"{(self.signals_generated / max(self.scan_count * len(config.SYMBOLS), 1)) * 100:.1f}%",
            'market_open': self.is_market_open()
        }


# =============================================================================
# 🧪 FUNCIONES DE TESTING Y DEMO
# =============================================================================

def test_single_symbol_scan(symbol: str = "SPY"):
    """
    Test de escaneo de un solo símbolo
    """
    print(f"🧪 TESTING SCANNER - {symbol}")
    print("=" * 60)
    
    try:
        scanner = SignalScanner()
        signal = scanner.scan_symbol(symbol)
        
        if signal:
            print("✅ SEÑAL DETECTADA!")
            print(scanner.format_signal_summary(signal))
            
            # Mostrar plan de posición si existe
            if signal.position_plan:
                print("\n" + scanner.position_calc.format_position_summary(signal.position_plan))
        else:
            print("❌ No se detectó señal válida")
            
        return signal
        
    except Exception as e:
        print(f"❌ Error en test: {e}")
        return None

def test_multiple_symbols_scan():
    """
    Test de escaneo múltiple con símbolos de prueba
    """
    print("🧪 TESTING SCANNER MÚLTIPLE")
    print("=" * 60)
    
    try:
        scanner = SignalScanner()
        
        # Usar símbolos de test si estamos en modo desarrollo
        test_symbols = config.TEST_SYMBOLS if config.TEST_MODE else config.SYMBOLS[:3]
        
        signals = scanner.scan_multiple_symbols(test_symbols)
        
        print(f"📊 RESULTADOS DEL ESCANEO:")
        print(f"Símbolos escaneados: {len(test_symbols)}")
        print(f"Señales detectadas: {len(signals)}")
        print("")
        
        if signals:
            print("🎯 SEÑALES ENCONTRADAS (ordenadas por fuerza):")
            print("-" * 60)
            
            for i, signal in enumerate(signals, 1):
                print(f"{i}. {signal.symbol} - {signal.signal_type}")
                print(f"   Fuerza: {signal.signal_strength}/100 ({signal.confidence_level})")
                print(f"   Precio: ${signal.current_price:.2f}")
                print(f"   R:R: 1:{signal.risk_reward_ratio:.1f}")
                print(f"   Estrategia: {signal.position_plan.strategy_type if signal.position_plan else 'N/A'}")
                print("")
        else:
            print("📵 No se detectaron señales en este momento")
            print("💡 Esto puede ser normal - el sistema es selectivo")
        
        # Mostrar estadísticas
        stats = scanner.get_scanner_stats()
        print("📈 ESTADÍSTICAS DEL SCANNER:")
        print(f"Mercado abierto: {'✅' if stats['market_open'] else '❌'}")
        print(f"Total escaneos: {stats['total_scans']}")
        print(f"Señales generadas: {stats['signals_generated']}")
        print(f"Tasa de detección: {stats['success_rate']}")
        
        return signals
        
    except Exception as e:
        print(f"❌ Error en test múltiple: {e}")
        return []

def test_signal_evaluation():
    """
    Test específico del sistema de evaluación de señales
    """
    print("🧪 TESTING EVALUACIÓN DE SEÑALES")
    print("=" * 60)
    
    try:
        scanner = SignalScanner()
        
        # Crear datos de ejemplo para testing
        mock_indicators = {
            'macd': {
                'bullish_cross': True,
                'bearish_cross': False,
                'histogram': 0.05
            },
            'rsi': {
                'rsi': 35  # Sobreventa - bueno para LONG
            },
            'vwap': {
                'deviation_pct': 0.3  # Cerca del VWAP - bueno
            },
            'roc': {
                'roc': 2.1  # Momentum alcista fuerte
            },
            'bollinger': {
                'bb_position': 0.15  # Banda inferior - bueno para LONG
            },
            'volume_osc': {
                'volume_oscillator': 65  # Volumen alto
            }
        }
        
        print("📊 DATOS DE EJEMPLO:")
        print("MACD: Cruce alcista ✅")
        print("RSI: 35 (sobreventa) ✅")
        print("VWAP: +0.3% (cerca) ✅")
        print("ROC: +2.1% (momentum fuerte) ✅")
        print("BB: Posición 0.15 (banda inferior) ✅")
        print("Volume: +65% (alto) ✅")
        print("")
        
        # Evaluar señal LONG
        long_score, long_scores, long_signals = scanner.evaluate_long_signal(mock_indicators)
        
        print("🟢 EVALUACIÓN SEÑAL LONG:")
        print(f"Puntuación total: {long_score}/100")
        print("Breakdown:")
        for indicator, score in long_scores.items():
            signal_desc = long_signals.get(indicator, "")
            print(f"  {indicator}: {score} pts - {signal_desc}")
        
        # Determinar calidad
        entry_quality, confidence = scanner.determine_signal_quality(long_score, "LONG")
        print(f"\nCalidad de entrada: {entry_quality}")
        print(f"Nivel de confianza: {confidence}")
        
        # Evaluar señal SHORT para comparar
        short_score, _, _ = scanner.evaluate_short_signal(mock_indicators)
        print(f"\n🔴 SEÑAL SHORT (comparación): {short_score}/100")
        
        print(f"\n✅ Resultado: Señal {entry_quality} para LONG con {long_score} puntos")
        
        return long_score >= config.SIGNAL_THRESHOLDS['NO_TRADE']
        
    except Exception as e:
        print(f"❌ Error en test de evaluación: {e}")
        return False

def test_market_timing():
    """
    Test del sistema de horarios de mercado
    """
    print("🧪 TESTING HORARIOS DE MERCADO")
    print("=" * 60)
    
    try:
        scanner = SignalScanner()
        
        # Estado actual
        is_open = scanner.is_market_open()
        current_time = datetime.now(scanner.market_tz)
        
        print(f"⏰ Hora actual (ET): {current_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        print(f"📅 Día de semana: {current_time.strftime('%A')} (#{current_time.weekday()})")
        print(f"🏛️ Mercado: {'🟢 ABIERTO' if is_open else '🔴 CERRADO'}")
        print("")
        
        # Mostrar sesiones configuradas
        print("📋 SESIONES DE TRADING CONFIGURADAS:")
        sessions = config.TRADING_SESSIONS
        print(f"Mañana: {sessions['MORNING']['START']} - {sessions['MORNING']['END']}")
        print(f"Tarde: {sessions['AFTERNOON']['START']} - {sessions['AFTERNOON']['END']}")
        print("")
        
        # Días permitidos
        allowed_days = [
            "Lunes", "Martes", "Miércoles", "Jueves", "Viernes"
        ]
        print(f"📅 Días permitidos: {', '.join(allowed_days)}")
        
        if config.DEVELOPMENT_MODE:
            print("\n💻 MODO DESARROLLO: Horarios ignorados")
        
        return is_open
        
    except Exception as e:
        print(f"❌ Error en test de horarios: {e}")
        return False

def demo_complete_workflow():
    """
    Demostración completa del workflow del scanner
    """
    print("🚀 DEMOSTRACIÓN COMPLETA DEL SCANNER")
    print("=" * 70)
    
    try:
        # 1. Inicializar scanner
        print("1️⃣ Inicializando scanner...")
        scanner = SignalScanner()
        print("✅ Scanner inicializado")
        print("")
        
        # 2. Verificar horarios
        print("2️⃣ Verificando horarios de mercado...")
        is_open = scanner.is_market_open()
        print(f"   Estado: {'🟢 Abierto' if is_open else '🔴 Cerrado'}")
        print("")
        
        # 3. Escanear símbolos
        print("3️⃣ Escaneando símbolos principales...")
        symbols_to_scan = ["SPY", "QQQ"] if config.TEST_MODE else config.SYMBOLS[:3]
        signals = scanner.scan_multiple_symbols(symbols_to_scan)
        print(f"   Símbolos escaneados: {len(symbols_to_scan)}")
        print(f"   Señales detectadas: {len(signals)}")
        print("")
        
        # 4. Procesar resultados
        print("4️⃣ Procesando resultados...")
        if signals:
            best_signal = signals[0]  # Ya están ordenadas por fuerza
            print(f"   🥇 Mejor señal: {best_signal.symbol} - {best_signal.signal_type}")
            print(f"   💪 Fuerza: {best_signal.signal_strength}/100")
            print(f"   🎯 Calidad: {best_signal.entry_quality}")
            
            # Mostrar detalles de la mejor señal
            print("\n📊 DETALLES DE LA MEJOR SEÑAL:")
            print(scanner.format_signal_summary(best_signal))
            
        else:
            print("   📵 No hay señales válidas en este momento")
            print("   💡 El sistema es muy selectivo - esto es normal")
        
        # 5. Estadísticas finales
        print("\n5️⃣ Estadísticas del scanner:")
        stats = scanner.get_scanner_stats()
        for key, value in stats.items():
            print(f"   {key}: {value}")
        
        print("\n🎯 DEMOSTRACIÓN COMPLETADA")
        print("El scanner está listo para uso en producción!")
        
        return len(signals) > 0
        
    except Exception as e:
        print(f"❌ Error en demostración: {e}")
        return False

if __name__ == "__main__":
    # Menú interactivo para testing
    print("🔍 SISTEMA SCANNER V2.0 - MODO TESTING")
    print("=" * 60)
    print("Selecciona un test:")
    print("1. Test símbolo individual (SPY)")
    print("2. Test escaneo múltiple")
    print("3. Test evaluación de señales")
    print("4. Test horarios de mercado")
    print("5. Demostración completa")
    print("6. Ejecutar todos los tests")
    print("")
    
    try:
        choice = input("Elige una opción (1-6): ").strip()
        print("")
        
        if choice == "1":
            test_single_symbol_scan("SPY")
        elif choice == "2":
            test_multiple_symbols_scan()
        elif choice == "3":
            test_signal_evaluation()
        elif choice == "4":
            test_market_timing()
        elif choice == "5":
            demo_complete_workflow()
        elif choice == "6":
            # Ejecutar todos los tests
            print("🧪 EJECUTANDO TODOS LOS TESTS")
            print("=" * 60)
            
            tests = [
                ("Horarios de mercado", test_market_timing),
                ("Evaluación de señales", test_signal_evaluation),
                ("Símbolo individual", lambda: test_single_symbol_scan("SPY")),
                ("Escaneo múltiple", test_multiple_symbols_scan),
                ("Workflow completo", demo_complete_workflow)
            ]
            
            results = []
            for test_name, test_func in tests:
                print(f"\n🔬 {test_name}...")
                try:
                    result = test_func()
                    results.append((test_name, "✅" if result else "⚠️"))
                    print(f"Resultado: {'✅ PASÓ' if result else '⚠️ COMPLETADO'}")
                except Exception as e:
                    results.append((test_name, "❌"))
                    print(f"Error: {e}")
                
                print("-" * 40)
            
            print("\n📊 RESUMEN DE TESTS:")
            for test_name, status in results:
                print(f"{status} {test_name}")
            
        else:
            print("❌ Opción no válida")
            
    except KeyboardInterrupt:
        print("\n👋 Tests interrumpidos por el usuario")
    except Exception as e:
        print(f"❌ Error ejecutando tests: {e}")
    
    print("\n🏁 Tests completados!")
    print("El módulo scanner.py está listo para integración con telegram_bot.py")