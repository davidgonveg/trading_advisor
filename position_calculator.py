#!/usr/bin/env python3
"""
💰 POSITION CALCULATOR V3.0 - CON TARGETS ADAPTATIVOS
====================================================

Versión mejorada que integra:
- Sistema de Take Profits orgánicos y adaptativos
- Análisis técnico real para targets
- Stop loss dinámico mejorado
- Gestión de riesgo contextual

MEJORAS PRINCIPALES:
- Targets basados en resistencias/soportes REALES
- R:R realistas (1.2 - 6.0 máximo)
- Fibonacci automático
- VWAP y Bollinger como targets dinámicos
- Distribución adaptativa según calidad de señal
"""

import logging
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime
import numpy as np
import pandas as pd

# Importar el nuevo calculador adaptativo
from adaptive_targets import AdaptiveTakeProfitCalculator, AdaptiveTarget

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class PositionLevel:
    """Representa un nivel de entrada o salida mejorado"""
    level_type: str  # 'ENTRY', 'EXIT', 'STOP'
    price: float
    percentage: float  # % del capital total a usar
    description: str
    trigger_condition: str = ""
    
    # Nuevos campos para targets adaptativos
    risk_reward: Optional[float] = None
    confidence: Optional[float] = None
    technical_basis: Optional[List[str]] = None

@dataclass
class PositionPlan:
    """Plan completo de posición mejorado"""
    symbol: str
    direction: str  # 'LONG' o 'SHORT'
    current_price: float
    signal_strength: int
    strategy_type: str
    total_risk_percent: float
    
    # Niveles
    entries: List[PositionLevel]
    exits: List[PositionLevel]
    stop_loss: PositionLevel
    
    # Métricas mejoradas
    max_risk_reward: float
    avg_risk_reward: float  # Nuevo: R:R promedio ponderado
    expected_hold_time: str
    confidence_level: str
    
    # Nuevos campos técnicos
    technical_summary: str
    market_context: str
    risk_assessment: str

