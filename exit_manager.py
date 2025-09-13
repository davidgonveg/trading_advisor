#!/usr/bin/env python3
"""
🚪 EXIT MANAGEMENT SYSTEM - TRADING AUTOMATIZADO V2.1
===================================================

Sistema inteligente que reevalúa posiciones activas y detecta:
- Deterioro severo de condiciones técnicas
- Cambios de momentum que invalidan la tesis original
- Señales de salida anticipada antes del stop loss
- Confluencias técnicas negativas

LÓGICA DE EXIT MANAGEMENT:
- Solo evalúa símbolos con posiciones activas
- Busca deterioro SEVERO (no oscilaciones normales)
- Genera alertas de "EXIT URGENTE" o "EXIT RECOMENDADO"
- Mantiene histórico de decisiones para aprendizaje
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import json
import os

# Importar módulos del sistema
from scanner import TradingSignal, SignalScanner
from indicators import TechnicalIndicators
from position_calculator import PositionPlan
import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ExitUrgency(Enum):
    """Niveles de urgencia para salidas"""
    NO_EXIT = "NO_EXIT"
    EXIT_WATCH = "EXIT_WATCH"           # Vigilar - condiciones se deterioran
    EXIT_RECOMMENDED = "EXIT_RECOMMENDED"  # Salida recomendada - condiciones malas
    EXIT_URGENT = "EXIT_URGENT"         # Salida urgente - condiciones críticas

@dataclass
class ActivePosition:
    """Representa una posición activa en seguimiento"""
    symbol: str
    direction: str  # 'LONG' or 'SHORT'
    entry_signal: TradingSignal
    entry_time: datetime
    entry_price: float
    position_plan: PositionPlan
    
    # Estado de la posición
    current_price: float = 0.0
    unrealized_pnl_pct: float = 0.0
    days_held: int = 0
    
    # Seguimiento de deterioro
    deterioration_count: int = 0  # Veces que ha mostrado deterioro
    last_evaluation: Optional[datetime] = None
    exit_alerts_sent: int = 0

@dataclass
class ExitSignal:
    """Señal de salida con análisis completo"""
    symbol: str
    urgency: ExitUrgency
    exit_score: int  # Puntuación negativa (0-100, 100=salir ya)
    position: ActivePosition
    
    # Razones técnicas específicas
    technical_reasons: List[str]
    momentum_change: float  # % cambio en momentum desde entrada
    trend_reversal: bool
    volume_divergence: bool
    
    # Recomendación
    recommended_action: str
    exit_percentage: int  # % de posición a cerrar
    
    # Timestamp y contexto
    timestamp: datetime
    current_indicators: Dict

class ExitManager:
    """
    Gestor principal de salidas inteligentes
    """
    
    def __init__(self, positions_file: str = "active_positions.json"):
        """Inicializar el exit manager"""
        self.positions_file = positions_file
        self.active_positions: Dict[str, ActivePosition] = {}
        
        # Componentes
        self.scanner = SignalScanner()
        self.indicators = TechnicalIndicators()
        
        # Configuración de deterioro
        self.deterioration_thresholds = {
            'MILD': 60,      # Puntuación 60-69: Deterioro leve
            'MODERATE': 70,  # Puntuación 70-79: Deterioro moderado
            'SEVERE': 80,    # Puntuación 80-89: Deterioro severo
            'CRITICAL': 90   # Puntuación 90+: Deterioro crítico
        }
        
        # Cargar posiciones existentes
        self.load_positions()
        
        logger.info("🚪 Exit Manager inicializado")
        logger.info(f"📊 Posiciones activas cargadas: {len(self.active_positions)}")
    
    def add_position(self, signal: TradingSignal, entry_price: float) -> bool:
        """
        Añadir nueva posición para seguimiento
        
        Args:
            signal: Señal original de entrada
            entry_price: Precio real de entrada
            
        Returns:
            True si se añadió correctamente
        """
        try:
            if not signal.position_plan:
                logger.error(f"❌ {signal.symbol}: Sin plan de posición")
                return False
            
            position = ActivePosition(
                symbol=signal.symbol,
                direction=signal.signal_type,
                entry_signal=signal,
                entry_time=signal.timestamp,
                entry_price=entry_price,
                position_plan=signal.position_plan,
                current_price=entry_price,
                last_evaluation=datetime.now()
            )
            
            self.active_positions[signal.symbol] = position
            self.save_positions()
            
            logger.info(f"✅ {signal.symbol}: Posición añadida para seguimiento")
            logger.info(f"   Dirección: {signal.signal_type}")
            logger.info(f"   Precio entrada: ${entry_price:.2f}")
            logger.info(f"   Estrategia: {signal.position_plan.strategy_type}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error añadiendo posición {signal.symbol}: {e}")
            return False
    
    def remove_position(self, symbol: str, reason: str = "Manual") -> bool:
        """Remover posición del seguimiento"""
        try:
            if symbol in self.active_positions:
                position = self.active_positions[symbol]
                logger.info(f"🚪 {symbol}: Posición removida - {reason}")
                logger.info(f"   Tiempo mantenida: {(datetime.now() - position.entry_time).days} días")
                logger.info(f"   Alertas de exit enviadas: {position.exit_alerts_sent}")
                
                del self.active_positions[symbol]
                self.save_positions()
                return True
            else:
                logger.warning(f"⚠️ {symbol}: No está en seguimiento")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error removiendo posición {symbol}: {e}")
            return False
    
    def evaluate_exit_for_long(self, position: ActivePosition, indicators: Dict) -> Tuple[int, List[str]]:
        """
        Evaluar deterioro para posición LONG
        
        Busca condiciones que invaliden la tesis alcista original:
        - MACD girando bajista con fuerza
        - RSI en sobrecompra extrema (>75) y divergencia
        - Precio alejándose mucho del VWAP (>2%)
        - ROC volviéndose fuertemente negativo
        - Bollinger Bands: precio en zona superior con rechazo
        - Volumen confirmando la distribución
        """
        try:
            deterioration_score = 0
            reasons = []
            
            # 1. MACD - ¿Girando bajista?
            macd_data = indicators.get('macd', {})
            if macd_data.get('bearish_cross', False):
                deterioration_score += 25  # Cruce bajista = deterioro severo
                reasons.append("🔴 MACD: Cruce bajista confirmado")
            elif macd_data.get('histogram', 0) < -0.01:
                deterioration_score += 15  # Histogram muy negativo
                reasons.append("📉 MACD: Histogram fuertemente negativo")
            
            # 2. RSI - ¿Sobrecompra extrema?
            rsi_data = indicators.get('rsi', {})
            rsi_value = rsi_data.get('rsi', 50)
            
            if rsi_value > 80:
                deterioration_score += 25  # RSI extremo
                reasons.append(f"🔴 RSI: Sobrecompra extrema ({rsi_value:.1f})")
            elif rsi_value > 75:
                deterioration_score += 15  # RSI muy alto
                reasons.append(f"⚠️ RSI: Sobrecompra severa ({rsi_value:.1f})")
            
            # 3. VWAP - ¿Muy alejado por arriba?
            vwap_data = indicators.get('vwap', {})
            vwap_deviation = vwap_data.get('deviation_pct', 0)
            
            if vwap_deviation > 3.0:
                deterioration_score += 20  # Muy alejado = distribución
                reasons.append(f"📊 VWAP: Precio muy alejado (+{vwap_deviation:.1f}%)")
            elif vwap_deviation > 2.0:
                deterioration_score += 10
                reasons.append(f"⚠️ VWAP: Precio alejado (+{vwap_deviation:.1f}%)")
            
            # 4. ROC - ¿Momentum bajista?
            roc_data = indicators.get('roc', {})
            roc_value = roc_data.get('roc', 0)
            
            if roc_value < -2.5:
                deterioration_score += 25  # Momentum muy bajista
                reasons.append(f"🔴 ROC: Momentum bajista fuerte ({roc_value:.1f}%)")
            elif roc_value < -1.0:
                deterioration_score += 15
                reasons.append(f"📉 ROC: Momentum bajista ({roc_value:.1f}%)")
            
            # 5. Bollinger Bands - ¿Rechazo en zona alta?
            bb_data = indicators.get('bollinger', {})
            bb_position = bb_data.get('bb_position', 0.5)
            
            if bb_position > 0.9:
                deterioration_score += 20  # En banda superior = distribución
                reasons.append("🔴 BB: Precio en banda superior - posible rechazo")
            elif bb_position > 0.8:
                deterioration_score += 10
                reasons.append("⚠️ BB: Precio en zona alta")
            
            # 6. Volumen - ¿Distribución?
            vol_data = indicators.get('volume_osc', {})
            vol_oscillator = vol_data.get('volume_oscillator', 0)
            
            # Para LONG, volumen alto con precio cayendo = distribución
            current_price = indicators.get('current_price', position.current_price)
            price_change_pct = ((current_price - position.entry_price) / position.entry_price) * 100
            
            if vol_oscillator > 50 and price_change_pct < -1.0:
                deterioration_score += 15  # Alto volumen + precio bajando
                reasons.append("📊 VOLUME: Alto volumen con precio bajando (distribución)")
            
            return deterioration_score, reasons
            
        except Exception as e:
            logger.error(f"❌ Error evaluando LONG exit: {e}")
            return 0, [f"Error en evaluación: {str(e)}"]
    
    def evaluate_exit_for_short(self, position: ActivePosition, indicators: Dict) -> Tuple[int, List[str]]:
        """
        Evaluar deterioro para posición SHORT
        
        Busca condiciones que invaliden la tesis bajista original:
        - MACD girando alcista con fuerza
        - RSI en sobreventa extrema (<25) y divergencia alcista
        - Precio volviendo hacia VWAP desde zona alta
        - ROC volviéndose fuertemente positivo
        - Bollinger Bands: precio en zona inferior con rebote
        - Volumen confirmando la acumulación
        """
        try:
            deterioration_score = 0
            reasons = []
            
            # 1. MACD - ¿Girando alcista?
            macd_data = indicators.get('macd', {})
            if macd_data.get('bullish_cross', False):
                deterioration_score += 25  # Cruce alcista = deterioro severo para SHORT
                reasons.append("🟢 MACD: Cruce alcista confirmado")
            elif macd_data.get('histogram', 0) > 0.01:
                deterioration_score += 15
                reasons.append("📈 MACD: Histogram fuertemente positivo")
            
            # 2. RSI - ¿Sobreventa extrema con divergencia?
            rsi_data = indicators.get('rsi', {})
            rsi_value = rsi_data.get('rsi', 50)
            
            if rsi_value < 20:
                deterioration_score += 25  # RSI extremo = posible rebote
                reasons.append(f"🟢 RSI: Sobreventa extrema ({rsi_value:.1f})")
            elif rsi_value < 25:
                deterioration_score += 15
                reasons.append(f"⚠️ RSI: Sobreventa severa ({rsi_value:.1f})")
            
            # 3. VWAP - ¿Volviendo hacia VWAP?
            vwap_data = indicators.get('vwap', {})
            vwap_deviation = vwap_data.get('deviation_pct', 0)
            
            # Para SHORT queremos que se mantenga alejado por arriba
            if -1.0 < vwap_deviation < 1.0:
                deterioration_score += 20  # Volviendo al VWAP = pérdida de control bajista
                reasons.append(f"📊 VWAP: Precio volviendo al VWAP ({vwap_deviation:+.1f}%)")
            elif vwap_deviation < -2.0:
                deterioration_score += 15  # Muy por debajo puede ser sobreventa extrema
                reasons.append(f"🟢 VWAP: Precio muy por debajo ({vwap_deviation:+.1f}%) - posible rebote")
            
            # 4. ROC - ¿Momentum alcista?
            roc_data = indicators.get('roc', {})
            roc_value = roc_data.get('roc', 0)
            
            if roc_value > 2.5:
                deterioration_score += 25  # Momentum fuertemente alcista
                reasons.append(f"🟢 ROC: Momentum alcista fuerte (+{roc_value:.1f}%)")
            elif roc_value > 1.0:
                deterioration_score += 15
                reasons.append(f"📈 ROC: Momentum alcista (+{roc_value:.1f}%)")
            
            # 5. Bollinger Bands - ¿Rebote desde zona baja?
            bb_data = indicators.get('bollinger', {})
            bb_position = bb_data.get('bb_position', 0.5)
            
            if bb_position < 0.1:
                deterioration_score += 20  # En banda inferior = posible rebote
                reasons.append("🟢 BB: Precio en banda inferior - posible rebote")
            elif bb_position < 0.2:
                deterioration_score += 10
                reasons.append("⚠️ BB: Precio en zona baja")
            
            # 6. Volumen - ¿Acumulación?
            vol_data = indicators.get('volume_osc', {})
            vol_oscillator = vol_data.get('volume_oscillator', 0)
            
            # Para SHORT, volumen alto con precio subiendo = acumulación
            current_price = indicators.get('current_price', position.current_price)
            price_change_pct = ((current_price - position.entry_price) / position.entry_price) * 100
            
            # Para SHORT, price_change_pct positivo es malo (precio subiendo)
            if vol_oscillator > 50 and price_change_pct > 1.0:
                deterioration_score += 15  # Alto volumen + precio subiendo
                reasons.append("📊 VOLUME: Alto volumen con precio subiendo (acumulación)")
            
            return deterioration_score, reasons
            
        except Exception as e:
            logger.error(f"❌ Error evaluando SHORT exit: {e}")
            return 0, [f"Error en evaluación: {str(e)}"]
    
    def calculate_momentum_change(self, position: ActivePosition, current_roc: float) -> float:
        """Calcular cambio de momentum desde la entrada"""
        try:
            # ROC de la señal original
            original_roc = position.entry_signal.indicator_scores.get('ROC', 0)
            
            # Convertir score a valor aproximado de ROC
            if position.direction == 'LONG':
                if original_roc >= 18:
                    original_roc_value = 2.5  # Momentum fuerte alcista
                elif original_roc >= 15:
                    original_roc_value = 1.8
                elif original_roc >= 10:
                    original_roc_value = 1.0
                else:
                    original_roc_value = 0.5
            else:  # SHORT
                if original_roc >= 18:
                    original_roc_value = -2.5  # Momentum fuerte bajista
                elif original_roc >= 15:
                    original_roc_value = -1.8
                elif original_roc >= 10:
                    original_roc_value = -1.0
                else:
                    original_roc_value = -0.5
            
            # Cambio porcentual en momentum
            if original_roc_value != 0:
                momentum_change = ((current_roc - original_roc_value) / abs(original_roc_value)) * 100
            else:
                momentum_change = 0
            
            return momentum_change
            
        except Exception as e:
            logger.error(f"❌ Error calculando cambio momentum: {e}")
            return 0
    
    def detect_trend_reversal(self, position: ActivePosition, indicators: Dict) -> bool:
        """Detectar si hay reversión de tendencia clara"""
        try:
            macd_data = indicators.get('macd', {})
            rsi_data = indicators.get('rsi', {})
            roc_data = indicators.get('roc', {})
            
            if position.direction == 'LONG':
                # Para LONG: reversal = MACD bajista + RSI alto + ROC negativo
                macd_bearish = macd_data.get('bearish_cross', False) or macd_data.get('histogram', 0) < -0.01
                rsi_high = rsi_data.get('rsi', 50) > 70
                roc_negative = roc_data.get('roc', 0) < -1.0
                
                return macd_bearish and (rsi_high or roc_negative)
            
            else:  # SHORT
                # Para SHORT: reversal = MACD alcista + RSI bajo + ROC positivo
                macd_bullish = macd_data.get('bullish_cross', False) or macd_data.get('histogram', 0) > 0.01
                rsi_low = rsi_data.get('rsi', 50) < 30
                roc_positive = roc_data.get('roc', 0) > 1.0
                
                return macd_bullish and (rsi_low or roc_positive)
                
        except Exception as e:
            logger.error(f"❌ Error detectando reversal: {e}")
            return False
    
    def detect_volume_divergence(self, position: ActivePosition, indicators: Dict) -> bool:
        """Detectar divergencia de volumen preocupante"""
        try:
            vol_data = indicators.get('volume_osc', {})
            vol_oscillator = vol_data.get('volume_oscillator', 0)
            
            current_price = indicators.get('current_price', position.current_price)
            price_change_pct = ((current_price - position.entry_price) / position.entry_price) * 100
            
            if position.direction == 'LONG':
                # Para LONG: divergencia = alto volumen + precio cayendo
                return vol_oscillator > 50 and price_change_pct < -2.0
            else:  # SHORT
                # Para SHORT: divergencia = alto volumen + precio subiendo
                return vol_oscillator > 50 and price_change_pct > 2.0
                
        except Exception as e:
            logger.error(f"❌ Error detectando divergencia volumen: {e}")
            return False
    
    def evaluate_position(self, symbol: str) -> Optional[ExitSignal]:
        """
        Evaluar una posición específica para posible salida
        """
        try:
            if symbol not in self.active_positions:
                return None
            
            position = self.active_positions[symbol]
            
            logger.info(f"🔍 Evaluando exit para {symbol} ({position.direction})")
            
            # Obtener indicadores actuales
            indicators = self.indicators.get_all_indicators(symbol)
            
            # Actualizar precio actual
            position.current_price = indicators['current_price']
            position.last_evaluation = datetime.now()
            
            # Calcular PnL actual
            if position.direction == 'LONG':
                position.unrealized_pnl_pct = ((position.current_price - position.entry_price) / position.entry_price) * 100
            else:  # SHORT
                position.unrealized_pnl_pct = ((position.entry_price - position.current_price) / position.entry_price) * 100
            
            # Evaluar deterioro según dirección
            if position.direction == 'LONG':
                exit_score, reasons = self.evaluate_exit_for_long(position, indicators)
            else:
                exit_score, reasons = self.evaluate_exit_for_short(position, indicators)
            
            # Si no hay deterioro significativo, no generar señal
            if exit_score < self.deterioration_thresholds['MILD']:
                logger.debug(f"✅ {symbol}: Sin deterioro significativo ({exit_score} pts)")
                return None
            
            # Determinar urgencia
            if exit_score >= self.deterioration_thresholds['CRITICAL']:
                urgency = ExitUrgency.EXIT_URGENT
                exit_percentage = 100  # Salir completamente
                recommended_action = "SALIR INMEDIATAMENTE - Deterioro crítico"
            elif exit_score >= self.deterioration_thresholds['SEVERE']:
                urgency = ExitUrgency.EXIT_URGENT
                exit_percentage = 75   # Salir 75%
                recommended_action = "SALIR URGENTE - Reducir posición significativamente"
            elif exit_score >= self.deterioration_thresholds['MODERATE']:
                urgency = ExitUrgency.EXIT_RECOMMENDED
                exit_percentage = 50   # Salir 50%
                recommended_action = "SALIDA RECOMENDADA - Reducir posición a la mitad"
            else:  # MILD
                urgency = ExitUrgency.EXIT_WATCH
                exit_percentage = 0    # Solo vigilar
                recommended_action = "VIGILAR DE CERCA - Condiciones se deterioran"
            
            # Calcular métricas adicionales
            current_roc = indicators.get('roc', {}).get('roc', 0)
            momentum_change = self.calculate_momentum_change(position, current_roc)
            trend_reversal = self.detect_trend_reversal(position, indicators)
            volume_divergence = self.detect_volume_divergence(position, indicators)
            
            # Incrementar contador de deterioro si es necesario
            if urgency in [ExitUrgency.EXIT_RECOMMENDED, ExitUrgency.EXIT_URGENT]:
                position.deterioration_count += 1
            
            # Crear señal de exit
            exit_signal = ExitSignal(
                symbol=symbol,
                urgency=urgency,
                exit_score=exit_score,
                position=position,
                technical_reasons=reasons,
                momentum_change=momentum_change,
                trend_reversal=trend_reversal,
                volume_divergence=volume_divergence,
                recommended_action=recommended_action,
                exit_percentage=exit_percentage,
                timestamp=datetime.now(),
                current_indicators=indicators
            )
            
            logger.info(f"🚪 {symbol}: Exit evaluado - {urgency.value} ({exit_score} pts)")
            logger.info(f"   PnL actual: {position.unrealized_pnl_pct:+.1f}%")
            logger.info(f"   Recomendación: {recommended_action}")
            
            return exit_signal
            
        except Exception as e:
            logger.error(f"❌ Error evaluando {symbol}: {e}")
            return None
    
    def evaluate_all_positions(self) -> List[ExitSignal]:
        """Evaluar todas las posiciones activas"""
        try:
            if not self.active_positions:
                logger.info("📊 No hay posiciones activas para evaluar")
                return []
            
            logger.info(f"🔍 Evaluando {len(self.active_positions)} posiciones activas...")
            
            exit_signals = []
            
            for symbol in list(self.active_positions.keys()):
                try:
                    exit_signal = self.evaluate_position(symbol)
                    if exit_signal:
                        exit_signals.append(exit_signal)
                        
                except Exception as e:
                    logger.error(f"❌ Error evaluando {symbol}: {e}")
                    continue
            
            # Ordenar por urgencia y score
            exit_signals.sort(key=lambda x: (x.urgency.value, x.exit_score), reverse=True)
            
            logger.info(f"🚪 Evaluación completada: {len(exit_signals)} alertas de exit generadas")
            
            return exit_signals
            
        except Exception as e:
            logger.error(f"❌ Error en evaluación general: {e}")
            return []
    
    def save_positions(self):
        """Guardar posiciones en archivo JSON"""
        try:
            positions_data = {}
            
            for symbol, position in self.active_positions.items():
                positions_data[symbol] = {
                    'symbol': position.symbol,
                    'direction': position.direction,
                    'entry_time': position.entry_time.isoformat(),
                    'entry_price': position.entry_price,
                    'current_price': position.current_price,
                    'unrealized_pnl_pct': position.unrealized_pnl_pct,
                    'deterioration_count': position.deterioration_count,
                    'exit_alerts_sent': position.exit_alerts_sent,
                    'last_evaluation': position.last_evaluation.isoformat() if position.last_evaluation else None,
                    
                    # Señal original (básica)
                    'entry_signal_strength': position.entry_signal.signal_strength,
                    'entry_confidence': position.entry_signal.confidence_level,
                    'strategy_type': position.position_plan.strategy_type if position.position_plan else None
                }
            
            with open(self.positions_file, 'w') as f:
                json.dump(positions_data, f, indent=2)
                
        except Exception as e:
            logger.error(f"❌ Error guardando posiciones: {e}")
    
    def load_positions(self):
        """Cargar posiciones desde archivo JSON"""
        try:
            if not os.path.exists(self.positions_file):
                return
            
            with open(self.positions_file, 'r') as f:
                positions_data = json.load(f)
            
            for symbol, data in positions_data.items():
                # Crear posición básica (sin objetos completos por simplicidad)
                position = ActivePosition(
                    symbol=data['symbol'],
                    direction=data['direction'],
                    entry_signal=None,  # Se reconstruirá si es necesario
                    entry_time=datetime.fromisoformat(data['entry_time'][:19]) if 'T' in data['entry_time'] else datetime.fromisoformat(data['entry_time']),
                    entry_price=data['entry_price'],
                    position_plan=None,  # Se reconstruirá si es necesario
                    current_price=data.get('current_price', data['entry_price']),
                    unrealized_pnl_pct=data.get('unrealized_pnl_pct', 0),
                    deterioration_count=data.get('deterioration_count', 0),
                    exit_alerts_sent=data.get('exit_alerts_sent', 0)
                )
                
                if data.get('last_evaluation'):
                    position.last_evaluation = datetime.fromisoformat(data['last_evaluation'])
                
                self.active_positions[symbol] = position
            
            logger.info(f"📂 {len(self.active_positions)} posiciones cargadas desde {self.positions_file}")
            
        except Exception as e:
            logger.error(f"❌ Error cargando posiciones: {e}")
    
    def get_positions_summary(self) -> Dict:
        """Obtener resumen de posiciones activas"""
        try:
            if not self.active_positions:
                return {'total_positions': 0}
            
            summary = {
                'total_positions': len(self.active_positions),
                'long_positions': sum(1 for p in self.active_positions.values() if p.direction == 'LONG'),
                'short_positions': sum(1 for p in self.active_positions.values() if p.direction == 'SHORT'),
                'positions_with_deterioration': sum(1 for p in self.active_positions.values() if p.deterioration_count > 0),
                'avg_days_held': sum((datetime.now() - p.entry_time).days for p in self.active_positions.values()) / len(self.active_positions),
                'total_unrealized_pnl': sum(p.unrealized_pnl_pct for p in self.active_positions.values()),
                'positions': {}
            }
            
            for symbol, position in self.active_positions.items():
                days_held = (datetime.now() - position.entry_time).days
                summary['positions'][symbol] = {
                    'direction': position.direction,
                    'entry_price': position.entry_price,
                    'current_price': position.current_price,
                    'unrealized_pnl_pct': position.unrealized_pnl_pct,
                    'days_held': days_held,
                    'deterioration_count': position.deterioration_count,
                    'exit_alerts_sent': position.exit_alerts_sent
                }
            
            return summary
            
        except Exception as e:
            logger.error(f"❌ Error en resumen posiciones: {e}")
            return {'error': str(e)}


# =============================================================================
# 🧪 FUNCIONES DE TESTING Y DEMO
# =============================================================================

def test_exit_manager():
    """Test básico del exit manager"""
    print("🧪 TESTING EXIT MANAGER")
    print("=" * 50)
    
    try:
        # Crear exit manager
        exit_manager = ExitManager("test_positions.json")
        
        # Test 1: Estado inicial
        print("1. Estado inicial:")
        summary = exit_manager.get_positions_summary()
        print(f"   Posiciones activas: {summary['total_positions']}")
        
        # Test 2: Simular posición (necesitaríamos una señal real)
        print("\n2. Simulación de posición:")
        print("   (Requiere señal real del scanner para test completo)")
        
        # Test 3: Evaluación general
        print("\n3. Evaluación de todas las posiciones:")
        exit_signals = exit_manager.evaluate_all_positions()
        print(f"   Señales de exit generadas: {len(exit_signals)}")
        
        print("\n✅ Test básico completado")
        return True
        
    except Exception as e:
        print(f"❌ Error en test: {e}")
        return False

def demo_exit_manager_with_real_position():
    """Demo con posición real simulada"""
    print("🎯 DEMO EXIT MANAGER CON POSICIÓN REAL")
    print("=" * 60)
    
    try:
        from scanner import SignalScanner, TradingSignal
        from position_calculator import PositionCalculator
        
        # Crear componentes
        scanner = SignalScanner()
        exit_manager = ExitManager("demo_positions.json")
        
        # 1. Generar señal real
        print("1. 🔍 Generando señal de entrada real...")
        signal = scanner.scan_symbol("SPY")  # Usar SPY para el demo
        
        if signal:
            print(f"   ✅ Señal generada: {signal.symbol} {signal.signal_type}")
            print(f"   Fuerza: {signal.signal_strength}/100")
            print(f"   Precio: ${signal.current_price:.2f}")
            
            # 2. Añadir posición
            print("\n2. 📊 Añadiendo posición al seguimiento...")
            entry_price = signal.current_price  # Simular entrada al precio actual
            success = exit_manager.add_position(signal, entry_price)
            
            if success:
                print(f"   ✅ Posición añadida correctamente")
                
                # 3. Evaluar inmediatamente (para demo)
                print("\n3. 🚪 Evaluando condiciones de salida...")
                exit_signal = exit_manager.evaluate_position(signal.symbol)
                
                if exit_signal:
                    print(f"   🚨 ALERTA EXIT: {exit_signal.urgency.value}")
                    print(f"   Score deterioro: {exit_signal.exit_score}/100")
                    print(f"   Recomendación: {exit_signal.recommended_action}")
                    print(f"   Salir: {exit_signal.exit_percentage}% de la posición")
                    
                    print(f"\n   📋 Razones técnicas:")
                    for i, reason in enumerate(exit_signal.technical_reasons, 1):
                        print(f"   {i}. {reason}")
                    
                    print(f"\n   📈 Métricas adicionales:")
                    print(f"   • Cambio momentum: {exit_signal.momentum_change:+.1f}%")
                    print(f"   • Reversión de tendencia: {'✅ SÍ' if exit_signal.trend_reversal else '❌ NO'}")
                    print(f"   • Divergencia volumen: {'✅ SÍ' if exit_signal.volume_divergence else '❌ NO'}")
                    
                else:
                    print("   ✅ No hay condiciones de deterioro significativo")
                
                # 4. Resumen posiciones
                print("\n4. 📊 Resumen de posiciones:")
                summary = exit_manager.get_positions_summary()
                print(f"   Total posiciones: {summary['total_positions']}")
                print(f"   LONG: {summary.get('long_positions', 0)}")
                print(f"   SHORT: {summary.get('short_positions', 0)}")
                print(f"   PnL total no realizado: {summary.get('total_unrealized_pnl', 0):+.1f}%")
                
                # 5. Cleanup
                print("\n5. 🧹 Limpiando demo...")
                exit_manager.remove_position(signal.symbol, "Demo completado")
                
            else:
                print("   ❌ Error añadiendo posición")
        else:
            print("   📊 No hay señales disponibles para demo")
            print("   💡 Esto es normal - el sistema es selectivo")
        
        print("\n✅ Demo completado exitosamente")
        return True
        
    except Exception as e:
        print(f"❌ Error en demo: {e}")
        return False

if __name__ == "__main__":
    # Menú interactivo para testing
    print("🚪 EXIT MANAGER V2.1 - MODO TESTING")
    print("=" * 50)
    print("Selecciona un test:")
    print("1. Test básico del exit manager")
    print("2. Demo con posición real")
    print("3. Mostrar posiciones activas")
    print("4. Ejecutar evaluación completa")
    print("")
    
    try:
        choice = input("Elige una opción (1-4): ").strip()
        print("")
        
        if choice == "1":
            test_exit_manager()
        
        elif choice == "2":
            demo_exit_manager_with_real_position()
        
        elif choice == "3":
            exit_manager = ExitManager()
            summary = exit_manager.get_positions_summary()
            
            print("📊 POSICIONES ACTIVAS:")
            print("=" * 40)
            
            if summary['total_positions'] == 0:
                print("No hay posiciones activas")
            else:
                print(f"Total: {summary['total_positions']}")
                print(f"LONG: {summary.get('long_positions', 0)}")
                print(f"SHORT: {summary.get('short_positions', 0)}")
                print(f"Con deterioro: {summary.get('positions_with_deterioration', 0)}")
                print(f"PnL total: {summary.get('total_unrealized_pnl', 0):+.1f}%")
                print("")
                
                positions = summary.get('positions', {})
                for symbol, pos_data in positions.items():
                    print(f"{symbol} ({pos_data['direction']}):")
                    print(f"  Entrada: ${pos_data['entry_price']:.2f}")
                    print(f"  Actual: ${pos_data['current_price']:.2f}")
                    print(f"  PnL: {pos_data['unrealized_pnl_pct']:+.1f}%")
                    print(f"  Días: {pos_data['days_held']}")
                    print(f"  Alertas exit: {pos_data['exit_alerts_sent']}")
                    print("")
        
        elif choice == "4":
            print("🔍 Ejecutando evaluación completa...")
            exit_manager = ExitManager()
            exit_signals = exit_manager.evaluate_all_positions()
            
            if exit_signals:
                print(f"\n🚨 {len(exit_signals)} ALERTAS DE EXIT:")
                print("=" * 50)
                
                for i, signal in enumerate(exit_signals, 1):
                    print(f"{i}. {signal.symbol} - {signal.urgency.value}")
                    print(f"   Score: {signal.exit_score}/100")
                    print(f"   PnL: {signal.position.unrealized_pnl_pct:+.1f}%")
                    print(f"   Recomendación: Salir {signal.exit_percentage}%")
                    print(f"   Razones principales:")
                    for reason in signal.technical_reasons[:2]:  # Solo 2 principales
                        print(f"     • {reason}")
                    print("")
            else:
                print("✅ No hay alertas de exit en este momento")
        
        else:
            print("❌ Opción no válida")
            
    except KeyboardInterrupt:
        print("\n👋 Tests interrumpidos por el usuario")
    except Exception as e:
        print(f"❌ Error ejecutando tests: {e}")
    
    print("\n🏁 Tests completados!")