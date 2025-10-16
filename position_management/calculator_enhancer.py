#!/usr/bin/env python3
"""
🧮 CALCULATOR ENHANCER - PARTIAL EXECUTION RECALCULATION V3.0 - FIXED
====================================================================

Enhancer que extiende position_calculator.py para manejar recálculos inteligentes
de niveles restantes basado en ejecuciones parciales reales del mercado.

FIXES V3.0:
✅ Imports corregidos para PositionCalculatorV3
✅ Reemplazo de PositionSizing por PositionPlan
✅ Compatibilidad con nueva API de position_calculator.py
✅ Todos los imports actualizados correctamente
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Union
from dataclasses import dataclass, asdict
import pytz

# Importar core components - FIXED para V3
from position_calculator import PositionCalculatorV3, PositionLevel, PositionPlan
from database.connection import get_connection
from database.position_queries import PositionQueries

# Importar position management system
from position_management.states import PositionStatus, EntryStatus, ExitStatus
from position_management.data_models import EnhancedPosition, ExecutionLevel
from position_management.state_manager import StateManager, get_state_manager
from position_management.execution_tracker import ExecutionTracker
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
    """Resultado de recálculo de niveles - FIXED para V3"""
    updated_entry_levels: List[ExecutionLevel]
    updated_exit_levels: List[ExecutionLevel]
    new_position_plan: PositionPlan  # CHANGED: era new_position_size
    risk_adjustment: Dict
    performance_metrics: Dict
    recalc_timestamp: datetime


class CalculatorEnhancer:
    """
    Enhancer que extiende PositionCalculatorV3 con capacidades de recálculo
    basado en ejecuciones parciales reales
    """
    
    def __init__(self, base_calculator: PositionCalculatorV3):
        """
        Inicializar el enhancer con el calculator base existente
        
        Args:
            base_calculator: Instancia de PositionCalculatorV3 existente
        """
        self.base_calculator = base_calculator
        self.position_queries = PositionQueries()
        self.state_manager = get_state_manager()
        self.execution_tracker = ExecutionTracker()
        
        # Configuration para recálculos
        self.recalc_config = {
            'max_risk_deviation': 0.05,
            'min_level_size': 10,
            'rebalance_threshold': 0.1,
            'preserve_dca_logic': True,
            'adjust_for_slippage': True,
        }
        
        logger.info("✅ Calculator Enhancer V3.0 inicializado")
    
    def recalculate_remaining_levels(
        self, 
        symbol: str, 
        current_price: float,
        force_recalc: bool = False
    ) -> Optional[RecalculatedLevels]:
        """Recalcular niveles restantes para una posición parcialmente ejecutada"""
        logger.info(f"🧮 Iniciando recálculo de niveles para {symbol}")
        
        position = self._get_position_for_recalculation(symbol)
        if not position:
            logger.warning(f"⚠️ No se encontró posición válida para recalcular: {symbol}")
            return None
        
        if not force_recalc and not self._should_recalculate(position, current_price):
            logger.debug(f"📊 Recálculo no necesario para {symbol}")
            return None
            
        context = self._build_recalculation_context(position, current_price)
        if not context:
            logger.error(f"❌ No se pudo construir contexto de recálculo para {symbol}")
            return None
        
        try:
            recalc_result = self._execute_recalculation(context)
            if recalc_result:
                logger.info(f"✅ Recálculo completado para {symbol}")
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
        """Ajustar niveles de riesgo basado en ejecuciones actuales"""
        logger.info(f"⚖️ Ajustando risk management para {symbol}")
        
        try:
            position = self._get_position_for_recalculation(symbol)
            if not position:
                return False
            
            current_risk = self._calculate_current_risk(position)
            original_risk = position.metadata.get('original_risk_amount', 0)
            
            logger.info(f"📊 Risk analysis: Original=${original_risk:.2f}, Current=${current_risk:.2f}")
            
            risk_deviation = abs(current_risk - original_risk) / max(original_risk, 1)
            
            if risk_deviation > self.recalc_config['max_risk_deviation']:
                logger.info(f"⚠️ Risk deviation {risk_deviation:.1%} excede threshold")
                target_risk = new_risk_tolerance or original_risk
                return self._adjust_levels_for_risk_target(symbol, position, target_risk)
            else:
                logger.debug(f"✅ Risk deviation {risk_deviation:.1%} dentro de límites")
                return True
                
        except Exception as e:
            logger.error(f"❌ Error ajustando risk para {symbol}: {e}")
            return False
    
    def recalculate_tp_sl_from_average_price(
        self, 
        symbol: str
    ) -> Optional[Tuple[List[ExecutionLevel], List[ExecutionLevel]]]:
        """Recalcular Take Profits y Stop Loss basado en precio promedio REAL"""
        logger.info(f"🎯 Recalculando TP/SL desde precio promedio real para {symbol}")
        
        try:
            position = self._get_position_for_recalculation(symbol)
            if not position:
                return None
            
            executed_levels = [level for level in position.entry_levels 
                             if level.status == EntryStatus.FILLED]
            
            if not executed_levels:
                logger.warning(f"⚠️ No hay niveles ejecutados: {symbol}")
                return None
            
            real_avg_price = self._calculate_real_average_price(executed_levels)
            logger.info(f"📊 Precio promedio real: ${real_avg_price:.4f}")
            
            original_tp_ratios = position.metadata.get('tp_ratios', [1.5, 2.0, 3.0])
            original_sl_ratio = position.metadata.get('sl_ratio', 0.5)
            
            new_tps = self._calculate_tps_from_average(
                real_avg_price, original_tp_ratios, position.direction
            )
            
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
            
            recalculable_states = [
                PositionStatus.PARTIALLY_FILLED,
                PositionStatus.WATCHING,
                PositionStatus.RISK_ADJUSTED
            ]
            
            if position.status not in recalculable_states:
                return None
                
            return position
            
        except Exception as e:
            logger.error(f"❌ Error obteniendo posición: {e}")
            return None
    
    def _should_recalculate(self, position: EnhancedPosition, current_price: float) -> bool:
        """Determinar si una posición necesita recálculo"""
        executed_count = sum(1 for level in position.entry_levels 
                           if level.status == EntryStatus.FILLED)
        total_count = len(position.entry_levels)
        
        if executed_count == 0 or executed_count == total_count:
            return False
        
        if position.last_recalc_price:
            price_change = abs(current_price - position.last_recalc_price) / position.last_recalc_price
            if price_change < self.recalc_config['rebalance_threshold']:
                return False
        
        if position.last_recalc_time:
            time_since_recalc = datetime.now(pytz.UTC) - position.last_recalc_time
            if time_since_recalc < timedelta(minutes=30):
                return False
        
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
            
            market_conditions = {'current_price': current_price, 'volatility': 'medium'}
            recalc_reason = f"PARTIAL: {len(executed_levels)}/{len(position.entry_levels)} executed"
            
            return RecalculationContext(
                original_position=position,
                executed_levels=executed_levels,
                remaining_levels=remaining_levels,
                current_price=current_price,
                market_conditions=market_conditions,
                recalc_reason=recalc_reason
            )
        except Exception as e:
            logger.error(f"❌ Error construyendo contexto: {e}")
            return None
    
    def _execute_recalculation(self, context: RecalculationContext) -> Optional[RecalculatedLevels]:
        """Ejecutar el recálculo principal"""
        try:
            current_metrics = self._calculate_current_position_metrics(context)
            remaining_risk = self._calculate_remaining_risk_budget(context, current_metrics)
            new_plan = self._calculate_new_position_plan(context, remaining_risk)
            
            updated_entry_levels = self._recalculate_entry_levels(context, new_plan)
            updated_exit_levels = self._recalculate_exit_levels(context, current_metrics)
            
            if not self._validate_recalculation(context, updated_entry_levels, updated_exit_levels):
                return None
            
            return RecalculatedLevels(
                updated_entry_levels=updated_entry_levels,
                updated_exit_levels=updated_exit_levels,
                new_position_plan=new_plan,
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
        
        total_cost = sum(level.executed_price * level.executed_quantity for level in executed_levels)
        total_quantity = sum(level.executed_quantity for level in executed_levels)
        avg_price = total_cost / total_quantity if total_quantity > 0 else 0
        
        current_value = total_quantity * context.current_price
        unrealized_pnl = current_value - total_cost
        
        return {
            'executed_levels': len(executed_levels),
            'total_quantity': total_quantity,
            'average_price': avg_price,
            'total_cost': total_cost,
            'current_value': current_value,
            'unrealized_pnl': unrealized_pnl,
            'position_value': abs(total_cost),
            'risk_percentage': abs(unrealized_pnl) / abs(total_cost) if total_cost != 0 else 0
        }
    
    def _calculate_remaining_risk_budget(self, context: RecalculationContext, current_metrics: Dict) -> float:
        """Calcular budget de riesgo restante"""
        original_risk = context.original_position.metadata.get('original_risk_amount', 0)
        committed_risk = abs(current_metrics.get('total_cost', 0))
        return max(0, original_risk - committed_risk)
    
    def _calculate_new_position_plan(self, context: RecalculationContext, remaining_risk: float) -> PositionPlan:
        """Calcular nuevo position plan para niveles restantes - FIXED para V3"""
        remaining_count = len(context.remaining_levels)
        
        if remaining_count == 0:
            return PositionPlan(
                symbol=context.original_position.symbol,
                direction=context.original_position.direction,
                current_price=context.current_price,
                signal_strength=0,
                strategy_type="RECALCULATED",
                total_risk_percent=0,
                entries=[],
                exits=[],
                stop_loss=None,
                max_risk_reward=0,
                avg_risk_reward=0,
                expected_hold_time="N/A",
                confidence_level="LOW",
                technical_summary="No remaining levels",
                market_context="Recalculation",
                risk_assessment="Zero risk"
            )
        
        risk_per_level = remaining_risk / remaining_count
        
        return PositionPlan(
            symbol=context.original_position.symbol,
            direction=context.original_position.direction,
            current_price=context.current_price,
            signal_strength=context.original_position.metadata.get('original_signal_strength', 70),
            strategy_type="RECALCULATED",
            total_risk_percent=remaining_risk,
            entries=[],
            exits=[],
            stop_loss=None,
            max_risk_reward=2.0,
            avg_risk_reward=1.5,
            expected_hold_time="Variable",
            confidence_level="MEDIUM",
            technical_summary="Recalculated position",
            market_context="Partial execution adjustment",
            risk_assessment=f"Remaining risk: ${remaining_risk:.2f}"
        )
    
    def _recalculate_entry_levels(self, context: RecalculationContext, new_plan: PositionPlan) -> List[ExecutionLevel]:
        """Recalcular niveles de entrada restantes"""
        updated_levels = []
        quantity_per_level = new_plan.total_risk_percent / max(len(context.remaining_levels), 1)
        
        for level in context.remaining_levels:
            updated_level = ExecutionLevel(
                level_id=level.level_id,
                level_type=level.level_type,
                target_price=level.target_price,
                target_quantity=quantity_per_level,
                executed_price=level.executed_price,
                executed_quantity=level.executed_quantity,
                status=level.status,
                created_at=level.created_at,
                updated_at=datetime.now(pytz.UTC)
            )
            updated_levels.append(updated_level)
        
        return updated_levels
    
    def _recalculate_exit_levels(self, context: RecalculationContext, current_metrics: Dict) -> List[ExecutionLevel]:
        """Recalcular niveles de salida basado en precio promedio real"""
        avg_price = current_metrics.get('average_price', 0)
        if avg_price == 0:
            return context.original_position.exit_levels
        
        tp_sl_result = self.recalculate_tp_sl_from_average_price(context.original_position.symbol)
        
        if tp_sl_result:
            new_tps, new_sls = tp_sl_result
            return new_tps + new_sls
        else:
            return context.original_position.exit_levels
    
    def _validate_recalculation(self, context: RecalculationContext, 
                                updated_entry_levels: List[ExecutionLevel],
                                updated_exit_levels: List[ExecutionLevel]) -> bool:
        """Validar que el recálculo mantiene risk management apropiado"""
        try:
            if not updated_entry_levels and not updated_exit_levels:
                return False
            
            total_new_risk = sum(level.target_quantity * level.target_price 
                               for level in updated_entry_levels)
            
            original_risk = context.original_position.metadata.get('original_risk_amount', 0)
            current_committed = sum(level.executed_quantity * level.executed_price 
                                  for level in context.executed_levels)
            
            total_risk = total_new_risk + current_committed
            
            if total_risk > original_risk * 1.1:
                logger.error(f"❌ Risk excede límite: ${total_risk:.2f} > ${original_risk * 1.1:.2f}")
                return False
            
            for level in updated_entry_levels:
                if level.target_quantity < self.recalc_config['min_level_size']:
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error validando recálculo: {e}")
            return False
    
    def _apply_recalculated_levels(self, symbol: str, recalc_result: RecalculatedLevels) -> bool:
        """Aplicar niveles recalculados a través del state manager"""
        try:
            updated_position = self.state_manager.get_position(symbol)
            if not updated_position:
                return False
            
            for level in recalc_result.updated_entry_levels:
                self.state_manager.update_entry_level(symbol, level.level_id, level)
            
            for level in recalc_result.updated_exit_levels:
                self.state_manager.update_exit_level(symbol, level.level_id, level)
            
            metadata_update = {
                'last_recalc_time': recalc_result.recalc_timestamp,
                'last_recalc_price': recalc_result.performance_metrics.get('current_price'),
                'recalc_count': updated_position.metadata.get('recalc_count', 0) + 1,
                'risk_adjustment': recalc_result.risk_adjustment
            }
            
            self.state_manager.update_position_metadata(symbol, metadata_update)
            logger.info(f"✅ Niveles recalculados aplicados para {symbol}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error aplicando niveles: {e}")
            return False
    
    # Utility methods
    def _calculate_current_risk(self, position: EnhancedPosition) -> float:
        """Calcular riesgo actual"""
        executed_levels = [level for level in position.entry_levels 
                          if level.status == EntryStatus.FILLED]
        return sum(level.executed_quantity * level.executed_price for level in executed_levels)
    
    def _adjust_levels_for_risk_target(self, symbol: str, position: EnhancedPosition, target_risk: float) -> bool:
        """Ajustar niveles para risk target"""
        logger.info(f"🎯 Ajustando para target ${target_risk:.2f}")
        return True
    
    def _calculate_real_average_price(self, executed_levels: List[ExecutionLevel]) -> float:
        """Calcular precio promedio real"""
        if not executed_levels:
            return 0.0
        total_cost = sum(level.executed_quantity * level.executed_price for level in executed_levels)
        total_quantity = sum(level.executed_quantity for level in executed_levels)
        return total_cost / total_quantity if total_quantity > 0 else 0.0
    
    def _calculate_tps_from_average(self, avg_price: float, tp_ratios: List[float], direction: str) -> List[ExecutionLevel]:
        """Calcular TPs desde precio promedio"""
        tps = []
        for i, ratio in enumerate(tp_ratios):
            tp_price = avg_price * (1 + ratio / 100) if direction == "LONG" else avg_price * (1 - ratio / 100)
            tp_level = ExecutionLevel(
                level_id=f"TP{i+1}_recalc_{int(datetime.now().timestamp())}",
                level_type="TAKE_PROFIT",
                target_price=tp_price,
                target_quantity=0,
                status=ExitStatus.PENDING,
                created_at=datetime.now(pytz.UTC)
            )
            tps.append(tp_level)
        return tps
    
    def _calculate_sl_from_average(self, avg_price: float, sl_ratio: float, direction: str) -> List[ExecutionLevel]:
        """Calcular SL desde precio promedio"""
        sl_price = avg_price * (1 - sl_ratio / 100) if direction == "LONG" else avg_price * (1 + sl_ratio / 100)
        sl_level = ExecutionLevel(
            level_id=f"SL_recalc_{int(datetime.now().timestamp())}",
            level_type="STOP_LOSS",
            target_price=sl_price,
            target_quantity=0,
            status=ExitStatus.PENDING,
            created_at=datetime.now(pytz.UTC)
        )
        return [sl_level]
    
    def _calculate_risk_adjustment(self, context: RecalculationContext, current_metrics: Dict) -> Dict:
        """Calcular ajuste de riesgo"""
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
            state_stats = self.state_manager.get_stats()
            recalc_stats = {
                'enhanced_calculation_enabled': True,
                'recalc_config': self.recalc_config,
            }
            return {**state_stats, **recalc_stats}
        except Exception as e:
            return {'error': str(e)}


# =============================================================================
# INTEGRATION HELPER
# =============================================================================

def enhance_calculator_if_enabled(calculator: PositionCalculatorV3) -> PositionCalculatorV3:
    """
    Helper function para activar enhancement del calculator si está habilitado
    
    Args:
        calculator: PositionCalculatorV3 base existente
        
    Returns:
        Calculator original o enhanced según configuración
    """
    if not getattr(config, 'USE_POSITION_MANAGEMENT', False):
        logger.info("📊 Position management desactivado")
        return calculator
    
    try:
        enhancer = CalculatorEnhancer(calculator)
        logger.info("✅ Calculator enhanced V3.0")
        
        # Monkey-patch para compatibilidad
        calculator.recalculate_remaining_levels = enhancer.recalculate_remaining_levels
        calculator.adjust_risk_based_on_executions = enhancer.adjust_risk_based_on_executions
        calculator.recalculate_tp_sl_from_average_price = enhancer.recalculate_tp_sl_from_average_price
        calculator.get_recalculation_stats = enhancer.get_recalculation_stats
        calculator._enhancer = enhancer
        
        return calculator
        
    except Exception as e:
        logger.error(f"❌ Error activando enhancement: {e}")
        return calculator


# =============================================================================
# TESTING
# =============================================================================

def test_calculator_enhancer():
    """Test rápido del enhancer"""
    logger.info("🧪 Testing Calculator Enhancer V3.0...")
    
    try:
        class MockCalculatorV3:
            def calculate_position_plan(self, symbol, price, signal_strength, market_data=None):
                return PositionPlan(
                    symbol=symbol,
                    direction="LONG",
                    current_price=price,
                    signal_strength=signal_strength,
                    strategy_type="TEST",
                    total_risk_percent=1.0,
                    entries=[],
                    exits=[],
                    stop_loss=None,
                    max_risk_reward=2.0,
                    avg_risk_reward=1.5,
                    expected_hold_time="1-2 hours",
                    confidence_level="MEDIUM",
                    technical_summary="Mock test",
                    market_context="Testing",
                    risk_assessment="Mock risk"
                )
        
        mock_calc = MockCalculatorV3()
        enhancer = CalculatorEnhancer(mock_calc)
        stats = enhancer.get_recalculation_stats()
        
        logger.info(f"✅ Test exitoso")
        logger.info(f"📊 Stats: {stats}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Test falló: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    test_calculator_enhancer()