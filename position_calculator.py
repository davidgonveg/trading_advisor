#!/usr/bin/env python3
"""
💰 SISTEMA DE GESTIÓN DE POSICIONES - TRADING AUTOMATIZADO V2.0
==============================================================

Sistema adaptativo de cálculo de posiciones que ajusta:
- Número de entradas según calidad de señal
- Distribución de tamaños según volatilidad
- Take profits según momentum
- Stop loss dinámico basado en ATR
"""

import logging
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime
import numpy as np

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class PositionLevel:
    """Representa un nivel de entrada o salida"""
    level_type: str  # 'ENTRY' o 'EXIT'
    price: float
    percentage: float  # % del capital total a usar
    description: str
    trigger_condition: str = ""

@dataclass
class PositionPlan:
    """Plan completo de posición"""
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
    
    # Métricas
    max_risk_reward: float
    expected_hold_time: str
    confidence_level: str

class PositionCalculator:
    """
    Calculadora de posiciones adaptativa
    """
    
    def __init__(self):
        """Inicializar calculadora con estrategias definidas"""
        
        # Estrategias según calidad de señal
        self.strategies = {
            'SCALP': {
                'signal_threshold': 85,
                'max_entries': 2,
                'base_risk': 1.0,
                'target_multipliers': [1.5, 2.5],
                'time_horizon': '15-45 min',
                'description': 'Señal muy fuerte - Scalping agresivo'
            },
            'SWING_SHORT': {
                'signal_threshold': 75,
                'max_entries': 3,
                'base_risk': 1.2,
                'target_multipliers': [2.0, 3.5, 5.0],
                'time_horizon': '2-8 horas',
                'description': 'Señal buena - Swing corto'
            },
            'SWING_MEDIUM': {
                'signal_threshold': 65,
                'max_entries': 3,
                'base_risk': 1.5,
                'target_multipliers': [2.5, 4.0, 6.0],
                'time_horizon': '4-24 horas',
                'description': 'Señal moderada - Swing medio'
            },
            'POSITION': {
                'signal_threshold': 50,
                'max_entries': 4,
                'base_risk': 0.8,
                'target_multipliers': [3.0, 5.0, 8.0, 12.0],
                'time_horizon': '1-5 días',
                'description': 'Señal débil - Trading posicional'
            }
        }
        
        # Configuración de volatilidad
        self.volatility_adjustments = {
            'LOW': {'atr_multiplier': 0.8, 'risk_reduction': 0.9},
            'NORMAL': {'atr_multiplier': 1.0, 'risk_reduction': 1.0},
            'HIGH': {'atr_multiplier': 1.2, 'risk_reduction': 1.1},
            'VERY_HIGH': {'atr_multiplier': 1.5, 'risk_reduction': 1.3}
        }
    
    def determine_strategy(self, signal_strength: int, indicators: Dict) -> str:
        """
        Determinar estrategia según señal y condiciones
        """
        try:
            # RSI para contexto
            rsi = indicators.get('rsi', {}).get('rsi', 50)
            
            # ROC para momentum
            roc = indicators.get('roc', {}).get('roc', 0)
            
            # Volatilidad
            volatility = indicators.get('atr', {}).get('volatility_level', 'NORMAL')
            
            # Ajustar signal_strength según contexto
            adjusted_strength = signal_strength
            
            # Reducir si momentum es bajo
            if abs(roc) < 1.0:
                adjusted_strength -= 10
            
            # Reducir si volatilidad muy alta
            if volatility == 'VERY_HIGH':
                adjusted_strength -= 15
            
            # Aumentar si momentum muy fuerte
            if abs(roc) > 3.0:
                adjusted_strength += 10
            
            # Seleccionar estrategia
            if adjusted_strength >= 85:
                return 'SCALP'
            elif adjusted_strength >= 75:
                return 'SWING_SHORT'
            elif adjusted_strength >= 65:
                return 'SWING_MEDIUM'
            else:
                return 'POSITION'
                
        except Exception as e:
            logger.error(f"Error determinando estrategia: {e}")
            return 'SWING_MEDIUM'  # Default seguro
    
    def calculate_entry_levels(self, 
                              current_price: float, 
                              atr: float, 
                              direction: str, 
                              strategy: Dict,
                              volatility: str) -> List[PositionLevel]:
        """
        Calcular niveles de entrada escalonados
        """
        try:
            entries = []
            max_entries = strategy['max_entries']
            vol_adj = self.volatility_adjustments[volatility]['atr_multiplier']
            
            if direction == 'LONG':
                # Entradas en retrocesos para LONG
                if max_entries == 2:
                    # Scalping - solo 2 entradas rápidas
                    prices = [
                        current_price,
                        current_price - (atr * 0.3 * vol_adj)
                    ]
                    percentages = [60, 40]
                    descriptions = [
                        "Entrada inmediata - Breakout",
                        "Entrada en retroceso - Dip buy"
                    ]
                
                elif max_entries == 3:
                    # Swing - 3 entradas graduales
                    prices = [
                        current_price,
                        current_price - (atr * 0.5 * vol_adj),
                        current_price - (atr * 1.0 * vol_adj)
                    ]
                    percentages = [40, 35, 25]
                    descriptions = [
                        "Entrada 1 - Confirmación inicial",
                        "Entrada 2 - Retroceso menor",
                        "Entrada 3 - Retroceso mayor"
                    ]
                
                else:  # max_entries == 4 (POSITION)
                    # Trading posicional - 4 entradas muy graduales
                    prices = [
                        current_price,
                        current_price - (atr * 0.4 * vol_adj),
                        current_price - (atr * 0.8 * vol_adj),
                        current_price - (atr * 1.2 * vol_adj)
                    ]
                    percentages = [30, 30, 25, 15]
                    descriptions = [
                        "Entrada 1 - Test inicial",
                        "Entrada 2 - Retroceso leve",
                        "Entrada 3 - Soporte técnico",
                        "Entrada 4 - Value zone"
                    ]
                    
            else:  # SHORT
                # Entradas en rebotes para SHORT
                if max_entries == 2:
                    prices = [
                        current_price,
                        current_price + (atr * 0.3 * vol_adj)
                    ]
                    percentages = [60, 40]
                    descriptions = [
                        "Entrada inmediata - Breakdown",
                        "Entrada en rebote - Rally fade"
                    ]
                
                elif max_entries == 3:
                    prices = [
                        current_price,
                        current_price + (atr * 0.5 * vol_adj),
                        current_price + (atr * 1.0 * vol_adj)
                    ]
                    percentages = [40, 35, 25]
                    descriptions = [
                        "Entrada 1 - Confirmación bajista",
                        "Entrada 2 - Rebote menor",
                        "Entrada 3 - Rebote mayor"
                    ]
                
                else:  # max_entries == 4
                    prices = [
                        current_price,
                        current_price + (atr * 0.4 * vol_adj),
                        current_price + (atr * 0.8 * vol_adj),
                        current_price + (atr * 1.2 * vol_adj)
                    ]
                    percentages = [30, 30, 25, 15]
                    descriptions = [
                        "Entrada 1 - Test inicial",
                        "Entrada 2 - Rebote leve",
                        "Entrada 3 - Resistencia técnica",
                        "Entrada 4 - Distribution zone"
                    ]
            
            # Crear PositionLevel objects
            for i, (price, pct, desc) in enumerate(zip(prices, percentages, descriptions)):
                entries.append(PositionLevel(
                    level_type='ENTRY',
                    price=round(price, 2),
                    percentage=pct,
                    description=desc,
                    trigger_condition=f"Precio {'<=' if direction == 'LONG' else '>='} {price:.2f}"
                ))
            
            return entries
            
        except Exception as e:
            logger.error(f"Error calculando entradas: {e}")
            return []
    
    def calculate_stop_loss(self, 
                           entry_price: float, 
                           atr: float, 
                           direction: str, 
                           strategy: Dict,
                           volatility: str) -> PositionLevel:
        """
        Calcular stop loss adaptativo
        """
        try:
            vol_adj = self.volatility_adjustments[volatility]['atr_multiplier']
            
            # Stop loss base en ATR
            base_stop_distance = atr * vol_adj
            
            # Ajustar según estrategia
            if strategy == self.strategies['SCALP']:
                stop_multiplier = 0.8  # Stops más ajustados para scalping
            elif strategy == self.strategies['SWING_SHORT']:
                stop_multiplier = 1.0  # Stop normal
            elif strategy == self.strategies['SWING_MEDIUM']:
                stop_multiplier = 1.2  # Stop más amplio
            else:  # POSITION
                stop_multiplier = 1.5  # Stop muy amplio para posicional
            
            stop_distance = base_stop_distance * stop_multiplier
            
            if direction == 'LONG':
                stop_price = entry_price - stop_distance
                description = f"Stop loss dinámico - {stop_distance:.2f} bajo entrada"
            else:
                stop_price = entry_price + stop_distance
                description = f"Stop loss dinámico - {stop_distance:.2f} sobre entrada"
            
            return PositionLevel(
                level_type='STOP',
                price=round(stop_price, 2),
                percentage=100,  # Todo out en stop
                description=description,
                trigger_condition=f"Precio {'<' if direction == 'LONG' else '>'} {stop_price:.2f}"
            )
            
        except Exception as e:
            logger.error(f"Error calculando stop loss: {e}")
            return PositionLevel('STOP', entry_price * 0.98, 100, "Stop de emergencia", "")
    
    def calculate_take_profits(self, 
                              entry_price: float, 
                              stop_price: float, 
                              direction: str, 
                              strategy: Dict,
                              indicators: Dict) -> List[PositionLevel]:
        """
        Calcular take profits adaptativos
        """
        try:
            exits = []
            risk_amount = abs(entry_price - stop_price)
            target_multipliers = strategy['target_multipliers']
            
            # Ajustar targets según momentum
            roc = indicators.get('roc', {}).get('roc', 0)
            momentum_adj = 1.0
            
            if abs(roc) > 3.0:
                momentum_adj = 1.2  # Targets más ambiciosos con momentum fuerte
            elif abs(roc) < 1.0:
                momentum_adj = 0.8  # Targets más conservadores con momentum débil
            
            # Distribución de salidas según estrategia
            if len(target_multipliers) == 2:  # SCALP
                percentages = [60, 40]
                descriptions = [
                    "TP1 - Quick profit",
                    "TP2 - Runner"
                ]
            elif len(target_multipliers) == 3:  # SWING
                percentages = [40, 35, 25]
                descriptions = [
                    "TP1 - Secure profits",
                    "TP2 - Momentum target",
                    "TP3 - Extended target"
                ]
            else:  # POSITION (4 targets)
                percentages = [25, 25, 25, 25]
                descriptions = [
                    "TP1 - Initial target",
                    "TP2 - Intermediate target", 
                    "TP3 - Main target",
                    "TP4 - Maximum target"
                ]
            
            # Calcular precios de take profit
            for i, (multiplier, pct, desc) in enumerate(zip(target_multipliers, percentages, descriptions)):
                adjusted_multiplier = multiplier * momentum_adj
                
                if direction == 'LONG':
                    target_price = entry_price + (risk_amount * adjusted_multiplier)
                else:
                    target_price = entry_price - (risk_amount * adjusted_multiplier)
                
                exits.append(PositionLevel(
                    level_type='EXIT',
                    price=round(target_price, 2),
                    percentage=pct,
                    description=f"{desc} - {adjusted_multiplier:.1f}R",
                    trigger_condition=f"Precio {'>=' if direction == 'LONG' else '<='} {target_price:.2f}"
                ))
            
            return exits
            
        except Exception as e:
            logger.error(f"Error calculando take profits: {e}")
            return []
    
    def calculate_position_plan(self, 
                               symbol: str, 
                               direction: str, 
                               current_price: float, 
                               signal_strength: int, 
                               indicators: Dict,
                               account_balance: float = 10000) -> PositionPlan:
        """
        Calcular plan completo de posición
        """
        try:
            logger.info(f"💰 Calculando plan de posición para {symbol} - {direction}")
            
            # Obtener datos necesarios
            atr = indicators.get('atr', {}).get('atr', current_price * 0.02)
            volatility = indicators.get('atr', {}).get('volatility_level', 'NORMAL')
            
            # Determinar estrategia
            strategy_name = self.determine_strategy(signal_strength, indicators)
            strategy = self.strategies[strategy_name]
            
            # Ajustar riesgo según volatilidad
            vol_risk_adj = self.volatility_adjustments[volatility]['risk_reduction']
            total_risk = strategy['base_risk'] / vol_risk_adj
            
            # Calcular niveles
            entries = self.calculate_entry_levels(
                current_price, atr, direction, strategy, volatility
            )
            
            if not entries:
                raise ValueError("No se pudieron calcular entradas")
            
            # Usar primera entrada como referencia para stop
            main_entry_price = entries[0].price
            stop_loss = self.calculate_stop_loss(
                main_entry_price, atr, direction, strategy, volatility
            )
            
            exits = self.calculate_take_profits(
                main_entry_price, stop_loss.price, direction, strategy, indicators
            )
            
            # Calcular métricas
            risk_amount = abs(main_entry_price - stop_loss.price)
            max_reward = max([abs(exit.price - main_entry_price) for exit in exits]) if exits else risk_amount
            max_rr = max_reward / risk_amount if risk_amount > 0 else 0
            
            # Determinar nivel de confianza
            if signal_strength >= 85:
                confidence = "MUY ALTA"
            elif signal_strength >= 75:
                confidence = "ALTA"
            elif signal_strength >= 65:
                confidence = "MEDIA"
            else:
                confidence = "BAJA"
            
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
                max_risk_reward=round(max_rr, 2),
                expected_hold_time=strategy['time_horizon'],
                confidence_level=confidence
            )
            
            logger.info(f"✅ Plan calculado: {strategy_name} - {confidence} confidence - {max_rr:.1f}R")
            return plan
            
        except Exception as e:
            logger.error(f"❌ Error calculando plan de posición: {e}")
            raise
    
    def format_position_summary(self, plan: PositionPlan, account_balance: float = 10000) -> str:
        """
        Formatear resumen del plan de posición
        """
        try:
            summary = []
            summary.append(f"📋 PLAN DE POSICIÓN - {plan.symbol}")
            summary.append("=" * 60)
            summary.append(f"🎯 Dirección: {plan.direction}")
            summary.append(f"💪 Estrategia: {plan.strategy_type} ({self.strategies[plan.strategy_type]['description']})")
            summary.append(f"🎲 Señal: {plan.signal_strength}/100 - Confianza {plan.confidence_level}")
            summary.append(f"💰 Riesgo total: {plan.total_risk_percent:.1f}% (${account_balance * plan.total_risk_percent / 100:.0f})")
            summary.append(f"⏰ Horizonte: {plan.expected_hold_time}")
            summary.append(f"🎯 R:R máximo: 1:{plan.max_risk_reward}")
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
            
            # Take Profits
            summary.append("🎯 TAKE PROFITS:")
            for i, exit in enumerate(plan.exits, 1):
                risk_reward = abs(exit.price - plan.entries[0].price) / abs(plan.entries[0].price - plan.stop_loss.price)
                summary.append(f"  {i}. ${exit.price:.2f} ({exit.percentage}%) - {risk_reward:.1f}R")
                summary.append(f"     {exit.description}")
            
            summary.append("=" * 60)
            
            return "\n".join(summary)
            
        except Exception as e:
            logger.error(f"Error formateando resumen: {e}")
            return f"Error generando resumen para {plan.symbol}"

def test_position_calculator():
    """
    Test del calculador de posiciones
    """
    print("🧪 TESTING POSITION CALCULATOR")
    print("=" * 60)
    
    # Datos de ejemplo (de nuestro sistema de indicadores)
    test_data = {
        'symbol': 'SPY',
        'current_price': 657.47,
        'direction': 'LONG',
        'signal_strength': 78,
        'indicators': {
            'rsi': {'rsi': 70.5},
            'roc': {'roc': 2.1},
            'atr': {'atr': 0.65, 'volatility_level': 'LOW'}
        }
    }
    
    calculator = PositionCalculator()
    
    try:
        plan = calculator.calculate_position_plan(
            test_data['symbol'],
            test_data['direction'],
            test_data['current_price'],
            test_data['signal_strength'],
            test_data['indicators']
        )
        
        print(calculator.format_position_summary(plan))
        print("\n✅ Test exitoso!")
        
        return plan
        
    except Exception as e:
        print(f"❌ Error en test: {e}")
        return None

if __name__ == "__main__":
    test_position_calculator()