class PositionCalculatorV3:
    """
    Calculadora de posiciones V3.0 con targets adaptativos
    """
    
    def __init__(self):
        """Inicializar calculadora mejorada"""
        
        # Inicializar calculador adaptativo
        self.adaptive_calculator = AdaptiveTakeProfitCalculator()
        
        # Estrategias mejoradas (R:R más realistas)
        self.strategies = {
            'SCALP': {
                'signal_threshold': 85,
                'max_entries': 2,
                'base_risk': 1.0,
                'max_rr': 3.0,  # Máximo R:R realista para scalping
                'time_horizon': '15-45 min',
                'description': 'Señal muy fuerte - Scalping agresivo'
            },
            'SWING_SHORT': {
                'signal_threshold': 75,
                'max_entries': 3,
                'base_risk': 1.2,
                'max_rr': 5.0,  # Máximo R:R para swing corto
                'time_horizon': '2-8 horas',
                'description': 'Señal buena - Swing corto'
            },
            'SWING_MEDIUM': {
                'signal_threshold': 65,
                'max_entries': 3,
                'base_risk': 1.5,
                'max_rr': 6.0,  # Máximo R:R para swing medio
                'time_horizon': '1-3 días',
                'description': 'Señal moderada - Swing medio'
            },
            'POSITION': {
                'signal_threshold': 60,
                'max_entries': 4,
                'base_risk': 2.0,
                'max_rr': 6.0,  # Ya no más de 6R (antes era 10R irreal)
                'time_horizon': '3-10 días',
                'description': 'Señal débil - Trading posicional'
            }
        }
        
        # Ajustes por volatilidad (mejorados)
        self.volatility_adjustments = {
            'LOW': {
                'atr_multiplier': 1.8,
                'risk_reduction': 1.2,
                'target_extension': 0.9  # Targets más conservadores en baja volatilidad
            },
            'NORMAL': {
                'atr_multiplier': 2.0,
                'risk_reduction': 1.0,
                'target_extension': 1.0
            },
            'HIGH': {
                'atr_multiplier': 2.5,
                'risk_reduction': 0.8,
                'target_extension': 1.1  # Targets ligeramente más ambiciosos
            }
        }
    
    def calculate_position_plan_v3(self, 
                                  symbol: str, 
                                  direction: str, 
                                  current_price: float, 
                                  signal_strength: int, 
                                  indicators: Dict,
                                  market_data: pd.DataFrame,  # Nuevo: datos OHLCV para análisis técnico
                                  account_balance: float = 10000) -> PositionPlan:
        """
        Calcular plan completo de posición V3.0 con targets adaptativos
        """
        try:
            logger.info(f"💰 Calculando plan V3.0 para {symbol} - {direction}")
            
            # 1. Determinar estrategia
            strategy_name = self.determine_strategy(signal_strength, indicators)
            strategy = self.strategies[strategy_name]
            
            # 2. Obtener datos técnicos
            atr = indicators.get('atr', {}).get('atr', current_price * 0.02)
            volatility = indicators.get('atr', {}).get('volatility_level', 'NORMAL')
            
            # 3. Calcular entradas (mantener lógica existente mejorada)
            entries = self.calculate_entry_levels_v3(
                current_price, atr, direction, strategy, volatility
            )
            
            if not entries:
                raise ValueError("No se pudieron calcular entradas")
            
            # 4. Calcular stop loss mejorado
            main_entry_price = entries[0].price
            stop_loss = self.calculate_stop_loss_v3(
                main_entry_price, atr, direction, strategy, volatility, indicators
            )
            
            # 5. 🚀 NUEVA FUNCIONALIDAD: Calcular targets adaptativos
            adaptive_targets = self.adaptive_calculator.calculate_adaptive_targets(
                symbol=symbol,
                data=market_data,
                entry_price=main_entry_price,
                stop_price=stop_loss.price,
                direction=direction,
                indicators=indicators,
                signal_strength=signal_strength
            )
            
            # 6. Convertir targets adaptativos a PositionLevel
            exits = self.convert_adaptive_targets_to_levels(adaptive_targets)
            
            # 7. Validar que los targets no excedan máximo R:R de la estrategia
            exits = self.validate_targets_against_strategy(exits, main_entry_price, stop_loss.price, strategy)
            
            # 8. Calcular métricas mejoradas
            metrics = self.calculate_enhanced_metrics(exits, main_entry_price, stop_loss.price)
            
            # 9. Generar análisis contextual
            context_analysis = self.generate_context_analysis(indicators, signal_strength, volatility)
            
            # 10. Determinar nivel de confianza mejorado
            confidence = self.calculate_enhanced_confidence(signal_strength, adaptive_targets, indicators)
            
            # 11. Ajustar riesgo total
            vol_risk_adj = self.volatility_adjustments[volatility]['risk_reduction']
            total_risk = strategy['base_risk'] / vol_risk_adj
            
            # 12. Crear plan final
            plan = PositionPlan(
                symbol=symbol,
                direction=direction,
                current_price=current_price,
                signal_strength=signal_strength,
                strategy_type=strategy_name,
                total_risk_percent=total_risk,
                entries=entries,
                exits=exits,
                stop_loss=stop_loss,
                max_risk_reward=metrics['max_rr'],
                avg_risk_reward=metrics['avg_rr'],
                expected_hold_time=strategy['time_horizon'],
                confidence_level=confidence,
                technical_summary=context_analysis['technical_summary'],
                market_context=context_analysis['market_context'],
                risk_assessment=context_analysis['risk_assessment']
            )
            
            logger.info(f"✅ Plan V3.0 calculado: {strategy_name} - {confidence} confidence - Avg {metrics['avg_rr']:.1f}R")
            return plan
            
        except Exception as e:
            logger.error(f"❌ Error calculando plan V3.0: {e}")
            # Fallback al sistema anterior si falla
            return self.calculate_fallback_plan(symbol, direction, current_price, signal_strength, indicators, account_balance)
    
    def determine_strategy(self, signal_strength: int, indicators: Dict) -> str:
        """Determinar estrategia basada en fuerza de señal"""
        try:
            # Lógica mejorada que considera también volatilidad
            volatility = indicators.get('atr', {}).get('volatility_level', 'NORMAL')
            
            if signal_strength >= 85:
                return 'SCALP'
            elif signal_strength >= 75:
                # En alta volatilidad, preferir swing corto aunque señal sea fuerte
                return 'SWING_SHORT'
            elif signal_strength >= 65:
                return 'SWING_MEDIUM'
            else:
                return 'POSITION'
                
        except Exception as e:
            logger.warning(f"⚠️ Error determinando estrategia: {e}")
            return 'SWING_MEDIUM'  # Estrategia por defecto
    
    def calculate_entry_levels_v3(self, 
                                 current_price: float, 
                                 atr: float, 
                                 direction: str, 
                                 strategy: Dict,
                                 volatility: str) -> List[PositionLevel]:
        """Calcular niveles de entrada mejorados"""
        try:
            entries = []
            max_entries = strategy['max_entries']
            vol_adj = self.volatility_adjustments[volatility]['atr_multiplier']
            
            if direction == 'LONG':
                if max_entries == 2:
                    # Scalping - entradas más precisas
                    prices = [
                        current_price,
                        current_price - (atr * 0.25 * vol_adj)  # Entrada más cerca
                    ]
                    percentages = [70, 30]  # Más peso en primera entrada
                    descriptions = [
                        "Entrada inmediata - Breakout confirmado",
                        "Entrada retroceso - Dip buy oportunista"
                    ]
                
                elif max_entries == 3:
                    # Swing - distribución balanceada
                    prices = [
                        current_price,
                        current_price - (atr * 0.4 * vol_adj),
                        current_price - (atr * 0.8 * vol_adj)
                    ]
                    percentages = [45, 35, 20]  # Distribución mejorada
                    descriptions = [
                        "Entrada 1 - Confirmación técnica",
                        "Entrada 2 - Retroceso controlado", 
                        "Entrada 3 - Oportunidad valor"
                    ]
                
                else:  # 4 entradas
                    prices = [
                        current_price,
                        current_price - (atr * 0.3 * vol_adj),
                        current_price - (atr * 0.6 * vol_adj),
                        current_price - (atr * 1.0 * vol_adj)
                    ]
                    percentages = [35, 30, 20, 15]
                    descriptions = [
                        "Entrada 1 - Test inicial",
                        "Entrada 2 - Pullback menor",
                        "Entrada 3 - Soporte técnico",
                        "Entrada 4 - Valor extremo"
                    ]
            
            else:  # SHORT
                if max_entries == 2:
                    prices = [
                        current_price,
                        current_price + (atr * 0.25 * vol_adj)
                    ]
                    percentages = [70, 30]
                    descriptions = [
                        "Entrada inmediata - Breakdown confirmado",
                        "Entrada rally - Pullback short"
                    ]
                
                elif max_entries == 3:
                    prices = [
                        current_price,
                        current_price + (atr * 0.4 * vol_adj),
                        current_price + (atr * 0.8 * vol_adj)
                    ]
                    percentages = [45, 35, 20]
                    descriptions = [
                        "Entrada 1 - Confirmación bajista",
                        "Entrada 2 - Rally controlado",
                        "Entrada 3 - Rechazo resistencia"
                    ]
                
                else:  # 4 entradas
                    prices = [
                        current_price,
                        current_price + (atr * 0.3 * vol_adj),
                        current_price + (atr * 0.6 * vol_adj),
                        current_price + (atr * 1.0 * vol_adj)
                    ]
                    percentages = [35, 30, 20, 15]
                    descriptions = [
                        "Entrada 1 - Test inicial bajista",
                        "Entrada 2 - Rally menor",
                        "Entrada 3 - Resistencia técnica",
                        "Entrada 4 - Rechazo extremo"
                    ]
            
            # Crear PositionLevels
            for price, pct, desc in zip(prices, percentages, descriptions):
                entries.append(PositionLevel(
                    level_type='ENTRY',
                    price=round(price, 2),
                    percentage=pct,
                    description=desc,
                    trigger_condition=f"Precio {'<=' if direction == 'LONG' else '>='} {price:.2f}"
                ))
            
            return entries
            
        except Exception as e:
            logger.error(f"❌ Error calculando entradas V3: {e}")
            return []
    
    def calculate_stop_loss_v3(self, 
                              entry_price: float, 
                              atr: float, 
                              direction: str, 
                              strategy: Dict,
                              volatility: str,
                              indicators: Dict) -> PositionLevel:
        """Calcular stop loss dinámico mejorado V3"""
        try:
            vol_adj = self.volatility_adjustments[volatility]['atr_multiplier']
            
            # Base stop en ATR
            base_stop_distance = atr * vol_adj
            
            # Ajustar según estrategia (mejorado)
            if strategy == self.strategies['SCALP']:
                stop_multiplier = 0.75  # Stops más ajustados para scalping
            elif strategy == self.strategies['SWING_SHORT']:
                stop_multiplier = 1.0   # Stop normal
            elif strategy == self.strategies['SWING_MEDIUM']:
                stop_multiplier = 1.25  # Stop más amplio
            else:  # POSITION
                stop_multiplier = 1.4   # Stop amplio pero no excesivo (antes 1.5)
            
            # 🆕 AJUSTE POR CONTEXTO TÉCNICO
            context_adj = 1.0
            
            # Ajustar por RSI (en extremos, stops más amplios)
            rsi_data = indicators.get('rsi', {})
            rsi_value = rsi_data.get('rsi', 50)
            
            if direction == 'LONG' and rsi_value < 25:
                context_adj *= 1.15  # RSI muy bajo = más espacio al stop
            elif direction == 'SHORT' and rsi_value > 75:
                context_adj *= 1.15  # RSI muy alto = más espacio al stop
            
            # Ajustar por volatilidad reciente
            if volatility == 'HIGH':
                context_adj *= 1.1  # Más espacio en alta volatilidad
            elif volatility == 'LOW':
                context_adj *= 0.95  # Menos espacio en baja volatilidad
            
            # Calcular distancia final del stop
            final_stop_distance = base_stop_distance * stop_multiplier * context_adj
            
            if direction == 'LONG':
                stop_price = entry_price - final_stop_distance
                description = f"Stop dinámico ATR {final_stop_distance:.2f} bajo entrada"
            else:
                stop_price = entry_price + final_stop_distance
                description = f"Stop dinámico ATR {final_stop_distance:.2f} sobre entrada"
            
            return PositionLevel(
                level_type='STOP',
                price=round(stop_price, 2),
                percentage=100,  # Todo out en stop
                description=description,
                trigger_condition=f"Precio {'<' if direction == 'LONG' else '>'} {stop_price:.2f}"
            )
            
        except Exception as e:
            logger.error(f"❌ Error calculando stop V3: {e}")
            # Stop de emergencia
            emergency_stop = entry_price * (0.98 if direction == 'LONG' else 1.02)
            return PositionLevel('STOP', emergency_stop, 100, "Stop de emergencia", "")
    
    def convert_adaptive_targets_to_levels(self, adaptive_targets: List[AdaptiveTarget]) -> List[PositionLevel]:
        """Convertir targets adaptativos a PositionLevels"""
        try:
            exit_levels = []
            
            for i, target in enumerate(adaptive_targets):
                exit_levels.append(PositionLevel(
                    level_type='EXIT',
                    price=target.price,
                    percentage=target.percentage_exit,
                    description=target.description,
                    trigger_condition=f"Precio alcanza ${target.price:.2f}",
                    risk_reward=target.risk_reward,
                    confidence=target.confidence,
                    technical_basis=target.technical_basis
                ))
            
            return exit_levels
            
        except Exception as e:
            logger.error(f"❌ Error convirtiendo targets adaptativos: {e}")
            return []
    
    def validate_targets_against_strategy(self, 
                                        exits: List[PositionLevel], 
                                        entry_price: float, 
                                        stop_price: float, 
                                        strategy: Dict) -> List[PositionLevel]:
        """Validar que targets no excedan límites de estrategia"""
        try:
            validated_exits = []
            risk_amount = abs(entry_price - stop_price)
            max_rr = strategy['max_rr']
            
            for exit_level in exits:
                # Calcular R:R real
                reward = abs(exit_level.price - entry_price)
                rr_ratio = reward / risk_amount if risk_amount > 0 else 0
                
                # Validar que no exceda máximo R:R de estrategia
                if rr_ratio <= max_rr:
                    # Actualizar R:R en el nivel
                    exit_level.risk_reward = round(rr_ratio, 2)
                    validated_exits.append(exit_level)
                else:
                    logger.warning(f"⚠️ Target {exit_level.price:.2f} excede máximo R:R {max_rr} (calculado: {rr_ratio:.1f})")
            
            # Si no quedan targets válidos, crear uno básico
            if not validated_exits:
                logger.warning("⚠️ No hay targets válidos, creando target conservador")
                conservative_rr = min(2.0, max_rr)
                
                if entry_price > stop_price:  # LONG
                    target_price = entry_price + (risk_amount * conservative_rr)
                else:  # SHORT
                    target_price = entry_price - (risk_amount * conservative_rr)
                
                validated_exits.append(PositionLevel(
                    level_type='EXIT',
                    price=round(target_price, 2),
                    percentage=100,
                    description=f"Target conservador {conservative_rr}R",
                    risk_reward=conservative_rr,
                    confidence=70.0,
                    technical_basis=["Target conservador por validación"]
                ))
            
            return validated_exits
            
        except Exception as e:
            logger.error(f"❌ Error validando targets: {e}")
            return exits  # Devolver originales si falla validación
    
    def calculate_enhanced_metrics(self, 
                                 exits: List[PositionLevel], 
                                 entry_price: float, 
                                 stop_price: float) -> Dict:
        """Calcular métricas mejoradas del plan"""
        try:
            if not exits:
                return {'max_rr': 0, 'avg_rr': 0}
            
            # Calcular R:R máximo
            max_rr = max([exit.risk_reward for exit in exits if exit.risk_reward])
            
            # Calcular R:R promedio ponderado por % de salida
            weighted_rr = 0
            total_percentage = 0
            
            for exit in exits:
                if exit.risk_reward and exit.percentage > 0:
                    weighted_rr += exit.risk_reward * (exit.percentage / 100)
                    total_percentage += exit.percentage
            
            avg_rr = weighted_rr if total_percentage > 0 else 0
            
            return {
                'max_rr': round(max_rr, 2),
                'avg_rr': round(avg_rr, 2)
            }
            
        except Exception as e:
            logger.error(f"❌ Error calculando métricas: {e}")
            return {'max_rr': 0, 'avg_rr': 0}
    
    def generate_context_analysis(self, 
                                indicators: Dict, 
                                signal_strength: int, 
                                volatility: str) -> Dict:
        """Generar análisis contextual del mercado"""
        try:
            # Análisis técnico
            tech_summary = []
            
            # RSI context
            rsi_data = indicators.get('rsi', {})
            rsi_value = rsi_data.get('rsi', 50)
            
            if rsi_value < 30:
                tech_summary.append("RSI oversold extremo")
            elif rsi_value < 40:
                tech_summary.append("RSI oversold")
            elif rsi_value > 70:
                tech_summary.append("RSI overbought extremo")
            elif rsi_value > 60:
                tech_summary.append("RSI overbought")
            else:
                tech_summary.append("RSI neutral")
            
            # ROC momentum
            roc_data = indicators.get('roc', {})
            roc_value = roc_data.get('roc', 0)
            
            if abs(roc_value) > 3:
                tech_summary.append("Momentum muy fuerte")
            elif abs(roc_value) > 1.5:
                tech_summary.append("Momentum moderado")
            else:
                tech_summary.append("Momentum débil")
            
            # VWAP position
            vwap_data = indicators.get('vwap', {})
            vwap_deviation = vwap_data.get('deviation_pct', 0)
            
            if abs(vwap_deviation) < 0.5:
                tech_summary.append("Precio cerca VWAP")
            elif abs(vwap_deviation) > 2:
                tech_summary.append("Precio alejado VWAP")
            else:
                tech_summary.append("Precio moderadamente alejado VWAP")
            
            # Contexto de mercado
            market_context = f"Volatilidad {volatility.lower()}, señal {signal_strength}/100"
            
            # Evaluación de riesgo
            risk_factors = []
            
            if volatility == 'HIGH':
                risk_factors.append("Alta volatilidad")
            if signal_strength < 70:
                risk_factors.append("Señal moderada")
            if abs(vwap_deviation) > 3:
                risk_factors.append("Precio muy alejado valor justo")
            
            risk_assessment = "Riesgo bajo" if not risk_factors else f"Factores riesgo: {', '.join(risk_factors)}"
            
            return {
                'technical_summary': ", ".join(tech_summary),
                'market_context': market_context,
                'risk_assessment': risk_assessment
            }
            
        except Exception as e:
            logger.error(f"❌ Error generando análisis contextual: {e}")
            return {
                'technical_summary': "Análisis no disponible",
                'market_context': "Contexto no disponible", 
                'risk_assessment': "Evaluación no disponible"
            }
    
    def calculate_enhanced_confidence(self, 
                                    signal_strength: int, 
                                    adaptive_targets: List[AdaptiveTarget],
                                    indicators: Dict) -> str:
        """Calcular nivel de confianza mejorado"""
        try:
            # Base confidence por signal strength
            base_confidence = signal_strength
            
            # Ajustar por calidad de targets adaptativos
            if adaptive_targets:
                avg_target_confidence = sum([t.confidence for t in adaptive_targets]) / len(adaptive_targets)
                # Promedio ponderado: 70% señal original + 30% targets adaptativos
                final_confidence = (base_confidence * 0.7) + (avg_target_confidence * 0.3)
            else:
                final_confidence = base_confidence * 0.8  # Penalizar si no hay targets adaptativos
            
            # Ajustar por confluencia de indicadores
            confluences = 0
            
            # Contar confluencias positivas
            rsi_data = indicators.get('rsi', {})
            if rsi_data.get('signal_strength', 0) > 15:
                confluences += 1
            
            roc_data = indicators.get('roc', {})
            if roc_data.get('signal_strength', 0) > 15:
                confluences += 1
            
            vwap_data = indicators.get('vwap', {})
            if vwap_data.get('signal_strength', 0) > 10:
                confluences += 1
            
            # Bonus por confluencias
            confluence_bonus = min(confluences * 3, 10)  # Max +10 pts
            final_confidence += confluence_bonus
            
            # Mapear a texto
            final_confidence = min(final_confidence, 100)
            
            if final_confidence >= 90:
                return "MUY ALTA"
            elif final_confidence >= 80:
                return "ALTA"
            elif final_confidence >= 70:
                return "MEDIA-ALTA"
            elif final_confidence >= 60:
                return "MEDIA"
            elif final_confidence >= 50:
                return "MEDIA-BAJA"
            else:
                return "BAJA"
                
        except Exception as e:
            logger.error(f"❌ Error calculando confianza mejorada: {e}")
            return "DESCONOCIDA"
    
    def calculate_fallback_plan(self, 
                              symbol: str, 
                              direction: str, 
                              current_price: float, 
                              signal_strength: int, 
                              indicators: Dict,
                              account_balance: float) -> PositionPlan:
        """Plan de respaldo si falla el sistema adaptativo"""
        try:
            logger.warning("⚠️ Usando plan de respaldo - sistema adaptativo falló")
            
            # Crear plan básico con targets conservadores
            atr = indicators.get('atr', {}).get('atr', current_price * 0.02)
            
            # Entrada simple
            entry = PositionLevel(
                level_type='ENTRY',
                price=current_price,
                percentage=100,
                description="Entrada única - plan respaldo"
            )
            
            # Stop loss conservador
            if direction == 'LONG':
                stop_price = current_price - (atr * 2)
            else:
                stop_price = current_price + (atr * 2)
            
            stop_loss = PositionLevel(
                level_type='STOP',
                price=round(stop_price, 2),
                percentage=100,
                description="Stop conservador 2xATR"
            )
            
            # Targets conservadores (máximo 3R)
            risk_amount = abs(current_price - stop_price)
            
            if direction == 'LONG':
                tp1_price = current_price + (risk_amount * 1.5)
                tp2_price = current_price + (risk_amount * 3.0)
            else:
                tp1_price = current_price - (risk_amount * 1.5)
                tp2_price = current_price - (risk_amount * 3.0)
            
            exits = [
                PositionLevel(
                    level_type='EXIT',
                    price=round(tp1_price, 2),
                    percentage=70,
                    description="TP1 conservador - 1.5R",
                    risk_reward=1.5
                ),
                PositionLevel(
                    level_type='EXIT',
                    price=round(tp2_price, 2),
                    percentage=30,
                    description="TP2 conservador - 3.0R",
                    risk_reward=3.0
                )
            ]
            
            return PositionPlan(
                symbol=symbol,
                direction=direction,
                current_price=current_price,
                signal_strength=signal_strength,
                strategy_type='FALLBACK',
                total_risk_percent=1.5,
                entries=[entry],
                exits=exits,
                stop_loss=stop_loss,
                max_risk_reward=3.0,
                avg_risk_reward=2.1,  # (1.5*0.7 + 3.0*0.3)
                expected_hold_time='1-4 horas',
                confidence_level='BAJA',
                technical_summary='Plan de respaldo',
                market_context='Sistema adaptativo no disponible',
                risk_assessment='Riesgo conservador'
            )
            
        except Exception as e:
            logger.error(f"❌ Error creando plan de respaldo: {e}")
            raise
    
    def format_position_summary_v3(self, plan: PositionPlan, account_balance: float = 10000) -> str:
        """Formatear resumen del plan V3.0 con información mejorada"""
        try:
            summary = []
            summary.append(f"📋 PLAN DE POSICIÓN V3.0 - {plan.symbol}")
            summary.append("=" * 70)
            summary.append(f"🎯 Dirección: {plan.direction}")
            summary.append(f"💪 Estrategia: {plan.strategy_type}")
            summary.append(f"🎲 Señal: {plan.signal_strength}/100 - Confianza {plan.confidence_level}")
            summary.append(f"💰 Riesgo total: {plan.total_risk_percent:.1f}% (${account_balance * plan.total_risk_percent / 100:.0f})")
            summary.append(f"⏰ Horizonte: {plan.expected_hold_time}")
            summary.append("")
            
            # Métricas mejoradas
            summary.append("📊 MÉTRICAS DE RENDIMIENTO:")
            summary.append(f"  🎯 R:R Máximo: 1:{plan.max_risk_reward}")
            summary.append(f"  📈 R:R Promedio: 1:{plan.avg_risk_reward}")
            summary.append(f"  📊 Análisis técnico: {plan.technical_summary}")
            summary.append(f"  🌍 Contexto mercado: {plan.market_context}")
            summary.append(f"  ⚠️ Evaluación riesgo: {plan.risk_assessment}")
            summary.append("")
            
            # Entradas
            summary.append("📈 ENTRADAS ESCALONADAS:")
            for i, entry in enumerate(plan.entries, 1):
                position_size = account_balance * plan.total_risk_percent / 100 * entry.percentage / 100
                summary.append(f"  {i}. ${entry.price:.2f} ({entry.percentage}%) - ${position_size:.0f}")
                summary.append(f"     {entry.description}")
            summary.append("")
            
            # Stop Loss
            summary.append("🛡️ STOP LOSS:")
            summary.append(f"  ${plan.stop_loss.price:.2f} (100% salida)")
            summary.append(f"  {plan.stop_loss.description}")
            summary.append("")
            
            # Take Profits mejorados
            summary.append("🎯 TAKE PROFITS ADAPTATIVOS:")
            for i, exit in enumerate(plan.exits, 1):
                summary.append(f"  {i}. ${exit.price:.2f} ({exit.percentage}%) - {exit.risk_reward:.1f}R")
                summary.append(f"     {exit.description}")
                if exit.confidence:
                    summary.append(f"     Confianza: {exit.confidence:.1f}%")
                if exit.technical_basis:
                    summary.append(f"     Base: {', '.join(exit.technical_basis[:2])}")  # Mostrar solo 2 razones
                summary.append("")
            
            summary.append("=" * 70)
            
            return "\n".join(summary)
            
        except Exception as e:
            logger.error(f"❌ Error formateando resumen V3: {e}")
            return f"Error generando resumen V3 para {plan.symbol}"


