#!/usr/bin/env python3
"""
🎯 SISTEMA DE TAKE PROFITS ADAPTATIVOS V3.0
==========================================

Sistema orgánico que calcula targets basándose en:
- Resistencias/Soportes técnicos reales
- Niveles de Fibonacci automáticos
- Bollinger Bands como targets dinámicos
- Volatilidad del símbolo (ATR)
- Momentum multi-indicador
- Contexto de mercado general

FILOSOFÍA: Cada señal es única, cada target debe ser único.
"""

import numpy as np
import pandas as pd
try:
    import talib
    HAS_TALIB = True
except ImportError:
    HAS_TALIB = False
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)

@dataclass
class TechnicalLevel:
    """Nivel técnico identificado en el precio"""
    price: float
    level_type: str  # 'RESISTANCE', 'SUPPORT', 'FIBONACCI', 'BOLLINGER', 'PSYCHOLOGICAL'
    strength: float  # 0-100, qué tan fuerte es el nivel
    distance_pct: float  # % de distancia desde precio actual
    description: str

@dataclass
class AdaptiveTarget:
    """Target adaptativo calculado orgánicamente"""
    price: float
    percentage_exit: float  # % de posición a cerrar
    risk_reward: float  # Ratio R:R
    confidence: float  # 0-100, confianza en alcanzar el target
    technical_basis: List[str]  # Razones técnicas del target
    description: str

