#!/usr/bin/env python3
"""
🔍 SCANNER ENHANCER - POSITION STATE AWARENESS V3.0
==================================================

Enhancer que extiende el scanner.py existente con conciencia de estados de posición.
Evita generar señales duplicadas para posiciones ya existentes y coordina con el
sistema de estados para gestión inteligente de señales.

🎯 FUNCIONALIDADES:
1. Estado-aware scanning - No regenera señales para posiciones existentes
2. Evaluación de nuevas oportunidades en símbolos sin posiciones
3. Re-evaluación de posiciones en estados específicos (PARTIALLY_FILLED, WATCHING)
4. Coordinación con state_machine para transiciones automáticas
5. Filtros de calidad mejorados basados en historial de posiciones

🔧 INTEGRACIÓN:
- Se activa mediante config.USE_POSITION_MANAGEMENT = True
- Extiende scanner.py SIN modificarlo (mantiene compatibilidad)
- Usa los mismos TradingSignal objects para consistencia
- Coordina con la base de datos para obtener estados actuales

🎯 LÓGICA DE SCANNING STATE-AWARE:
- NUEVO símbolo → Scanning completo normal
- POSICIÓN ACTIVA → Skip scanning (evita duplicados)  
- PARTIALLY_FILLED → Re-evaluar solo condiciones de entrada
- WATCHING → Evaluar si condiciones mejoraron para reactivar
- CLOSED → Evaluar nueva oportunidad con cooldown period
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass
import pytz

# Importar core components
from scanner import SignalScanner, TradingSignal
from database.connection import get_connection
from database.position_queries import PositionQueries

# Importar position management system
from .states import PositionStatus, EntryStatus, ExitStatus
from .data_models import EnhancedPosition, ExecutionLevel
from .state_machine import PositionStateMachine
import config

logger = logging.getLogger(__name__)

@dataclass
class ScanningContext:
    """Contexto de scanning para un símbolo específico"""
    symbol: str
    current_position: Optional[EnhancedPosition] = None
    position_status: Optional[PositionStatus] = None
    last_signal_time: Optional[datetime] = None
    cooldown_until: Optional[datetime] = None
    should_scan: bool = True
    scan_reason: str = ""


class ScannerEnhancer:
    """
    Enhancer que extiende SignalScanner con conciencia de estados de posición
    """
    
    def __init__(self, base_scanner: SignalScanner):
        """
        Inicializar el enhancer con el scanner base existente
        
        Args:
            base_scanner: Instancia de SignalScanner existente
        """
        self.base_scanner = base_scanner
        self.position_queries = PositionQueries()
        self.state_machine = PositionStateMachine()
        
        # Cache para optimizar consultas
        self._position_cache: Dict[str, EnhancedPosition] = {}
        self._cache_expiry: Dict[str, datetime] = {}
        self._cache_timeout = timedelta(minutes=5)  # Cache 5 minutos
        
        # Configuración del enhancer
        self.cooldown_periods = {
            'CLOSED_PROFIT': timedelta(hours=2),    # 2h después de cerrar con ganancia
            'CLOSED_LOSS': timedelta(minutes=30),   # 30min después de cerrar con pérdida
            'STOPPED_OUT': timedelta(hours=1),      # 1h después de stop loss
            'CANCELLED': timedelta(minutes=15)      # 15min después de cancelar
        }
        
        logger.info("✅ Scanner Enhancer inicializado con position state awareness")
    
    def scan_with_state_awareness(self, symbols: List[str]) -> List[TradingSignal]:
        """
        Scan inteligente que considera estados de posición existentes
        
        Args:
            symbols: Lista de símbolos a analizar
            
        Returns:
            Lista de TradingSignal válidos (sin duplicados de posiciones activas)
        """
        logger.info(f"🔍 Iniciando scan state-aware para {len(symbols)} símbolos")
        
        # STEP 1: Evaluar contexto de scanning para cada símbolo
        scanning_contexts = []
        for symbol in symbols:
            context = self._evaluate_scanning_context(symbol)
            scanning_contexts.append(context)
            
            if not context.should_scan:
                logger.debug(f"⏭️ Skip {symbol}: {context.scan_reason}")
        
        # STEP 2: Filtrar símbolos que requieren scanning
        symbols_to_scan = [ctx.symbol for ctx in scanning_contexts if ctx.should_scan]
        
        if not symbols_to_scan:
            logger.info("📊 No hay símbolos que requieran scanning en este momento")
            return []
        
        logger.info(f"🎯 Scanning {len(symbols_to_scan)}/{len(symbols)} símbolos que requieren evaluación")
        
        # STEP 3: Ejecutar scanning en símbolos válidos usando el scanner base
        new_signals = []
        for symbol in symbols_to_scan:
            try:
                signal = self.base_scanner.scan_single_symbol(symbol)
                if signal:
                    # Validar que la señal es apropiada considerando el contexto
                    context = next(ctx for ctx in scanning_contexts if ctx.symbol == symbol)
                    if self._validate_signal_with_context(signal, context):
                        new_signals.append(signal)
                        logger.info(f"✅ Nueva señal válida: {symbol} {signal.signal_type}")
                    else:
                        logger.debug(f"🚫 Señal filtrada por contexto: {symbol}")
                        
            except Exception as e:
                logger.error(f"❌ Error scanning {symbol}: {e}")
                continue
        
        # STEP 4: Procesar señales para posiciones en estados específicos
        enhanced_signals = self._process_partial_position_signals(scanning_contexts)
        new_signals.extend(enhanced_signals)
        
        logger.info(f"✅ Scan completado: {len(new_signals)} señales válidas generadas")
        return new_signals
    
    def _evaluate_scanning_context(self, symbol: str) -> ScanningContext:
        """
        Evaluar el contexto de scanning para un símbolo específico
        
        Args:
            symbol: Símbolo a evaluar
            
        Returns:
            ScanningContext con información para decisión de scanning
        """
        # Obtener posición actual (usar cache si está disponible)
        position = self._get_current_position(symbol)
        
        context = ScanningContext(
            symbol=symbol,
            current_position=position
        )
        
        if not position:
            # No hay posición - scanning completo normal
            context.should_scan = True
            context.scan_reason = "No position - normal scanning"
            return context
        
        # Hay posición - evaluar estado
        context.position_status = position.status
        context.last_signal_time = position.created_at
        
        # Lógica de decisión basada en estado
        if position.status == PositionStatus.ACTIVE:
            # Posición activa - no generar nuevas señales
            context.should_scan = False
            context.scan_reason = f"Active position {position.status.value}"
            
        elif position.status == PositionStatus.PARTIALLY_FILLED:
            # Parcialmente ejecutada - re-evaluar solo si han pasado >30min
            if self._should_reevaluate_partial(position):
                context.should_scan = True
                context.scan_reason = "Re-evaluate partial position"
            else:
                context.should_scan = False
                context.scan_reason = "Partial position - too soon to re-evaluate"
            
        elif position.status in [PositionStatus.CLOSED, PositionStatus.STOPPED_OUT, PositionStatus.CANCELLED]:
            # Posición cerrada - evaluar cooldown
            cooldown_until = self._calculate_cooldown_expiry(position)
            context.cooldown_until = cooldown_until
            
            if datetime.now(pytz.UTC) >= cooldown_until:
                context.should_scan = True
                context.scan_reason = f"Cooldown expired for {position.status.value}"
            else:
                context.should_scan = False
                remaining = (cooldown_until - datetime.now(pytz.UTC)).total_seconds() / 60
                context.scan_reason = f"Cooldown active for {remaining:.0f}min"
                
        else:
            # Estado desconocido - scanning por defecto
            context.should_scan = True
            context.scan_reason = f"Unknown state {position.status} - default scanning"
        
        return context
    
    def _get_current_position(self, symbol: str) -> Optional[EnhancedPosition]:
        """
        Obtener posición actual para un símbolo (con cache)
        
        Args:
            symbol: Símbolo a consultar
            
        Returns:
            EnhancedPosition si existe, None si no hay posición
        """
        # Verificar cache
        if symbol in self._position_cache:
            if datetime.now() < self._cache_expiry.get(symbol, datetime.min):
                return self._position_cache[symbol]
        
        # Cache expirado o no existe - consultar DB
        try:
            position = self.position_queries.get_active_position(symbol)
            
            # Actualizar cache
            self._position_cache[symbol] = position
            self._cache_expiry[symbol] = datetime.now() + self._cache_timeout
            
            return position
            
        except Exception as e:
            logger.error(f"❌ Error obteniendo posición para {symbol}: {e}")
            return None
    
    def _should_reevaluate_partial(self, position: EnhancedPosition) -> bool:
        """
        Determinar si una posición parcialmente ejecutada debe re-evaluarse
        
        Args:
            position: Posición a evaluar
            
        Returns:
            True si debe re-evaluarse
        """
        if not position.updated_at:
            return True
        
        # Re-evaluar solo si han pasado >30 minutos desde última actualización
        time_since_update = datetime.now(pytz.UTC) - position.updated_at
        return time_since_update > timedelta(minutes=30)
    
    def _calculate_cooldown_expiry(self, position: EnhancedPosition) -> datetime:
        """
        Calcular cuándo expira el cooldown para una posición cerrada
        
        Args:
            position: Posición cerrada
            
        Returns:
            Timestamp cuando expira el cooldown
        """
        if not position.updated_at:
            return datetime.now(pytz.UTC)
        
        # Obtener periodo de cooldown basado en cómo se cerró
        if position.status == PositionStatus.CLOSED:
            # Determinar si fue ganancia o pérdida
            if position.total_pnl_percent and position.total_pnl_percent > 0:
                cooldown = self.cooldown_periods['CLOSED_PROFIT']
            else:
                cooldown = self.cooldown_periods['CLOSED_LOSS']
        else:
            cooldown = self.cooldown_periods.get(position.status.value, timedelta(hours=1))
        
        return position.updated_at + cooldown
    
    def _validate_signal_with_context(self, signal: TradingSignal, context: ScanningContext) -> bool:
        """
        Validar que una señal es apropiada dado el contexto de la posición
        
        Args:
            signal: Señal generada por el scanner
            context: Contexto de scanning del símbolo
            
        Returns:
            True si la señal es válida para el contexto
        """

        
        if context.position_status == PositionStatus.PARTIALLY_FILLED:
            # Para posiciones parciales, verificar que la dirección coincide
            if context.current_position:
                expected_direction = context.current_position.direction.value
                if signal.signal_type != expected_direction:
                    logger.debug(f"📊 Señal {signal.symbol} rechazada: dirección inconsistente con posición parcial")
                    return False
        
        # Validación general: evitar señales de baja calidad después de pérdidas
        if (context.current_position and 
            context.current_position.total_pnl_percent and 
            context.current_position.total_pnl_percent < -5 and
            signal.confidence_level in ['LOW', 'MEDIUM']):
            logger.debug(f"📊 Señal {signal.symbol} rechazada: calidad insuficiente después de pérdida")
            return False
        
        return True
    
    def _process_partial_position_signals(self, contexts: List[ScanningContext]) -> List[TradingSignal]:
        """
        Procesar señales especiales para posiciones en estados específicos
        
        Args:
            contexts: Lista de contextos de scanning
            
        Returns:
            Lista de señales adicionales para posiciones especiales
        """
        enhanced_signals = []
        
        for context in contexts:
            if not context.current_position:
                continue
            
            try:
                # Generar señales de ajuste para posiciones parciales
                if context.position_status == PositionStatus.PARTIALLY_FILLED:
                    adjustment_signal = self._generate_partial_adjustment_signal(context)
                    if adjustment_signal:
                        enhanced_signals.append(adjustment_signal)
                        
            except Exception as e:
                logger.error(f"❌ Error procesando señal especial para {context.symbol}: {e}")
                continue
        
        return enhanced_signals
    
    def _generate_partial_adjustment_signal(self, context: ScanningContext) -> Optional[TradingSignal]:
        """
        Generar señal de ajuste para posición parcialmente ejecutada
        
        Args:
            context: Contexto con posición parcial
            
        Returns:
            TradingSignal de ajuste si es apropiado
        """
        position = context.current_position
        if not position:
            return None
        
        # Obtener indicadores actuales
        try:
            signal = self.base_scanner.scan_single_symbol(context.symbol)
            if not signal:
                return None
            
            # Validar que la dirección es consistente
            if signal.signal_type != position.direction.value:
                return None
            
            # Crear señal de ajuste con metadata especial
            signal.metadata = signal.metadata or {}
            signal.metadata.update({
                'adjustment_type': 'PARTIAL_FILL_CONTINUATION',
                'original_position_id': str(position.position_id),
                'remaining_levels': len([level for level in position.entry_levels if not level.executed])
            })
            
            logger.info(f"🔄 Señal de ajuste generada para {context.symbol} (posición parcial)")
            return signal
            
        except Exception as e:
            logger.error(f"❌ Error generando señal de ajuste para {context.symbol}: {e}")
            return None
    
    def _generate_reactivation_signal(self, context: ScanningContext) -> Optional[TradingSignal]:
        """
        Generar señal de reactivación para posición en watching
        
        Args:
            context: Contexto con posición en watching
            
        Returns:
            TradingSignal de reactivación si las condiciones mejoraron
        """
        position = context.current_position
        if not position:
            return None
        
        try:
            signal = self.base_scanner.scan_single_symbol(context.symbol)
            if not signal:
                return None
            
            # Solo reactivar si las condiciones mejoraron significativamente
            if signal.confidence_level not in ['HIGH', 'VERY_HIGH']:
                return None
            
            if signal.signal_strength < 75:  # Requiere alta fuerza
                return None
            
            # Crear señal de reactivación
            signal.metadata = signal.metadata or {}
            signal.metadata.update({
                'adjustment_type': 'WATCHING_REACTIVATION',
                'original_position_id': str(position.position_id),
                'reactivation_reason': f"Conditions improved to {signal.signal_strength}/100"
            })
            
            logger.info(f"🔄 Señal de reactivación generada para {context.symbol} (watching)")
            return signal
            
        except Exception as e:
            logger.error(f"❌ Error generando señal de reactivación para {context.symbol}: {e}")
            return None
    
    def get_position_state(self, symbol: str) -> Optional[Dict]:
        """
        Obtener estado actual de posición para un símbolo
        
        Args:
            symbol: Símbolo a consultar
            
        Returns:
            Diccionario con información del estado o None
        """
        position = self._get_current_position(symbol)
        if not position:
            return None
        
        return {
            'position_id': str(position.position_id),
            'status': position.status.value,
            'direction': position.direction.value,
            'symbol': position.symbol,
            'created_at': position.created_at.isoformat() if position.created_at else None,
            'entry_progress': position.entry_progress_percent,
            'exit_progress': position.exit_progress_percent,
            'unrealized_pnl': position.total_pnl_percent,
            'active_levels': len([l for l in position.entry_levels if not l.executed]),
            'can_generate_new_signal': False  # Por definición, si hay posición no se generan nuevas señales
        }
    
    def clear_cache(self):
        """Limpiar cache de posiciones (útil para testing)"""
        self._position_cache.clear()
        self._cache_expiry.clear()
        logger.debug("🧹 Cache de posiciones limpiado")
    
    def get_scanning_stats(self) -> Dict:
        """
        Obtener estadísticas del sistema de scanning state-aware
        
        Returns:
            Diccionario con estadísticas
        """
        try:
            total_positions = self.position_queries.get_active_positions_count()
            positions_by_status = self.position_queries.get_positions_by_status_count()
            
            return {
                'enhanced_scanning_enabled': True,
                'total_active_positions': total_positions,
                'positions_by_status': positions_by_status,
                'cache_size': len(self._position_cache),
                'cache_hit_ratio': self._calculate_cache_hit_ratio(),
                'cooldown_periods': {k: v.total_seconds()/60 for k, v in self.cooldown_periods.items()}
            }
            
        except Exception as e:
            logger.error(f"❌ Error obteniendo estadísticas de scanning: {e}")
            return {'error': str(e)}
    
    def _calculate_cache_hit_ratio(self) -> float:
        """Calcular ratio de hits del cache (simplificado)"""
        if not hasattr(self, '_cache_hits'):
            return 0.0
        return getattr(self, '_cache_hits', 0) / max(getattr(self, '_cache_requests', 1), 1)


# 🔧 INTEGRATION HELPER - Función para integrar con scanner.py existente
def enhance_scanner_if_enabled(scanner: SignalScanner) -> SignalScanner:
    """
    Helper function para activar enhancement del scanner si está habilitado en config
    
    Args:
        scanner: SignalScanner base existente
        
    Returns:
        Scanner original o ScannerEnhancer según configuración
    """
    if not getattr(config, 'USE_POSITION_MANAGEMENT', False):
        logger.info("📊 Position management desactivado - usando scanner básico")
        return scanner
    
    try:
        enhancer = ScannerEnhancer(scanner)
        logger.info("✅ Scanner enhanced with position state awareness")
        
        # Monkey-patch para mantener compatibilidad
        original_scan_symbols = scanner.scan_symbols
        
        def enhanced_scan_symbols(symbols):
            return enhancer.scan_with_state_awareness(symbols)
        
        scanner.scan_symbols = enhanced_scan_symbols
        scanner._enhancer = enhancer  # Mantener referencia
        
        return scanner
        
    except Exception as e:
        logger.error(f"❌ Error activando scanner enhancement: {e}")
        logger.warning("🔄 Fallback a scanner básico")
        return scanner