# =============================================================================
# 🧪 FUNCIONES DE TESTING Y COMPARACIÓN
# =============================================================================

def test_position_calculator_v3():
    """Test completo del calculador V3.0"""
    print("🧪 TESTING POSITION CALCULATOR V3.0")
    print("=" * 70)
    
    try:
        # Crear calculadora V3
        calculator = PositionCalculatorV3()
        
        # Crear datos simulados
        import pandas as pd
        import numpy as np
        
        # DataFrame simulado con datos OHLCV
        dates = pd.date_range(start='2024-01-01', periods=100, freq='15min')
        np.random.seed(42)
        
        base_price = 230.0
        returns = np.random.normal(0, 0.01, 100)
        prices = [base_price]
        
        for ret in returns[1:]:
            prices.append(prices[-1] * (1 + ret))
        
        market_data = pd.DataFrame({
            'Open': prices,
            'High': [p * 1.005 for p in prices],
            'Low': [p * 0.995 for p in prices],
            'Close': prices,
            'Volume': np.random.randint(1000000, 5000000, 100)
        }, index=dates)
        
        # Indicadores simulados
        indicators = {
            'macd': {'histogram': 0.15, 'signal_strength': 20},
            'rsi': {'rsi': 35, 'signal_strength': 18},
            'vwap': {'vwap': base_price * 1.01, 'deviation_pct': 1.0, 'signal_strength': 15},
            'roc': {'roc': 2.5, 'signal_strength': 18},
            'bollinger': {
                'upper_band': base_price * 1.02,
                'lower_band': base_price * 0.98,
                'signal_strength': 15
            },
            'volume_osc': {'signal_strength': 8},
            'atr': {'atr': base_price * 0.015, 'volatility_level': 'NORMAL'}
        }
        
        # Test señal LONG
        print("📈 Test señal LONG V3.0:")
        plan_v3 = calculator.calculate_position_plan_v3(
            symbol="AAPL",
            direction="LONG",
            current_price=base_price,
            signal_strength=85,
            indicators=indicators,
            market_data=market_data,
            account_balance=10000
        )
        
        # Mostrar resumen
        summary = calculator.format_position_summary_v3(plan_v3)
        print(summary)
        
        print("\n✅ Test V3.0 completado exitosamente!")
        
        # Comparar con métricas clave
        print(f"\n📊 MÉTRICAS CLAVE:")
        print(f"  • R:R Máximo: {plan_v3.max_risk_reward}")
        print(f"  • R:R Promedio: {plan_v3.avg_risk_reward}")
        print(f"  • Targets adaptativos: {len(plan_v3.exits)}")
        print(f"  • Confianza: {plan_v3.confidence_level}")
        
        return plan_v3
        
    except Exception as e:
        print(f"❌ Error en test V3.0: {e}")
        return None