class AdaptiveTakeProfitCalculator:
    """
    Calculadora de take profits orgánicos y adaptativos
    """
    
    def __init__(self):
        self.min_rr = 1.2  # R:R mínimo aceptable
        self.max_rr = 6.0  # R:R máximo realista
        self.lookback_period = 50  # Velas para análisis técnico
    
    def calculate_adaptive_targets(self, 
                                 symbol: str,
                                 data: pd.DataFrame, 
                                 entry_price: float,
                                 stop_price: float,
                                 direction: str,
                                 indicators: Dict,
                                 signal_strength: int) -> List[AdaptiveTarget]:
        """
        Calcular targets adaptativos basados en análisis técnico real
        
        Args:
            symbol: Símbolo del activo
            data: DataFrame con datos OHLCV
            entry_price: Precio de entrada
            stop_price: Precio de stop loss
            direction: 'LONG' o 'SHORT'
            indicators: Dict con indicadores técnicos
            signal_strength: Fuerza de la señal (0-100)
            
        Returns:
            Lista de targets adaptativos ordenados por proximidad
        """
        try:
            logger.info(f"🎯 Calculando targets adaptativos para {symbol} - {direction}")
            
            # 1. Identificar niveles técnicos clave
            technical_levels = self._identify_technical_levels(data, entry_price, direction, indicators)
            
            # 2. Filtrar niveles válidos para targets
            valid_targets = self._filter_valid_targets(
                technical_levels, entry_price, stop_price, direction
            )
            
            # 3. Calcular potencial de cada target
            target_potentials = self._calculate_target_potentials(
                valid_targets, indicators, signal_strength, direction
            )
            
            # 4. Crear targets adaptativos finales
            adaptive_targets = self._create_adaptive_targets(
                target_potentials, entry_price, stop_price, direction
            )
            
            # 5. Optimizar distribución de salidas
            optimized_targets = self._optimize_exit_distribution(adaptive_targets, signal_strength)
            
            logger.info(f"✅ {len(optimized_targets)} targets adaptativos calculados")
            
            return optimized_targets
            
        except Exception as e:
            logger.error(f"❌ Error calculando targets adaptativos: {e}")
            return self._get_fallback_targets(entry_price, stop_price, direction)
    
    def _identify_technical_levels(self, 
                                 data: pd.DataFrame, 
                                 entry_price: float, 
                                 direction: str,
                                 indicators: Dict) -> List[TechnicalLevel]:
        """Identificar niveles técnicos clave en el precio"""
        levels = []
        
        try:
            # 1. RESISTENCIAS Y SOPORTES (Pivots)
            pivot_levels = self._find_pivot_levels(data, direction)
            levels.extend(pivot_levels)
            
            # 2. FIBONACCI RETRACEMENTS
            fib_levels = self._calculate_fibonacci_levels(data, entry_price, direction)
            levels.extend(fib_levels)
            
            # 3. BOLLINGER BANDS COMO TARGETS
            bb_levels = self._get_bollinger_targets(indicators, entry_price, direction)
            levels.extend(bb_levels)
            
            # 4. NIVELES PSICOLÓGICOS (números redondos)
            psych_levels = self._find_psychological_levels(entry_price, direction)
            levels.extend(psych_levels)
            
            # 5. VWAP COMO TARGET DINÁMICO
            vwap_levels = self._get_vwap_targets(indicators, entry_price, direction)
            levels.extend(vwap_levels)
            
            # 6. EXTENSIONES BASADAS EN ATR
            atr_levels = self._calculate_atr_extensions(indicators, entry_price, direction)
            levels.extend(atr_levels)
            
            logger.debug(f"📊 {len(levels)} niveles técnicos identificados")
            return levels
            
        except Exception as e:
            logger.error(f"❌ Error identificando niveles técnicos: {e}")
            return []
    
    def _find_pivot_levels(self, data: pd.DataFrame, direction: str) -> List[TechnicalLevel]:
        """Encontrar niveles de resistencia y soporte basados en pivots"""
        levels = []
        
        try:
            # Usar últimas 50 velas para análisis
            recent_data = data.tail(self.lookback_period)
            highs = recent_data['High'].values
            lows = recent_data['Low'].values
            
            # Encontrar pivots altos (resistencias potenciales)
            for i in range(2, len(highs) - 2):
                if (highs[i] > highs[i-1] and highs[i] > highs[i-2] and 
                    highs[i] > highs[i+1] and highs[i] > highs[i+2]):
                    
                    # Calcular fuerza del nivel (cuántas veces fue testado)
                    level_price = highs[i]
                    tests = self._count_level_tests(data, level_price, tolerance=0.2)
                    strength = min(tests * 20, 100)  # Max 100
                    
                    distance_pct = abs(level_price - recent_data['Close'].iloc[-1]) / recent_data['Close'].iloc[-1] * 100
                    
                    levels.append(TechnicalLevel(
                        price=level_price,
                        level_type='RESISTANCE',
                        strength=strength,
                        distance_pct=distance_pct,
                        description=f"Resistencia pivot ({tests} tests)"
                    ))
            
            # Encontrar pivots bajos (soportes potenciales) 
            for i in range(2, len(lows) - 2):
                if (lows[i] < lows[i-1] and lows[i] < lows[i-2] and 
                    lows[i] < lows[i+1] and lows[i] < lows[i+2]):
                    
                    level_price = lows[i]
                    tests = self._count_level_tests(data, level_price, tolerance=0.2)
                    strength = min(tests * 20, 100)
                    
                    distance_pct = abs(level_price - recent_data['Close'].iloc[-1]) / recent_data['Close'].iloc[-1] * 100
                    
                    levels.append(TechnicalLevel(
                        price=level_price,
                        level_type='SUPPORT',
                        strength=strength,
                        distance_pct=distance_pct,
                        description=f"Soporte pivot ({tests} tests)"
                    ))
            
            return levels
            
        except Exception as e:
            logger.error(f"❌ Error encontrando pivots: {e}")
            return []
    
    def _calculate_fibonacci_levels(self, 
                                  data: pd.DataFrame, 
                                  entry_price: float, 
                                  direction: str) -> List[TechnicalLevel]:
        """Calcular niveles de Fibonacci automáticamente"""
        levels = []
        
        try:
            # Encontrar el swing más relevante (últimos 20-50 períodos)
            recent_data = data.tail(50)
            
            if direction == 'LONG':
                # Para LONG: desde último low significativo hasta high previo
                swing_low = recent_data['Low'].min()
                swing_high = recent_data['High'].max()
                
                # Calcular extensiones Fibonacci (targets al alza)
                fib_levels = [1.236, 1.382, 1.618, 2.618]  # Extensiones comunes
                
                for fib in fib_levels:
                    fib_price = swing_low + (swing_high - swing_low) * fib
                    
                    if fib_price > entry_price:  # Solo targets al alza
                        distance_pct = (fib_price - entry_price) / entry_price * 100
                        
                        levels.append(TechnicalLevel(
                            price=fib_price,
                            level_type='FIBONACCI',
                            strength=80,  # Fibonacci tiene alta confianza
                            distance_pct=distance_pct,
                            description=f"Fibonacci {fib:.3f} extension"
                        ))
            
            else:  # SHORT
                # Para SHORT: desde último high significativo hasta low previo
                swing_high = recent_data['High'].max()
                swing_low = recent_data['Low'].min()
                
                fib_levels = [1.236, 1.382, 1.618, 2.618]
                
                for fib in fib_levels:
                    fib_price = swing_high - (swing_high - swing_low) * fib
                    
                    if fib_price < entry_price:  # Solo targets a la baja
                        distance_pct = (entry_price - fib_price) / entry_price * 100
                        
                        levels.append(TechnicalLevel(
                            price=fib_price,
                            level_type='FIBONACCI',
                            strength=80,
                            distance_pct=distance_pct,
                            description=f"Fibonacci {fib:.3f} extension"
                        ))
            
            return levels
            
        except Exception as e:
            logger.error(f"❌ Error calculando Fibonacci: {e}")
            return []
    
    def _get_bollinger_targets(self, 
                             indicators: Dict, 
                             entry_price: float, 
                             direction: str) -> List[TechnicalLevel]:
        """Usar Bollinger Bands como targets dinámicos"""
        levels = []
        
        try:
            bb_data = indicators.get('bollinger', {})
            
            if direction == 'LONG':
                # Para LONG: banda superior como target
                upper_band = bb_data.get('upper_band', 0)
                if upper_band > entry_price:
                    distance_pct = (upper_band - entry_price) / entry_price * 100
                    
                    levels.append(TechnicalLevel(
                        price=upper_band,
                        level_type='BOLLINGER',
                        strength=75,
                        distance_pct=distance_pct,
                        description="Bollinger banda superior"
                    ))
            
            else:  # SHORT
                # Para SHORT: banda inferior como target
                lower_band = bb_data.get('lower_band', 0)
                if lower_band < entry_price:
                    distance_pct = (entry_price - lower_band) / entry_price * 100
                    
                    levels.append(TechnicalLevel(
                        price=lower_band,
                        level_type='BOLLINGER',
                        strength=75,
                        distance_pct=distance_pct,
                        description="Bollinger banda inferior"
                    ))
            
            return levels
            
        except Exception as e:
            logger.error(f"❌ Error calculando targets Bollinger: {e}")
            return []
    
    def _find_psychological_levels(self, 
                                 entry_price: float, 
                                 direction: str) -> List[TechnicalLevel]:
        """Encontrar niveles psicológicos (números redondos)"""
        levels = []
        
        try:
            # Niveles psicológicos comunes (números redondos)
            if entry_price > 100:
                # Para precios > $100: múltiplos de $5 y $10
                round_levels = [5, 10]
            elif entry_price > 50:
                # Para precios $50-100: múltiplos de $2.50 y $5
                round_levels = [2.5, 5]
            else:
                # Para precios < $50: múltiplos de $1 y $2.50
                round_levels = [1, 2.5]
            
            for round_val in round_levels:
                if direction == 'LONG':
                    # Buscar niveles redondos por encima
                    target_level = ((entry_price // round_val) + 1) * round_val
                    while target_level <= entry_price + (entry_price * 0.15):  # Max 15% away
                        distance_pct = (target_level - entry_price) / entry_price * 100
                        
                        levels.append(TechnicalLevel(
                            price=target_level,
                            level_type='PSYCHOLOGICAL',
                            strength=60,
                            distance_pct=distance_pct,
                            description=f"Nivel psicológico ${target_level:.2f}"
                        ))
                        
                        target_level += round_val
                
                else:  # SHORT
                    # Buscar niveles redondos por debajo
                    target_level = (entry_price // round_val) * round_val
                    while target_level >= entry_price - (entry_price * 0.15):  # Max 15% away
                        if target_level < entry_price:
                            distance_pct = (entry_price - target_level) / entry_price * 100
                            
                            levels.append(TechnicalLevel(
                                price=target_level,
                                level_type='PSYCHOLOGICAL',
                                strength=60,
                                distance_pct=distance_pct,
                                description=f"Nivel psicológico ${target_level:.2f}"
                            ))
                        
                        target_level -= round_val
            
            return levels
            
        except Exception as e:
            logger.error(f"❌ Error calculando niveles psicológicos: {e}")
            return []
    
    def _get_vwap_targets(self, 
                        indicators: Dict, 
                        entry_price: float, 
                        direction: str) -> List[TechnicalLevel]:
        """VWAP como target dinámico"""
        levels = []
        
        try:
            vwap_data = indicators.get('vwap', {})
            vwap_price = vwap_data.get('vwap', 0)
            
            if direction == 'LONG' and vwap_price > entry_price:
                # VWAP como target para LONG
                distance_pct = (vwap_price - entry_price) / entry_price * 100
                
                levels.append(TechnicalLevel(
                    price=vwap_price,
                    level_type='VWAP',
                    strength=85,  # VWAP muy confiable
                    distance_pct=distance_pct,
                    description="VWAP como target"
                ))
            
            elif direction == 'SHORT' and vwap_price < entry_price:
                # VWAP como target para SHORT
                distance_pct = (entry_price - vwap_price) / entry_price * 100
                
                levels.append(TechnicalLevel(
                    price=vwap_price,
                    level_type='VWAP',
                    strength=85,
                    distance_pct=distance_pct,
                    description="VWAP como target"
                ))
            
            return levels
            
        except Exception as e:
            logger.error(f"❌ Error calculando targets VWAP: {e}")
            return []
    
    def _calculate_atr_extensions(self, 
                                indicators: Dict, 
                                entry_price: float, 
                                direction: str) -> List[TechnicalLevel]:
        """Calcular extensiones basadas en ATR (volatilidad real)"""
        levels = []
        
        try:
            atr_data = indicators.get('atr', {})
            atr_value = atr_data.get('atr', entry_price * 0.02)  # Default 2%
            
            # Múltiplos de ATR realistas para targets
            atr_multipliers = [2, 3, 4, 6]  # Más conservador que antes
            
            for multiplier in atr_multipliers:
                if direction == 'LONG':
                    target_price = entry_price + (atr_value * multiplier)
                else:
                    target_price = entry_price - (atr_value * multiplier)
                
                distance_pct = abs(target_price - entry_price) / entry_price * 100
                
                # Ajustar fuerza según multiplier (menos fuerza = más lejos)
                strength = max(90 - (multiplier * 10), 50)
                
                levels.append(TechnicalLevel(
                    price=target_price,
                    level_type='ATR_EXTENSION',
                    strength=strength,
                    distance_pct=distance_pct,
                    description=f"ATR {multiplier}x extension"
                ))
            
            return levels
            
        except Exception as e:
            logger.error(f"❌ Error calculando extensiones ATR: {e}")
            return []
    
    def _filter_valid_targets(self, 
                            levels: List[TechnicalLevel], 
                            entry_price: float, 
                            stop_price: float, 
                            direction: str) -> List[TechnicalLevel]:
        """Filtrar solo niveles válidos para targets"""
        valid_targets = []
        risk_amount = abs(entry_price - stop_price)
        
        for level in levels:
            try:
                # Calcular R:R potencial
                reward = abs(level.price - entry_price)
                rr_ratio = reward / risk_amount if risk_amount > 0 else 0
                
                # Filtros de validez
                is_valid = True
                
                # 1. R:R mínimo
                if rr_ratio < self.min_rr:
                    is_valid = False
                
                # 2. R:R máximo realista
                if rr_ratio > self.max_rr:
                    is_valid = False
                
                # 3. Dirección correcta
                if direction == 'LONG' and level.price <= entry_price:
                    is_valid = False
                elif direction == 'SHORT' and level.price >= entry_price:
                    is_valid = False
                
                # 4. Distancia razonable (no más de 10% para scalping, 20% para swing)
                if level.distance_pct > 20:
                    is_valid = False
                
                if is_valid:
                    valid_targets.append(level)
            
            except Exception as e:
                logger.warning(f"⚠️ Error validando nivel {level.price}: {e}")
                continue
        
        # Ordenar por R:R (más conservador primero)
        valid_targets.sort(key=lambda x: abs(x.price - entry_price))
        
        logger.debug(f"✅ {len(valid_targets)} targets válidos después de filtros")
        return valid_targets[:6]  # Max 6 targets
    
    def _calculate_target_potentials(self, 
                                   levels: List[TechnicalLevel], 
                                   indicators: Dict, 
                                   signal_strength: int,
                                   direction: str) -> List[Dict]:
        """Calcular potencial de cada target basado en contexto de mercado"""
        potentials = []
        
        for level in levels:
            try:
                # Score base por tipo de nivel
                type_scores = {
                    'FIBONACCI': 90,
                    'VWAP': 85,
                    'RESISTANCE': 80,
                    'SUPPORT': 80,
                    'BOLLINGER': 75,
                    'PSYCHOLOGICAL': 65,
                    'ATR_EXTENSION': 60
                }
                
                base_score = type_scores.get(level.level_type, 50)
                
                # Ajustar por fuerza del nivel técnico
                strength_adj = level.strength / 100
                
                # Ajustar por momentum (ROC + RSI)
                momentum_adj = self._calculate_momentum_adjustment(indicators, direction)
                
                # Ajustar por distancia (más cerca = más probable)
                distance_adj = max(0.5, 1 - (level.distance_pct / 100))
                
                # Ajustar por fuerza de señal original
                signal_adj = signal_strength / 100
                
                # Score final
                final_score = base_score * strength_adj * momentum_adj * distance_adj * signal_adj
                
                potentials.append({
                    'level': level,
                    'score': final_score,
                    'base_score': base_score,
                    'adjustments': {
                        'strength': strength_adj,
                        'momentum': momentum_adj,
                        'distance': distance_adj,
                        'signal': signal_adj
                    }
                })
            
            except Exception as e:
                logger.warning(f"⚠️ Error calculando potencial para {level.price}: {e}")
                continue
        
        # Ordenar por score (mejores primero)
        potentials.sort(key=lambda x: x['score'], reverse=True)
        
        return potentials
    
    def _calculate_momentum_adjustment(self, indicators: Dict, direction: str) -> float:
        """Calcular ajuste por momentum multi-indicador"""
        try:
            adjustments = []
            
            # ROC adjustment
            roc_data = indicators.get('roc', {})
            roc_value = roc_data.get('roc', 0)
            
            if direction == 'LONG':
                if roc_value > 3:
                    adjustments.append(1.3)  # Momentum muy fuerte
                elif roc_value > 1.5:
                    adjustments.append(1.1)  # Momentum bueno
                elif roc_value > 0:
                    adjustments.append(1.0)  # Momentum neutro
                else:
                    adjustments.append(0.8)  # Momentum negativo
            else:  # SHORT
                if roc_value < -3:
                    adjustments.append(1.3)
                elif roc_value < -1.5:
                    adjustments.append(1.1)
                elif roc_value < 0:
                    adjustments.append(1.0)
                else:
                    adjustments.append(0.8)
            
            # RSI adjustment (para confirmar momentum)
            rsi_data = indicators.get('rsi', {})
            rsi_value = rsi_data.get('rsi', 50)
            
            if direction == 'LONG':
                if rsi_value < 30:
                    adjustments.append(1.2)  # Muy oversold = buen potencial
                elif rsi_value < 50:
                    adjustments.append(1.1)
                else:
                    adjustments.append(0.9)  # Ya overbought
            else:  # SHORT
                if rsi_value > 70:
                    adjustments.append(1.2)  # Muy overbought = buen potencial
                elif rsi_value > 50:
                    adjustments.append(1.1)
                else:
                    adjustments.append(0.9)  # Ya oversold
            
            # Promedio de ajustes
            return sum(adjustments) / len(adjustments) if adjustments else 1.0
            
        except Exception as e:
            logger.warning(f"⚠️ Error calculando ajuste momentum: {e}")
            return 1.0
    
    def _create_adaptive_targets(self, 
                               potentials: List[Dict], 
                               entry_price: float, 
                               stop_price: float, 
                               direction: str) -> List[AdaptiveTarget]:
        """Crear targets adaptativos finales"""
        targets = []
        risk_amount = abs(entry_price - stop_price)
        
        # Tomar los mejores 3-4 targets
        best_potentials = potentials[:4]
        
        for i, potential in enumerate(best_potentials):
            try:
                level = potential['level']
                score = potential['score']
                
                # Calcular R:R
                reward = abs(level.price - entry_price)
                rr_ratio = reward / risk_amount if risk_amount > 0 else 0
                
                # Calcular confianza (0-100)
                confidence = min(score, 100)
                
                # Basar descripción en análisis técnico
                technical_reasons = [level.description]
                if level.level_type == 'FIBONACCI':
                    technical_reasons.append("Nivel Fibonacci histórico")
                elif level.level_type == 'RESISTANCE':
                    technical_reasons.append("Resistencia técnica probada")
                elif level.level_type == 'VWAP':
                    technical_reasons.append("Referencia institucional")
                
                targets.append(AdaptiveTarget(
                    price=round(level.price, 2),
                    percentage_exit=0,  # Se asignará después
                    risk_reward=round(rr_ratio, 2),
                    confidence=round(confidence, 1),
                    technical_basis=technical_reasons,
                    description=f"Target {i+1}: {level.description} ({rr_ratio:.1f}R)"
                ))
            
            except Exception as e:
                logger.warning(f"⚠️ Error creando target adaptativo: {e}")
                continue
        
        return targets
    
    def _optimize_exit_distribution(self, 
                                  targets: List[AdaptiveTarget], 
                                  signal_strength: int) -> List[AdaptiveTarget]:
        """Optimizar distribución de salidas según fuerza de señal"""
        try:
            if not targets:
                return targets
            
            # Distribuciones según calidad de señal
            if signal_strength >= 85:
                # Scalping: salidas rápidas
                if len(targets) >= 2:
                    targets[0].percentage_exit = 70  # Asegurar beneficios rápido
                    targets[1].percentage_exit = 30  # Runner pequeño
                else:
                    targets[0].percentage_exit = 100
            
            elif signal_strength >= 75:
                # Swing corto: distribución equilibrada
                if len(targets) >= 3:
                    targets[0].percentage_exit = 50
                    targets[1].percentage_exit = 35
                    targets[2].percentage_exit = 15
                elif len(targets) == 2:
                    targets[0].percentage_exit = 60
                    targets[1].percentage_exit = 40
                else:
                    targets[0].percentage_exit = 100
            
            else:
                # Swing medio/largo: más distribución
                if len(targets) >= 4:
                    targets[0].percentage_exit = 40
                    targets[1].percentage_exit = 30
                    targets[2].percentage_exit = 20
                    targets[3].percentage_exit = 10
                elif len(targets) >= 3:
                    targets[0].percentage_exit = 45
                    targets[1].percentage_exit = 35
                    targets[2].percentage_exit = 20
                elif len(targets) == 2:
                    targets[0].percentage_exit = 65
                    targets[1].percentage_exit = 35
                else:
                    targets[0].percentage_exit = 100
            
            return targets
            
        except Exception as e:
            logger.error(f"❌ Error optimizando distribución: {e}")
            return targets
    
    def _count_level_tests(self, data: pd.DataFrame, level_price: float, tolerance: float = 0.2) -> int:
        """Contar cuántas veces un nivel fue testado"""
        try:
            # Buscar cuántas veces el precio tocó este nivel
            tests = 0
            tolerance_amount = level_price * (tolerance / 100)
            
            for _, row in data.iterrows():
                if (level_price - tolerance_amount <= row['High'] <= level_price + tolerance_amount or
                    level_price - tolerance_amount <= row['Low'] <= level_price + tolerance_amount):
                    tests += 1
            
            return tests
            
        except Exception as e:
            logger.warning(f"⚠️ Error contando tests de nivel: {e}")
            return 1
    
    def _get_fallback_targets(self, 
                            entry_price: float, 
                            stop_price: float, 
                            direction: str) -> List[AdaptiveTarget]:
        """Targets de respaldo si falla el análisis técnico"""
        try:
            risk_amount = abs(entry_price - stop_price)
            fallback_targets = []
            
            # Targets conservadores basados solo en R:R
            rr_ratios = [1.5, 2.5, 4.0]  # Mucho más realista que antes
            percentages = [60, 30, 10]
            
            for i, (rr, pct) in enumerate(zip(rr_ratios, percentages)):
                if direction == 'LONG':
                    target_price = entry_price + (risk_amount * rr)
                else:
                    target_price = entry_price - (risk_amount * rr)
                
                fallback_targets.append(AdaptiveTarget(
                    price=round(target_price, 2),
                    percentage_exit=pct,
                    risk_reward=rr,
                    confidence=60.0,  # Confianza media para fallback
                    technical_basis=["R:R conservador"],
                    description=f"Fallback target {i+1}: {rr}R"
                ))
            
            return fallback_targets
            
        except Exception as e:
            logger.error(f"❌ Error creando targets fallback: {e}")
            return []

    def format_adaptive_targets_summary(self, 
                                      targets: List[AdaptiveTarget], 
                                      entry_price: float,
                                      symbol: str) -> str:
        """Formatear resumen de targets adaptativos para mostrar"""
        try:
            if not targets:
                return "❌ No se pudieron calcular targets adaptativos"
            
            summary = []
            summary.append(f"🎯 TARGETS ADAPTATIVOS - {symbol}")
            summary.append("=" * 60)
            summary.append(f"💰 Precio entrada: ${entry_price:.2f}")
            summary.append("")
            
            total_percentage = 0
            for i, target in enumerate(targets, 1):
                total_percentage += target.percentage_exit
                
                summary.append(f"🎯 TARGET {i}: ${target.price:.2f} ({target.percentage_exit}%)")
                summary.append(f"   📊 R:R: 1:{target.risk_reward}")
                summary.append(f"   🎲 Confianza: {target.confidence:.1f}%")
                summary.append(f"   📈 Base técnica: {', '.join(target.technical_basis)}")
                summary.append("")
            
            summary.append(f"✅ Total distribución: {total_percentage}%")
            summary.append("=" * 60)
            
            return "\n".join(summary)
            
        except Exception as e:
            logger.error(f"❌ Error formateando resumen: {e}")
            return f"❌ Error generando resumen para {symbol}"


# =============================================================================
# 🧪 FUNCIONES DE TESTING Y DEMO
# =============================================================================

def test_adaptive_calculator():
    """Test del calculador adaptativo"""
    print("🧪 TESTING ADAPTIVE TAKE PROFIT CALCULATOR")
    print("=" * 60)
    
    try:
        # Crear calculadora
        calculator = AdaptiveTakeProfitCalculator()
        
        # Datos de ejemplo (simular datos reales)
        import pandas as pd
        import numpy as np
        
        # Crear DataFrame simulado con datos OHLCV
        dates = pd.date_range(start='2024-01-01', periods=100, freq='15min')
        np.random.seed(42)  # Para resultados reproducibles
        
        base_price = 230.0
        returns = np.random.normal(0, 0.01, 100)  # Retornos aleatorios
        prices = [base_price]
        
        for ret in returns[1:]:
            prices.append(prices[-1] * (1 + ret))
        
        # Crear OHLCV simulado
        data = pd.DataFrame({
            'Open': prices,
            'High': [p * 1.005 for p in prices],  # High ligeramente superior
            'Low': [p * 0.995 for p in prices],   # Low ligeramente inferior  
            'Close': prices,
            'Volume': np.random.randint(1000000, 5000000, 100)
        }, index=dates)
        
        # Indicadores simulados
        indicators = {
            'bollinger': {
                'upper_band': base_price * 1.02,
                'lower_band': base_price * 0.98,
                'middle_band': base_price
            },
            'vwap': {
                'vwap': base_price * 1.01
            },
            'roc': {
                'roc': 2.5  # Momentum alcista fuerte
            },
            'rsi': {
                'rsi': 35  # Oversold
            },
            'atr': {
                'atr': base_price * 0.015  # 1.5% de volatilidad
            }
        }
        
        # Test para señal LONG
        print("📈 Test señal LONG:")
        entry_price = base_price
        stop_price = base_price * 0.98  # Stop 2% abajo
        
        adaptive_targets = calculator.calculate_adaptive_targets(
            symbol="AAPL",
            data=data,
            entry_price=entry_price,
            stop_price=stop_price,
            direction="LONG",
            indicators=indicators,
            signal_strength=85
        )
        
        # Mostrar resultados
        summary = calculator.format_adaptive_targets_summary(
            adaptive_targets, entry_price, "AAPL"
        )
        print(summary)
        
        print("\n" + "="*60)
        
        # Test para señal SHORT
        print("📉 Test señal SHORT:")
        entry_price = base_price
        stop_price = base_price * 1.02  # Stop 2% arriba
        
        adaptive_targets_short = calculator.calculate_adaptive_targets(
            symbol="AAPL",
            data=data,
            entry_price=entry_price,
            stop_price=stop_price,
            direction="SHORT",
            indicators=indicators,
            signal_strength=75
        )
        
        summary_short = calculator.format_adaptive_targets_summary(
            adaptive_targets_short, entry_price, "AAPL (SHORT)"
        )
        print(summary_short)
        
        print("\n✅ Test completado exitosamente!")
        return True
        
    except Exception as e:
        print(f"❌ Error en test: {e}")
        return False

def compare_old_vs_new_targets():
    """Comparar sistema anterior vs nuevo"""
    print("⚖️ COMPARACIÓN: SISTEMA ANTERIOR VS NUEVO")
    print("=" * 60)
    
    print("🔴 SISTEMA ANTERIOR (Problemático):")
    print("   • Targets fijos: 1.5R, 2.5R, 5.0R, 10.0R")
    print("   • 10R = Objetivo irreal (< 5% probabilidad)")
    print("   • Solo ajuste por ROC (+/-20%)")
    print("   • Ignora resistencias/soportes reales")
    print("   • No considera contexto de mercado")
    print("   • Distribución fija de salidas")
    print()
    
    print("🟢 SISTEMA NUEVO (Adaptativo):")
    print("   • Targets basados en análisis técnico REAL:")
    print("     - Resistencias/Soportes (pivots históricos)")
    print("     - Fibonacci automático (extensiones)")
    print("     - Bollinger Bands dinámicas")
    print("     - VWAP como referencia institucional")
    print("     - Niveles psicológicos (números redondos)")
    print("     - Extensiones ATR realistas (2x-6x)")
    print()
    print("   • Filtros inteligentes:")
    print("     - R:R mínimo: 1.2 (realista)")
    print("     - R:R máximo: 6.0 (alcanzable)")
    print("     - Validación direccional")
    print("     - Límite distancia (máx 20%)")
    print()
    print("   • Score multicriteria:")
    print("     - Fuerza del nivel técnico")
    print("     - Momentum multi-indicador (ROC + RSI)")
    print("     - Proximidad del target")
    print("     - Calidad señal original")
    print()
    print("   • Distribución adaptativa:")
    print("     - Scalping (85+ pts): 70% + 30%")
    print("     - Swing corto (75+ pts): 50% + 35% + 15%")
    print("     - Swing medio (65+ pts): 45% + 35% + 20%")
    print()
    
    print("🎯 RESULTADOS ESPERADOS:")
    print("   • Targets más realistas y alcanzables")
    print("   • Mayor tasa de éxito en TPs")
    print("   • Mejor gestión de riesgo")
    print("   • Adaptación automática al contexto")
    print("   • Targets únicos para cada señal")

if __name__ == "__main__":
    print("🎯 ADAPTIVE TAKE PROFIT CALCULATOR V3.0")
    print("=" * 60)
    print("1. Test básico del calculador")
    print("2. Comparación sistema anterior vs nuevo")
    print("3. Ambos tests")
    
    choice = input("\nElige una opción (1-3): ").strip()
    
    if choice == '1':
        test_adaptive_calculator()
    elif choice == '2':
        compare_old_vs_new_targets()
    elif choice == '3':
        test_adaptive_calculator()
        print("\n" + "="*80 + "\n")
        compare_old_vs_new_targets()
    else:
        print("Opción no válida")