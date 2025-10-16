#!/usr/bin/env python3
"""
🧮 CALCULATOR ENHANCER - PARTIAL EXECUTION RECALCULATION V3.0
============================================================

Enhancer que extiende position_calculator.py para manejar recálculos inteligentes
de niveles restantes basado en ejecuciones parciales reales del mercado.

🎯 FUNCIONALIDADES CLAVE:
1. Recálculo dinámico de position sizing para niveles no ejecutados
2. Ajuste de risk management basado en niveles ya ejecutados  
3. Optimización de DCA levels considerando precio promedio actual
4. Rebalanceo inteligente de Take Profits y Stop Loss
5. Preservación del risk management original en términos absolutos

🔧 CASOS DE USO:
- PARTIALLY_FILLED: Recalcular niveles restantes con nuevo sizing
- RISK_ADJUSTED: Ajustar SL/TP basado en posición promedio real
- REBALANCING: Optimizar niveles basado en condiciones de mercado actuales

🎯 LÓGICA DE RECÁLCULO:
- Mantener risk absoluto original ($ de pérdida máxima)
- Ajustar position sizes para optimizar niveles restantes
- Preservar lógica DCA pero con precios de mercado actuales
- Recalcular TP/SL basado en precio promedio REAL de ejecuciones

Example:
    Señal original: 3 niveles de $100 cada uno, SL a -$50
    Ejecutado: 1 nivel a $99 (no $100 planeado)
    Recálculo: 2 niveles restantes ajustados para mantener SL a -$50 total
    considerando que ya tenemos $99 en lugar de $100 planificado.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Union
from dataclasses import dataclass, asdict
import pytz
import pandas as pd

# Importar core components  
import position_calculator
try:
    from position_calculator import PositionCalculatorV3, PositionPlan, PositionLevel
    # Para backward compatibility, usar V3 como calculador base
    PositionCalculator = PositionCalculatorV3
    PositionSizing = PositionPlan  # Usando PositionPlan como estructura de sizing
except ImportError:
    # Fallback si no existe V3
    from position_calculator import PositionCalculator
    PositionSizing = dict  # Fallback simple
from database.connection import get_connection
from database.position_queries import PositionQueries

# Importar position management system
from .states import PositionStatus, EntryStatus, ExitStatus
from .data_models import EnhancedPosition, ExecutionLevel
from .state_manager import StateManager, get_state_manager
from .execution_tracker import ExecutionTracker
import config

logger = logging.getLogger(__name__)

@dataclass
class RecalculationContext:
    """Contexto para recálculo de posición"""
    original_position: EnhancedPosition
    executed_levels: List[ExecutionLevel]
    remaining_levels: List[ExecutionLevel] 
    current_price: float
    market_conditions: Dict
    recalc_reason: str = ""
    preserve_risk: bool = True
    preserve_reward: bool = True


@dataclass
class RecalculatedLevels:
    """Resultado de recálculo de niveles"""
    updated_entry_levels: List[ExecutionLevel]
    updated_exit_levels: List[ExecutionLevel]
    new_position_size: PositionSizing
    risk_adjustment: Dict
    performance_metrics: Dict
    recalc_timestamp: datetime


class CalculatorEnhancer:
    """
    Enhancer que extiende PositionCalculator con capacidades de recálculo
    basado en ejecuciones parciales reales
    """
    
    def __init__(self, base_calculator: PositionCalculator):
        """
        Inicializar el enhancer con el calculator base existente
        
        Args:
            base_calculator: Instancia de PositionCalculator existente
        """
        self.base_calculator = base_calculator
        self.position_queries = PositionQueries()
        self.state_manager = get_state_manager()
        self.execution_tracker = ExecutionTracker()
        
        # Configuration para recálculos
        self.recalc_config = {
            'max_risk_deviation': 0.05,      # Máximo 5% desviación del risk original
            'min_level_size': 10,            # Mínimo $10 por nivel
            'rebalance_threshold': 0.1,      # 10% cambio para rebalancear
            'preserve_dca_logic': True,      # Mantener lógica de DCA
            'adjust_for_slippage': True,     # Considerar slippage histórico
        }
        
        logger.info("✅ Calculator Enhancer inicializado")
    
    def recalculate_remaining_levels(
        self, 
        symbol: str, 
        current_price: float,
        force_recalc: bool = False
    ) -> Optional[RecalculatedLevels]:
        """
        Recalcular niveles restantes para una posición parcialmente ejecutada
        
        Args:
            symbol: Símbolo de la posición
            current_price: Precio actual del mercado
            force_recalc: Forzar recálculo aunque no sea necesario
            
        Returns:
            RecalculatedLevels si el recálculo es necesario y exitoso
            None si no es necesario o falló
        """
        logger.info(f"🧮 Iniciando recálculo de niveles para {symbol}")
        
        # STEP 1: Obtener posición actual y validar que requiere recálculo
        position = self._get_position_for_recalculation(symbol)
        if not position:
            logger.warning(f"⚠️ No se encontró posición válida para recalcular: {symbol}")
            return None
        
        # STEP 2: Evaluar si el recálculo es necesario
        if not force_recalc and not self._should_recalculate(position, current_price):
            logger.debug(f"📊 Recálculo no necesario para {symbol}")
            return None
            
        # STEP 3: Preparar contexto de recálculo
        context = self._build_recalculation_context(position, current_price)
        if not context:
            logger.error(f"❌ No se pudo construir contexto de recálculo para {symbol}")
            return None
        
        # STEP 4: Ejecutar recálculo basado en el tipo de ajuste necesario
        try:
            recalc_result = self._execute_recalculation(context)
            if recalc_result:
                logger.info(f"✅ Recálculo completado para {symbol}: "
                           f"{len(recalc_result.updated_entry_levels)} entry levels, "
                           f"{len(recalc_result.updated_exit_levels)} exit levels")
                
                # STEP 5: Actualizar posición en state manager
                self._apply_recalculated_levels(symbol, recalc_result)
                
                return recalc_result
            else:
                logger.error(f"❌ Recálculo falló para {symbol}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Error durante recálculo para {symbol}: {e}")
            return None
    
    def adjust_risk_based_on_executions(
        self, 
        symbol: str,
        new_risk_tolerance: Optional[float] = None
    ) -> bool:
        """
        Ajustar niveles de riesgo basado en ejecuciones actuales
        
        Args:
            symbol: Símbolo de la posición
            new_risk_tolerance: Nueva tolerancia al riesgo (opcional)
            
        Returns:
            True si el ajuste fue exitoso
        """
        logger.info(f"⚖️ Ajustando risk management para {symbol}")
        
        try:
            position = self._get_position_for_recalculation(symbol)
            if not position:
                return False
            
            # Calcular riesgo actual basado en ejecuciones reales
            current_risk = self._calculate_current_risk(position)
            original_risk = position.metadata.get('original_risk_amount', 0)
            
            logger.info(f"📊 Risk analysis: Original=${original_risk:.2f}, Current=${current_risk:.2f}")
            
            # Determinar si necesita ajuste
            risk_deviation = abs(current_risk - original_risk) / max(original_risk, 1)
            
            if risk_deviation > self.recalc_config['max_risk_deviation']:
                logger.info(f"⚠️ Risk deviation {risk_deviation:.1%} excede threshold, ajustando...")
                
                # Recalcular con nuevo risk target
                target_risk = new_risk_tolerance or original_risk
                return self._adjust_levels_for_risk_target(symbol, position, target_risk)
            else:
                logger.debug(f"✅ Risk deviation {risk_deviation:.1%} dentro de límites")
                return True
                
        except Exception as e:
            logger.error(f"❌ Error ajustando risk para {symbol}: {e}")
            return False
    
    def optimize_remaining_dca_levels(
        self, 
        symbol: str, 
        market_conditions: Dict
    ) -> Optional[List[ExecutionLevel]]:
        """
        Optimizar niveles DCA restantes basado en condiciones de mercado
        
        Args:
            symbol: Símbolo de la posición
            market_conditions: Condiciones actuales del mercado
            
        Returns:
            Lista optimizada de ExecutionLevel o None si no es posible
        """
        logger.info(f"🎯 Optimizando niveles DCA restantes para {symbol}")
        
        try:
            position = self._get_position_for_recalculation(symbol)
            if not position:
                return None
            
            remaining_levels = self._get_remaining_entry_levels(position)
            if not remaining_levels:
                logger.info(f"📊 No hay niveles DCA restantes para {symbol}")
                return None
            
            # Análizar condiciones de mercado para optimización
            optimization_factor = self._calculate_optimization_factor(market_conditions)
            
            optimized_levels = []
            for level in remaining_levels:
                optimized_level = self._optimize_single_dca_level(
                    level, position, optimization_factor, market_conditions
                )
                if optimized_level:
                    optimized_levels.append(optimized_level)
            
            logger.info(f"✅ Optimización completada: {len(optimized_levels)} niveles optimizados")
            return optimized_levels
            
        except Exception as e:
            logger.error(f"❌ Error optimizando DCA para {symbol}: {e}")
            return None
    
    def recalculate_tp_sl_from_average_price(
        self, 
        symbol: str
    ) -> Optional[Tuple[List[ExecutionLevel], List[ExecutionLevel]]]:
        """
        Recalcular Take Profits y Stop Loss basado en precio promedio REAL
        
        Args:
            symbol: Símbolo de la posición
            
        Returns:
            Tupla de (nuevos_TPs, nuevos_SLs) o None si falló
        """
        logger.info(f"🎯 Recalculando TP/SL desde precio promedio real para {symbol}")
        
        try:
            position = self._get_position_for_recalculation(symbol)
            if not position:
                return None
            
            # Calcular precio promedio real de ejecuciones
            executed_levels = [level for level in position.entry_levels 
                             if level.status == EntryStatus.FILLED]
            
            if not executed_levels:
                logger.warning(f"⚠️ No hay niveles ejecutados para calcular precio promedio: {symbol}")
                return None
            
            real_avg_price = self._calculate_real_average_price(executed_levels)
            logger.info(f"📊 Precio promedio real: ${real_avg_price:.4f}")
            
            # Obtener configuración original de TP/SL ratios
            original_tp_ratios = position.metadata.get('tp_ratios', [1.5, 2.0, 3.0])
            original_sl_ratio = position.metadata.get('sl_ratio', 0.5)
            
            # Recalcular TPs basado en precio promedio real
            new_tps = self._calculate_tps_from_average(
                real_avg_price, original_tp_ratios, position.direction
            )
            
            # Recalcular SL basado en precio promedio real  
            new_sls = self._calculate_sl_from_average(
                real_avg_price, original_sl_ratio, position.direction
            )
            
            logger.info(f"✅ TP/SL recalculados: {len(new_tps)} TPs, {len(new_sls)} SLs")
            return (new_tps, new_sls)
            
        except Exception as e:
            logger.error(f"❌ Error recalculando TP/SL para {symbol}: {e}")
            return None
    
    # =============================================================================
    # PRIVATE HELPER METHODS
    # =============================================================================
    
    def _get_position_for_recalculation(self, symbol: str) -> Optional[EnhancedPosition]:
        """Obtener posición válida para recálculo"""
        try:
            position = self.position_queries.get_active_position(symbol)
            if not position:
                return None
            
            # Validar que la posición puede ser recalculada
            recalculable_states = [
                PositionStatus.PARTIALLY_FILLED,
                PositionStatus.WATCHING,
                PositionStatus.RISK_ADJUSTED
            ]
            
            if position.status not in recalculable_states:
                logger.debug(f"📊 Posición {symbol} en estado {position.status} no requiere recálculo")
                return None
                
            return position
            
        except Exception as e:
            logger.error(f"❌ Error obteniendo posición para recálculo {symbol}: {e}")
            return None
    
    def _should_recalculate(self, position: EnhancedPosition, current_price: float) -> bool:
        """Determinar si una posición necesita recálculo"""
        
        # Verificar si hay ejecuciones parciales
        executed_count = sum(1 for level in position.entry_levels 
                           if level.status == EntryStatus.FILLED)
        total_count = len(position.entry_levels)
        
        if executed_count == 0:
            logger.debug("No hay ejecuciones - recálculo no necesario")
            return False
        
        if executed_count == total_count:
            logger.debug("Todas las entradas ejecutadas - recálculo no necesario")
            return False
        
        # Verificar cambios significativos en precio
        if position.last_recalc_price:
            price_change = abs(current_price - position.last_recalc_price) / position.last_recalc_price
            if price_change < self.recalc_config['rebalance_threshold']:
                logger.debug(f"Cambio de precio {price_change:.1%} < threshold")
                return False
        
        # Verificar tiempo desde último recálculo
        if position.last_recalc_time:
            time_since_recalc = datetime.now(pytz.UTC) - position.last_recalc_time
            if time_since_recalc < timedelta(minutes=30):
                logger.debug("Recálculo reciente - esperando cooldown")
                return False
        
        logger.info(f"✅ Recálculo necesario: {executed_count}/{total_count} niveles ejecutados")
        return True
    
    def _build_recalculation_context(
        self, 
        position: EnhancedPosition, 
        current_price: float
    ) -> Optional[RecalculationContext]:
        """Construir contexto para recálculo"""
        
        try:
            executed_levels = [level for level in position.entry_levels 
                             if level.status == EntryStatus.FILLED]
            remaining_levels = [level for level in position.entry_levels 
                              if level.status == EntryStatus.PENDING]
            
            # Obtener condiciones de mercado actuales
            market_conditions = self._get_market_conditions(position.symbol, current_price)
            
            # Determinar razón del recálculo
            recalc_reason = self._determine_recalc_reason(position, executed_levels, remaining_levels)
            
            return RecalculationContext(
                original_position=position,
                executed_levels=executed_levels,
                remaining_levels=remaining_levels,
                current_price=current_price,
                market_conditions=market_conditions,
                recalc_reason=recalc_reason
            )
            
        except Exception as e:
            logger.error(f"❌ Error construyendo contexto de recálculo: {e}")
            return None
    
    def _execute_recalculation(self, context: RecalculationContext) -> Optional[RecalculatedLevels]:
        """Ejecutar el recálculo principal"""
        
        try:
            # STEP 1: Calcular métricas actuales
            current_metrics = self._calculate_current_position_metrics(context)
            
            # STEP 2: Determinar nuevo position sizing para niveles restantes
            remaining_risk = self._calculate_remaining_risk_budget(context, current_metrics)
            new_sizing = self._calculate_new_position_sizing(context, remaining_risk)
            
            # STEP 3: Recalcular niveles de entrada restantes
            updated_entry_levels = self._recalculate_entry_levels(context, new_sizing)
            
            # STEP 4: Recalcular niveles de salida basado en nuevo promedio
            updated_exit_levels = self._recalculate_exit_levels(context, current_metrics)
            
            # STEP 5: Validar que el recálculo mantiene risk management
            if not self._validate_recalculation(context, updated_entry_levels, updated_exit_levels):
                logger.error("❌ Recálculo no pasó validación de risk management")
                return None
            
            # STEP 6: Construir resultado
            return RecalculatedLevels(
                updated_entry_levels=updated_entry_levels,
                updated_exit_levels=updated_exit_levels,
                new_position_size=new_sizing,
                risk_adjustment=self._calculate_risk_adjustment(context, current_metrics),
                performance_metrics=current_metrics,
                recalc_timestamp=datetime.now(pytz.UTC)
            )
            
        except Exception as e:
            logger.error(f"❌ Error ejecutando recálculo: {e}")
            return None
    
    def _calculate_current_position_metrics(self, context: RecalculationContext) -> Dict:
        """Calcular métricas actuales de la posición"""
        
        executed_levels = context.executed_levels
        if not executed_levels:
            return {}
        
        # Calcular precio promedio real
        total_cost = sum(level.executed_price * level.executed_quantity for level in executed_levels)
        total_quantity = sum(level.executed_quantity for level in executed_levels)
        avg_price = total_cost / total_quantity if total_quantity > 0 else 0
        
        # Calcular unrealized P&L
        current_value = total_quantity * context.current_price
        unrealized_pnl = current_value - total_cost
        
        # Calcular métricas de risk
        position_value = abs(total_cost)
        risk_percentage = abs(unrealized_pnl) / position_value if position_value > 0 else 0
        
        return {
            'executed_levels': len(executed_levels),
            'total_quantity': total_quantity,
            'average_price': avg_price,
            'total_cost': total_cost,
            'current_value': current_value,
            'unrealized_pnl': unrealized_pnl,
            'position_value': position_value,
            'risk_percentage': risk_percentage,
            'price_deviation': (context.current_price - avg_price) / avg_price if avg_price > 0 else 0
        }
    
    def _calculate_remaining_risk_budget(
        self, 
        context: RecalculationContext, 
        current_metrics: Dict
    ) -> float:
        """Calcular budget de riesgo restante"""
        
        # Obtener risk budget original
        original_risk = context.original_position.metadata.get('original_risk_amount', 0)
        
        # Calcular risk ya comprometido
        committed_risk = abs(current_metrics.get('total_cost', 0))
        
        # Risk budget restante
        remaining_risk = max(0, original_risk - committed_risk)
        
        logger.debug(f"📊 Risk budget: Original=${original_risk:.2f}, "
                    f"Committed=${committed_risk:.2f}, Remaining=${remaining_risk:.2f}")
        
        return remaining_risk
    
    def _calculate_new_position_sizing(
        self, 
        context: RecalculationContext, 
        remaining_risk: float
    ) -> PositionSizing:
        """Calcular nuevo position sizing para niveles restantes"""
        
        remaining_levels_count = len(context.remaining_levels)
        if remaining_levels_count == 0:
            # No hay niveles restantes - retornar structure vacía
            if hasattr(PositionSizing, '__name__') and PositionSizing.__name__ == 'PositionPlan':
                # Es PositionPlan, crear uno mínimo
                return PositionSizing(
                    symbol=context.original_position.symbol,
                    direction=context.original_position.direction,
                    current_price=context.current_price,
                    signal_strength=0,
                    strategy_type='RECALC',
                    total_risk_percent=0,
                    entries=[],
                    exits=[],
                    stop_loss=None,
                    max_risk_reward=0,
                    avg_risk_reward=0,
                    expected_hold_time='N/A',
                    confidence_level='NONE',
                    technical_summary='No remaining levels',
                    market_context='Recalculation',
                    risk_assessment='No risk'
                )
            else:
                # Es dict o otra estructura simple
                return {'position_size': 0, 'risk_amount': 0, 'reward_ratio': 0, 'stop_loss_distance': 0}
        
        # Distribuir risk restante entre niveles pendientes
        risk_per_level = remaining_risk / remaining_levels_count
        
        # Usar calculator base para obtener sizing apropiado
        try:
            if hasattr(self.base_calculator, 'calculate_position_plan_v3'):
                # Es PositionCalculatorV3
                base_sizing = self.base_calculator.calculate_position_plan_v3(
                    symbol=context.original_position.symbol,
                    direction=context.original_position.direction,
                    current_price=context.current_price,
                    signal_strength=50,  # Neutral para recálculo
                    indicators={},
                    market_data=pd.DataFrame(),  # Empty for recalc
                    account_balance=risk_per_level * remaining_levels_count
                )
            else:
                # Fallback simple
                base_sizing = {
                    'position_size': risk_per_level / context.current_price,
                    'risk_amount': risk_per_level,
                    'reward_ratio': 2.0,
                    'stop_loss_distance': context.current_price * 0.02
                }
        except Exception as e:
            logger.warning(f"⚠️ Error usando base calculator, usando fallback: {e}")
            base_sizing = {
                'position_size': risk_per_level / context.current_price,
                'risk_amount': risk_per_level,
                'reward_ratio': 2.0,
                'stop_loss_distance': context.current_price * 0.02
            }
        
        return base_sizing
    
    def _recalculate_entry_levels(
        self, 
        context: RecalculationContext, 
        new_sizing: PositionSizing
    ) -> List[ExecutionLevel]:
        """Recalcular niveles de entrada restantes"""
        
        updated_levels = []
        
        for level in context.remaining_levels:
            # Mantener precio original pero ajustar quantity
            # Determinar quantity apropiada basada en el tipo de sizing
            if hasattr(new_sizing, 'entries') and new_sizing.entries:
                # Es PositionPlan con entries
                target_quantity = sum(entry.percentage for entry in new_sizing.entries) / 100
            elif isinstance(new_sizing, dict) and 'position_size' in new_sizing:
                # Es dict con position_size
                target_quantity = new_sizing['position_size']
            else:
                # Fallback
                target_quantity = 100  # Default quantity
            
            updated_level = ExecutionLevel(
                level_id=level.level_id,
                level_type=level.level_type,
                target_price=level.target_price,  # Mantener precio objetivo
                target_quantity=target_quantity,  # Nueva cantidad
                executed_price=level.executed_price,
                executed_quantity=level.executed_quantity,
                status=level.status,
                created_at=level.created_at,
                updated_at=datetime.now(pytz.UTC)
            )
            
            updated_levels.append(updated_level)
        
        return updated_levels
    
    def _recalculate_exit_levels(
        self, 
        context: RecalculationContext, 
        current_metrics: Dict
    ) -> List[ExecutionLevel]:
        """Recalcular niveles de salida basado en precio promedio real"""
        
        avg_price = current_metrics.get('average_price', 0)
        if avg_price == 0:
            return context.original_position.exit_levels  # Mantener originales si no hay promedio
        
        # Recalcular TPs y SL desde precio promedio real
        tp_sl_result = self.recalculate_tp_sl_from_average_price(context.original_position.symbol)
        
        if tp_sl_result:
            new_tps, new_sls = tp_sl_result
            return new_tps + new_sls
        else:
            return context.original_position.exit_levels
    
    def _validate_recalculation(
        self, 
        context: RecalculationContext,
        updated_entry_levels: List[ExecutionLevel],
        updated_exit_levels: List[ExecutionLevel]
    ) -> bool:
        """Validar que el recálculo mantiene risk management apropiado"""
        
        try:
            # Validar que hay niveles válidos
            if not updated_entry_levels and not updated_exit_levels:
                logger.error("❌ Recálculo resultó en niveles vacíos")
                return False
            
            # Validar risk budget
            total_new_risk = sum(level.target_quantity * level.target_price 
                               for level in updated_entry_levels if level.target_quantity and level.target_price)
            
            original_risk = context.original_position.metadata.get('original_risk_amount', 1000.0)  # Default fallback
            current_committed = sum(level.executed_quantity * level.executed_price 
                                  for level in context.executed_levels if level.executed_quantity and level.executed_price)
            
            total_risk = total_new_risk + current_committed
            
            if total_risk > original_risk * 1.1:  # 10% tolerancia
                logger.error(f"❌ Risk excede límite: ${total_risk:.2f} > ${original_risk * 1.1:.2f}")
                return False
            
            # Validar que quantities son razonables
            for level in updated_entry_levels:
                if level.target_quantity and level.target_quantity < self.recalc_config['min_level_size']:
                    logger.error(f"❌ Level size demasiado pequeño: ${level.target_quantity:.2f}")
                    return False
            
            logger.info("✅ Recálculo pasó todas las validaciones")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error validando recálculo: {e}")
            return False
    
    def _apply_recalculated_levels(self, symbol: str, recalc_result: RecalculatedLevels) -> bool:
        """Aplicar niveles recalculados a través del state manager"""
        
        try:
            # Actualizar posición con niveles recalculados
            updated_position = self.state_manager.get_position(symbol)
            if not updated_position:
                logger.error(f"❌ No se encontró posición en state manager: {symbol}")
                return False
            
            # Aplicar nuevos niveles de entrada
            for level in recalc_result.updated_entry_levels:
                self.state_manager.update_entry_level(symbol, level.level_id, level)
            
            # Aplicar nuevos niveles de salida
            for level in recalc_result.updated_exit_levels:
                self.state_manager.update_exit_level(symbol, level.level_id, level)
            
            # Actualizar metadata con información del recálculo
            metadata_update = {
                'last_recalc_time': recalc_result.recalc_timestamp,
                'last_recalc_price': recalc_result.performance_metrics.get('current_price'),
                'recalc_count': updated_position.metadata.get('recalc_count', 0) + 1,
                'risk_adjustment': recalc_result.risk_adjustment
            }
            
            self.state_manager.update_position_metadata(symbol, metadata_update)
            
            logger.info(f"✅ Niveles recalculados aplicados exitosamente para {symbol}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error aplicando niveles recalculados para {symbol}: {e}")
            return False
    
    # =============================================================================
    # UTILITY & HELPER METHODS
    # =============================================================================
    
    def _get_market_conditions(self, symbol: str, current_price: float) -> Dict:
        """Obtener condiciones actuales del mercado (simplificado para MVP)"""
        return {
            'current_price': current_price,
            'volatility': 'medium',  # Placeholder
            'trend': 'neutral',      # Placeholder
            'volume': 'normal'       # Placeholder
        }
    
    def _determine_recalc_reason(
        self, 
        position: EnhancedPosition, 
        executed_levels: List[ExecutionLevel], 
        remaining_levels: List[ExecutionLevel]
    ) -> str:
        """Determinar razón del recálculo"""
        
        if len(executed_levels) > 0 and len(remaining_levels) > 0:
            return f"PARTIAL_EXECUTION: {len(executed_levels)} executed, {len(remaining_levels)} pending"
        elif len(executed_levels) == 0:
            return "PRICE_ADJUSTMENT: No executions yet"
        else:
            return "COMPLETION_OPTIMIZATION: All entries executed"
    
    def _calculate_current_risk(self, position: EnhancedPosition) -> float:
        """Calcular riesgo actual de la posición"""
        executed_levels = [level for level in position.entry_levels 
                          if level.status == EntryStatus.FILLED]
        
        return sum(level.executed_quantity * level.executed_price 
                  for level in executed_levels 
                  if level.executed_quantity and level.executed_price)
    
    def _adjust_levels_for_risk_target(
        self, 
        symbol: str, 
        position: EnhancedPosition, 
        target_risk: float
    ) -> bool:
        """Ajustar niveles para alcanzar risk target específico"""
        # Placeholder para implementación futura
        logger.info(f"🎯 Ajustando niveles para risk target ${target_risk:.2f}")
        return True
    
    def _get_remaining_entry_levels(self, position: EnhancedPosition) -> List[ExecutionLevel]:
        """Obtener niveles de entrada restantes"""
        return [level for level in position.entry_levels 
                if level.status == EntryStatus.PENDING]
    
    def _calculate_optimization_factor(self, market_conditions: Dict) -> float:
        """Calcular factor de optimización basado en condiciones de mercado"""
        # Placeholder - implementar lógica más sofisticada
        return 1.0
    
    def _optimize_single_dca_level(
        self, 
        level: ExecutionLevel, 
        position: EnhancedPosition,
        optimization_factor: float, 
        market_conditions: Dict
    ) -> Optional[ExecutionLevel]:
        """Optimizar un nivel DCA individual"""
        # Placeholder - mantener nivel original por ahora
        return level
    
    def _calculate_real_average_price(self, executed_levels: List[ExecutionLevel]) -> float:
        """Calcular precio promedio real de niveles ejecutados"""
        if not executed_levels:
            return 0.0
        
        total_cost = sum(level.executed_quantity * level.executed_price for level in executed_levels)
        total_quantity = sum(level.executed_quantity for level in executed_levels)
        
        return total_cost / total_quantity if total_quantity > 0 else 0.0
    
    def _calculate_tps_from_average(
        self, 
        avg_price: float, 
        tp_ratios: List[float], 
        direction: str
    ) -> List[ExecutionLevel]:
        """Calcular Take Profits desde precio promedio real"""
        
        tps = []
        for i, ratio in enumerate(tp_ratios):
            if direction == "LONG":
                tp_price = avg_price * (1 + ratio / 100)  # Para LONG: precio + ratio%
            else:
                tp_price = avg_price * (1 - ratio / 100)  # Para SHORT: precio - ratio%
            
            tp_level = ExecutionLevel(
                level_id=f"TP{i+1}_recalc_{int(datetime.now().timestamp())}",
                level_type="TAKE_PROFIT",
                target_price=tp_price,
                target_quantity=0,  # Se calculará basado en posición actual
                status=ExitStatus.PENDING,
                created_at=datetime.now(pytz.UTC)
            )
            
            tps.append(tp_level)
        
        return tps
    
    def _calculate_sl_from_average(
        self, 
        avg_price: float, 
        sl_ratio: float, 
        direction: str
    ) -> List[ExecutionLevel]:
        """Calcular Stop Loss desde precio promedio real"""
        
        if direction == "LONG":
            sl_price = avg_price * (1 - sl_ratio / 100)  # Para LONG: precio - ratio%
        else:
            sl_price = avg_price * (1 + sl_ratio / 100)  # Para SHORT: precio + ratio%
        
        sl_level = ExecutionLevel(
            level_id=f"SL_recalc_{int(datetime.now().timestamp())}",
            level_type="STOP_LOSS",
            target_price=sl_price,
            target_quantity=0,  # Se calculará basado en posición total
            status=ExitStatus.PENDING,
            created_at=datetime.now(pytz.UTC)
        )
        
        return [sl_level]
    
    def _calculate_risk_adjustment(
        self, 
        context: RecalculationContext, 
        current_metrics: Dict
    ) -> Dict:
        """Calcular ajuste de riesgo aplicado"""
        
        original_risk = context.original_position.metadata.get('original_risk_amount', 0)
        current_risk = current_metrics.get('position_value', 0)
        
        return {
            'original_risk_amount': original_risk,
            'current_risk_amount': current_risk,
            'risk_adjustment_ratio': current_risk / original_risk if original_risk > 0 else 1.0,
            'adjustment_reason': context.recalc_reason,
            'adjustment_timestamp': datetime.now(pytz.UTC)
        }
    
    def get_recalculation_stats(self) -> Dict:
        """Obtener estadísticas del sistema de recálculo"""
        try:
            # Stats básicas desde state manager
            state_stats = self.state_manager.get_stats()
            
            # Stats específicas de recálculo
            recalc_stats = {
                'enhanced_calculation_enabled': True,
                'recalc_config': self.recalc_config,
                'positions_requiring_recalc': self._count_positions_requiring_recalc(),
                'recent_recalculations': self._get_recent_recalculation_count(),
            }
            
            return {**state_stats, **recalc_stats}
            
        except Exception as e:
            logger.error(f"❌ Error obteniendo stats de recálculo: {e}")
            return {'error': str(e)}
    
    def _count_positions_requiring_recalc(self) -> int:
        """Contar posiciones que requieren recálculo"""
        try:
            positions = self.position_queries.get_positions_by_status([
                PositionStatus.PARTIALLY_FILLED,
                PositionStatus.WATCHING,
                PositionStatus.RISK_ADJUSTED
            ])
            return len(positions)
        except:
            return 0
    
    def _get_recent_recalculation_count(self) -> int:
        """Contar recálculos recientes (última hora)"""
        # Placeholder - implementar cuando tengamos tracking de recálculos
        return 0
    
    def clear_cache(self):
        """Limpiar caches del enhancer"""
        # Placeholder para limpieza de cache si fuera necesario
        logger.info("🧹 Calculator enhancer cache cleared")


# =============================================================================
# INTEGRATION HELPER - Función para integrar con position_calculator.py
# =============================================================================

def enhance_calculator_if_enabled(calculator: PositionCalculator) -> PositionCalculator:
    """
    Helper function para activar enhancement del calculator si está habilitado
    
    Args:
        calculator: PositionCalculator base existente
        
    Returns:
        Calculator original o enhanced según configuración
    """
    if not getattr(config, 'USE_POSITION_MANAGEMENT', False):
        logger.info("📊 Position management desactivado - usando calculator básico")
        return calculator
    
    try:
        enhancer = CalculatorEnhancer(calculator)
        logger.info("✅ Calculator enhanced with recalculation capabilities")
        
        # Monkey-patch para mantener compatibilidad
        # Agregar métodos de recálculo al calculator existente
        calculator.recalculate_remaining_levels = enhancer.recalculate_remaining_levels
        calculator.adjust_risk_based_on_executions = enhancer.adjust_risk_based_on_executions
        calculator.optimize_remaining_dca_levels = enhancer.optimize_remaining_dca_levels
        calculator.recalculate_tp_sl_from_average_price = enhancer.recalculate_tp_sl_from_average_price
        calculator.get_recalculation_stats = enhancer.get_recalculation_stats
        calculator.clear_recalc_cache = enhancer.clear_cache  # Renamed to avoid conflicts
        calculator._enhancer = enhancer  # Mantener referencia
        
        return calculator
        
    except Exception as e:
        logger.error(f"❌ Error activando calculator enhancement: {e}")
        logger.warning("🔄 Fallback a calculator básico")
        return calculator


# =============================================================================
# TESTING UTILITIES
# =============================================================================

def test_calculator_enhancer():
    """
    Función de testing rápido para validar el enhancer
    """
    logger.info("🧪 Testing Calculator Enhancer...")
    
    try:
        # Mock calculator básico
        class MockCalculator:
            def calculate_position_size(self, price, risk, direction):
                from position_calculator import PositionSizing
                return PositionSizing(100, risk/price, risk, 1.0)
        
        # Test inicialización
        mock_calc = MockCalculator()
        enhancer = CalculatorEnhancer(mock_calc)
        
        # Test stats
        stats = enhancer.get_recalculation_stats()
        
        logger.info(f"✅ Calculator Enhancer test exitoso")
        logger.info(f"📊 Stats: {stats}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Calculator Enhancer test falló: {e}")
        return False


if __name__ == "__main__":
    # Test básico si se ejecuta directamente
    test_calculator_enhancer()