def compare_v2_vs_v3():
    """Comparar sistema V2 vs V3"""
    print("⚖️ COMPARACIÓN SISTEMA V2.0 vs V3.0")
    print("=" * 70)
    
    print("🔴 SISTEMA V2.0 (ANTERIOR):")
    print("  ❌ Targets fijos irreales (hasta 10R)")
    print("  ❌ Solo ajuste básico por ROC (+/-20%)")
    print("  ❌ No considera resistencias/soportes reales")
    print("  ❌ Distribución fija de salidas")
    print("  ❌ Stop loss básico solo con ATR")
    print("  ❌ Confianza solo por signal strength")
    print()
    
    print("🟢 SISTEMA V3.0 (NUEVO):")
    print("  ✅ Targets adaptativos basados en análisis técnico REAL")
    print("  ✅ Máximo R:R realista por estrategia:")
    print("    • Scalping: Max 3R")
    print("    • Swing corto: Max 5R") 
    print("    • Swing medio: Max 6R")
    print("    • Posicional: Max 6R (antes 10R irreal)")
    print()
    print("  ✅ Análisis técnico orgánico:")
    print("    • Resistencias/Soportes por pivots")
    print("    • Fibonacci automático")
    print("    • Bollinger Bands como targets")
    print("    • VWAP institucional")
    print("    • Niveles psicológicos")
    print("    • Extensiones ATR realistas")
    print()
    print("  ✅ Validación inteligente:")
    print("    • Filtros por R:R mínimo/máximo")
    print("    • Validación direccional")
    print("    • Límites de distancia razonables")
    print()
    print("  ✅ Métricas mejoradas:")
    print("    • R:R promedio ponderado")
    print("    • Confianza multicriteria")
    print("    • Análisis contextual completo")
    print("    • Stop loss con contexto técnico")
    print()
    
    print("🎯 BENEFICIOS ESPERADOS:")
    print("  📈 Mayor tasa de éxito en targets")
    print("  🎯 Targets más realistas y alcanzables")
    print("  💰 Mejor gestión de riesgo")
    print("  🔄 Adaptación automática al contexto")
    print("  📊 Decisiones basadas en análisis técnico real")

if __name__ == "__main__":
    print("🎯 POSITION CALCULATOR V3.0 - TARGETS ADAPTATIVOS")
    print("=" * 70)
    print("1. Test Position Calculator V3.0")
    print("2. Comparación V2.0 vs V3.0")
    print("3. Test completo (ambos)")
    
    choice = input("\nElige una opción (1-3): ").strip()
    
    if choice == '1':
        test_position_calculator_v3()
    elif choice == '2':
        compare_v2_vs_v3()
    elif choice == '3':
        test_position_calculator_v3()
        print("\n" + "="*80 + "\n")
        compare_v2_vs_v3()
    else:
        print("❌ Opción no válida")