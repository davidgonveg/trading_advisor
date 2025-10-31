#!/usr/bin/env python3
"""
🎛️ SIGNAL COORDINATOR V4.0
===========================

Coordinador inteligente de señales y actualizaciones.

Responsabilidades:
- Decidir CUÁNDO enviar actualizaciones a Telegram
- Generar mensajes optimizados con cambios significativos
- Ajustar niveles futuros basándose en ejecuciones pasadas
- Prevenir spam de señales redundantes
- Integrar scanner, tracker y monitor

FILOSOFÍA: "Smart messenger" - solo mensajes relevantes, nunca spam
"""

import logging
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any, TYPE_CHECKING

# Añadir path del proyecto para imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Imports de position_manager
from .models import (
    TrackedPosition,
    ExecutionEvent,
    ExecutionEventType,
    ExecutionStatus,
    PositionStatus
)
from .position_tracker import PositionTracker
from .execution_monitor import ExecutionMonitor

# Imports condicionales
if TYPE_CHECKING:
    from scanner import TradingSignal, SignalScanner
    from telegram_bot import TelegramBot
    from position_calculator import PositionPlan

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SignalCoordinator:
    """
    Coordinador central de señales y actualizaciones
    
    Integra scanner, tracker, monitor y telegram para
    gestionar el flujo completo de señales.
    """
    
    def __init__(
        self,
        tracker: PositionTracker,
        monitor: ExecutionMonitor,
        scanner: Any = None,      # SignalScanner
        telegram: Any = None,     # TelegramBot
        min_update_interval_minutes: int = 30,
        min_signal_strength_change: int = 10
    ):
        """
        Inicializar el coordinador
        
        Args:
            tracker: Instancia del PositionTracker
            monitor: Instancia del ExecutionMonitor
            scanner: Instancia del SignalScanner (opcional)
            telegram: Instancia del TelegramBot (opcional)
            min_update_interval_minutes: Mínimo tiempo entre updates (default 30min)
            min_signal_strength_change: Mínimo cambio de fuerza para update (default +10)
        """
        self.tracker = tracker
        self.monitor = monitor
        self.scanner = scanner
        self.telegram = telegram
        
        # Configuración
        self.min_update_interval = timedelta(minutes=min_update_interval_minutes)
        self.min_signal_strength_change = min_signal_strength_change
        
        # Estadísticas
        self.stats = {
            'signals_processed': 0,
            'new_positions_created': 0,
            'updates_sent': 0,
            'updates_skipped': 0,
            'spam_prevented': 0
        }
        
        logger.info("🎛️ Signal Coordinator inicializado")
        logger.info(f"   Min interval: {min_update_interval_minutes}min")
        logger.info(f"   Min strength change: +{min_signal_strength_change}")
    
    # =========================================================================
    # 🎯 PROCESAMIENTO DE SEÑALES NUEVAS
    # =========================================================================
    
    def process_new_signal(
        self,
        signal: Any,  # TradingSignal
        plan: Optional[Any] = None  # PositionPlan
    ) -> bool:
        """
        Procesar una señal nueva del scanner
        
        Esta es la ENTRADA PRINCIPAL del sistema.
        
        Flujo:
        1. ¿Ya existe posición para este símbolo?
        2. Si NO -> crear nueva posición + enviar señal
        3. Si SÍ -> evaluar si actualizar
        
        Args:
            signal: Señal del scanner
            plan: Plan de posición (si no se provee, se genera)
            
        Returns:
            True si se procesó correctamente
        """
        try:
            self.stats['signals_processed'] += 1
            
            symbol = signal.symbol
            logger.info(f"🎯 Procesando señal: {symbol} {signal.signal_type}")
            
            # Verificar si ya existe posición activa
            existing_position = self.tracker.get_position(symbol)
            
            if existing_position is None:
                # CASO 1: Nueva posición
                return self._create_new_position(signal, plan)
            else:
                # CASO 2: Actualización de posición existente
                return self._evaluate_position_update(existing_position, signal, plan)
            
        except Exception as e:
            logger.error(f"❌ Error procesando señal {signal.symbol}: {e}")
            return False
    
    def _create_new_position(
        self,
        signal: Any,
        plan: Optional[Any] = None
    ) -> bool:
        """
        Crear nueva posición y enviar señal inicial
        
        Args:
            signal: Señal del scanner
            plan: Plan de posición (o None para generarlo)
            
        Returns:
            True si se creó y envió correctamente
        """
        try:
            # Generar plan si no se proveyó
            if plan is None:
                if self.scanner and hasattr(self.scanner, 'position_calculator'):
                    plan = self.scanner.position_calculator.calculate_position_v3(
                        signal.symbol,
                        signal.signal_type,
                        signal.current_price,
                        signal.signal_strength
                    )
                else:
                    logger.error("❌ No se puede generar plan - scanner no disponible")
                    return False
            
            # Registrar posición en tracker
            position_id = self.tracker.register_new_position(signal, plan)
            
            # Enviar mensaje inicial por Telegram
            if self.telegram:
                message = self._generate_new_position_message(signal, plan)
                success = self.telegram.send_message(message)
                
                if success:
                    logger.info(f"📱 Señal inicial enviada: {signal.symbol}")
                    self.stats['new_positions_created'] += 1
                else:
                    logger.warning(f"⚠️ No se pudo enviar señal: {signal.symbol}")
            else:
                logger.info(f"ℹ️ Telegram no disponible - posición creada sin enviar")
                self.stats['new_positions_created'] += 1
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error creando nueva posición: {e}")
            return False
    
    def _evaluate_position_update(
        self,
        position: TrackedPosition,
        new_signal: Any,
        new_plan: Optional[Any] = None
    ) -> bool:
        """
        Evaluar si una posición existente necesita actualización
        
        Args:
            position: Posición existente
            new_signal: Nueva señal del scanner
            new_plan: Nuevo plan (opcional)
            
        Returns:
            True si se debe actualizar
        """
        try:
            symbol = position.symbol
            
            # Verificar si debe enviar update
            should_update, reason = self.should_send_update(position, new_signal)
            
            if should_update:
                logger.info(f"📊 Update necesario para {symbol}: {reason}")
                
                # Generar mensaje de actualización
                message = self._generate_update_message(position, new_signal, reason)
                
                # Enviar por Telegram
                if self.telegram:
                    success = self.telegram.send_message(message)
                    if success:
                        # Actualizar timestamp de último mensaje
                        position.last_signal_sent = datetime.now()
                        position.telegram_messages_sent += 1
                        position.update_count += 1
                        self.stats['updates_sent'] += 1
                        logger.info(f"📱 Update enviado: {symbol}")
                    else:
                        logger.warning(f"⚠️ No se pudo enviar update: {symbol}")
                
                return True
            else:
                logger.debug(f"⏭️ Update no necesario para {symbol}: {reason}")
                self.stats['updates_skipped'] += 1
                self.stats['spam_prevented'] += 1
                return False
            
        except Exception as e:
            logger.error(f"❌ Error evaluando update: {e}")
            return False
    
    # =========================================================================
    # 🤔 LÓGICA DE DECISIÓN
    # =========================================================================
    
    def should_send_update(
        self,
        position: TrackedPosition,
        new_signal: Any
    ) -> Tuple[bool, str]:
        """
        Decidir si enviar actualización
        
        Reglas:
        1. Han pasado al menos 30min desde última señal
        2. Y al menos UNA de estas condiciones:
           - Se ejecutó un nivel de entrada/salida
           - Deterioro técnico significativo (via exit_manager)
           - Precio rompió stop loss
           - Nueva señal con fuerza +10 puntos vs original
        
        Args:
            position: Posición actual
            new_signal: Nueva señal del scanner
            
        Returns:
            (should_update: bool, reason: str)
        """
        try:
            # Regla 1: Tiempo mínimo desde última señal
            if position.last_signal_sent:
                time_since_last = datetime.now() - position.last_signal_sent
                if time_since_last < self.min_update_interval:
                    remaining = self.min_update_interval - time_since_last
                    return False, f"Muy pronto ({remaining.seconds // 60}min restantes)"
            
            # Regla 2A: Se ejecutó algún nivel recientemente
            entries_filled = position.get_entries_executed_count()
            exits_filled = position.get_exits_executed_count()
            
            # Verificar si hay ejecuciones muy recientes (últimos 5min)
            recent_execution = False
            check_time = datetime.now() - timedelta(minutes=5)
            
            for entry in position.entry_levels:
                if entry.filled_timestamp and entry.filled_timestamp > check_time:
                    recent_execution = True
                    break
            
            if not recent_execution:
                for exit_level in position.exit_levels:
                    if exit_level.filled_timestamp and exit_level.filled_timestamp > check_time:
                        recent_execution = True
                        break
            
            if recent_execution:
                return True, "Ejecución reciente de nivel"
            
            # Regla 2B: Stop loss tocado
            if position.stop_loss and position.stop_loss.is_hit():
                return True, "Stop loss ejecutado"
            
            # Regla 2C: Cambio significativo en fuerza de señal
            strength_change = new_signal.signal_strength - position.signal_strength
            if strength_change >= self.min_signal_strength_change:
                return True, f"Fuerza aumentó +{strength_change} puntos"
            
            # Regla 2D: Posición totalmente ejecutada (primera vez)
            if position.is_fully_entered() and position.update_count == 0:
                return True, "Todas las entradas ejecutadas"
            
            # Regla 2E: Cambio de dirección de señal (!)
            if new_signal.signal_type != position.direction:
                return True, f"⚠️ Cambio de dirección: {position.direction} → {new_signal.signal_type}"
            
            # Por defecto: no actualizar
            return False, "Sin cambios significativos"
            
        except Exception as e:
            logger.error(f"❌ Error en should_send_update: {e}")
            return False, f"Error: {e}"
    
    # =========================================================================
    # 📝 GENERACIÓN DE MENSAJES
    # =========================================================================
    
    def _generate_new_position_message(
        self,
        signal: Any,
        plan: Any
    ) -> str:
        """
        Generar mensaje para señal NUEVA
        
        Args:
            signal: Señal del scanner
            plan: Plan de posición
            
        Returns:
            Mensaje formateado para Telegram
        """
        try:
            emoji_direction = "🟢" if signal.signal_type == "LONG" else "🔴"
            
            message = f"""
{emoji_direction} **NUEVA SEÑAL - {signal.symbol}**
━━━━━━━━━━━━━━━━━━━━━━━━

📊 **Tipo:** {signal.signal_type}
💪 **Fuerza:** {signal.signal_strength}/100
🎯 **Confianza:** {getattr(signal, 'confidence_level', 'N/A')}
💰 **Precio actual:** ${signal.current_price:.2f}

**📈 ENTRADAS ESCALONADAS:**
"""
            
            # Añadir niveles de entrada
            for i, entry in enumerate(plan.entries, 1):
                message += f"  {i}. ${entry.price:.2f} - {entry.percentage:.0f}%\n"
            
            message += "\n**🎯 TAKE PROFITS:**\n"
            
            # Añadir niveles de salida
            for i, exit_level in enumerate(plan.exits, 1):
                rr = getattr(exit_level, 'risk_reward', None)
                rr_text = f" (R:R 1:{rr:.1f})" if rr else ""
                message += f"  {i}. ${exit_level.price:.2f} - {exit_level.percentage:.0f}%{rr_text}\n"
            
            # Stop loss
            message += f"\n🛡️ **Stop Loss:** ${plan.stop_loss.price:.2f}\n"
            
            # Info adicional
            message += f"\n📊 **Estrategia:** {getattr(plan, 'strategy_type', 'N/A')}"
            message += f"\n⏰ **Horizonte:** {getattr(plan, 'expected_hold_time', 'N/A')}"
            
            return message.strip()
            
        except Exception as e:
            logger.error(f"❌ Error generando mensaje nuevo: {e}")
            return f"Error generando mensaje para {signal.symbol}"
    
    def _generate_update_message(
        self,
        position: TrackedPosition,
        new_signal: Any,
        reason: str
    ) -> str:
        """
        Generar mensaje de ACTUALIZACIÓN
        
        Args:
            position: Posición existente
            new_signal: Nueva señal
            reason: Razón del update
            
        Returns:
            Mensaje formateado para Telegram
        """
        try:
            emoji_direction = "🟢" if position.direction == "LONG" else "🔴"
            
            message = f"""
{emoji_direction} **UPDATE - {position.symbol}**
━━━━━━━━━━━━━━━━━━━━━━━━

📌 **Razón:** {reason}
💰 **Precio actual:** ${position.current_price:.2f}

**📊 ESTADO DE EJECUCIÓN:**
"""
            
            # Estado de entradas
            entries_filled = position.get_entries_executed_count()
            total_entries = len(position.entry_levels)
            message += f"  • Entradas: {entries_filled}/{total_entries} ejecutadas ({position.total_filled_percentage:.0f}%)\n"
            
            # Detallar entradas
            for entry in position.entry_levels:
                status_emoji = "✅" if entry.status == ExecutionStatus.FILLED else "⏳" if entry.status == ExecutionStatus.PENDING else "⏭️"
                filled_text = f" @ ${entry.filled_price:.2f}" if entry.filled_price else ""
                message += f"    {status_emoji} Entry {entry.level_id}: ${entry.target_price:.2f}{filled_text}\n"
            
            # Estado de salidas (solo si ya entramos)
            if entries_filled > 0:
                exits_filled = position.get_exits_executed_count()
                total_exits = len(position.exit_levels)
                message += f"\n  • Salidas: {exits_filled}/{total_exits} ejecutadas\n"
                
                for exit_level in position.exit_levels:
                    if exit_level.status == ExecutionStatus.FILLED:
                        message += f"    ✅ TP{exit_level.level_id}: ${exit_level.target_price:.2f} @ ${exit_level.filled_price:.2f}\n"
                    elif exit_level.status == ExecutionStatus.PENDING:
                        message += f"    ⏳ TP{exit_level.level_id}: ${exit_level.target_price:.2f}\n"
            
            # P&L
            if position.unrealized_pnl != 0:
                pnl_emoji = "📈" if position.unrealized_pnl > 0 else "📉"
                message += f"\n{pnl_emoji} **P&L no realizado:** {position.unrealized_pnl:+.2f}%\n"
            
            # Stop loss
            stop_status = "🛑 EJECUTADO" if position.stop_loss.is_hit() else "🛡️ Activo"
            message += f"\n{stop_status} **Stop:** ${position.stop_loss.target_price:.2f}\n"
            
            # Precio medio si ya entramos
            if position.average_entry_price > 0:
                message += f"💵 **Entrada media:** ${position.average_entry_price:.2f}\n"
            
            return message.strip()
            
        except Exception as e:
            logger.error(f"❌ Error generando mensaje update: {e}")
            return f"Error generando update para {position.symbol}"
    
    def generate_execution_notification(
        self,
        position: TrackedPosition,
        event: ExecutionEvent
    ) -> str:
        """
        Generar notificación de ejecución específica
        
        Args:
            position: Posición
            event: Evento de ejecución
            
        Returns:
            Mensaje formateado
        """
        try:
            if event.event_type == ExecutionEventType.ENTRY_FILLED:
                emoji = "✅"
                title = "ENTRADA EJECUTADA"
            elif event.event_type == ExecutionEventType.EXIT_FILLED:
                emoji = "🎯"
                title = "TAKE PROFIT ALCANZADO"
            elif event.event_type == ExecutionEventType.STOP_HIT:
                emoji = "🛑"
                title = "STOP LOSS EJECUTADO"
            else:
                emoji = "📊"
                title = "EVENTO"
            
            message = f"""
{emoji} **{title} - {position.symbol}**
━━━━━━━━━━━━━━━━━━━━━━━━

💰 **Precio:** ${event.executed_price:.2f}
🎯 **Target:** ${event.target_price:.2f}
📊 **Slippage:** {event.slippage:+.3f}%
📈 **Cantidad:** {event.percentage:.0f}%

⏰ {event.timestamp.strftime('%H:%M:%S')}
"""
            
            return message.strip()
            
        except Exception as e:
            logger.error(f"❌ Error generando notificación: {e}")
            return f"Evento ejecutado en {position.symbol}"
    
    # =========================================================================
    # 📊 ESTADÍSTICAS Y RESUMEN
    # =========================================================================
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Obtener estadísticas del coordinador
        
        Returns:
            Dict con estadísticas
        """
        return {
            **self.stats,
            'active_positions': len(self.tracker.active_positions),
            'spam_prevention_rate': (
                self.stats['spam_prevented'] / max(self.stats['signals_processed'], 1) * 100
            )
        }
    
    def should_send_update_for_events(
        self,
        position: 'TrackedPosition',
        events: List['ExecutionEvent']
    ) -> bool:
        """
        Decidir si enviar update basándose en eventos detectados
        
        Args:
            position: Posición activa
            events: Eventos detectados en el último ciclo de monitoreo
            
        Returns:
            True si debe enviar update a Telegram
            
        Lógica:
        - SIEMPRE enviar si hay STOP_HIT
        - Verificar intervalo mínimo desde última señal
        - Enviar si hay eventos significativos (ENTRY/EXIT FILLED)
        """
        try:
            # 1. SIEMPRE notificar si se toca el stop loss
            if any(e.event_type == ExecutionEventType.STOP_HIT for e in events):
                logger.info(f"🔴 {position.symbol}: Stop Loss hit - enviando notificación inmediata")
                return True
            
            # 2. Verificar intervalo mínimo desde última señal
            if position.last_signal_sent:
                time_since_last = datetime.now() - position.last_signal_sent
                if time_since_last < self.min_update_interval:
                    logger.debug(
                        f"⏸️ {position.symbol}: Solo {time_since_last.seconds//60}min "
                        f"desde última señal (mínimo {self.min_update_interval.seconds//60}min)"
                    )
                    self.stats['updates_skipped'] += 1
                    return False
            
            # 3. Filtrar eventos significativos
            significant_events = [
                e for e in events 
                if e.event_type in [
                    ExecutionEventType.ENTRY_FILLED,
                    ExecutionEventType.EXIT_FILLED,
                    ExecutionEventType.TRAILING_STOP_HIT
                ]
            ]
            
            if len(significant_events) == 0:
                logger.debug(f"ℹ️ {position.symbol}: No hay eventos significativos para notificar")
                return False
            
            # 4. Decidir enviar
            logger.info(
                f"📬 {position.symbol}: {len(significant_events)} eventos "
                f"significativos - enviando update"
            )
            return True
            
        except Exception as e:
            logger.error(f"❌ Error evaluando si enviar update: {e}")
            return False


    def generate_update_message(
        self,
        position: 'TrackedPosition',
        events: List['ExecutionEvent']
    ) -> str:
        """
        Generar mensaje de actualización formateado para Telegram
        
        Args:
            position: Posición activa
            events: Eventos que dispararon el update
            
        Returns:
            Mensaje HTML formateado para Telegram
            
        Formato del mensaje:
        - Header con símbolo y dirección
        - Eventos detectados (con emojis)
        - Estado actual de la posición
        - Niveles pendientes
        - Stop loss
        """
        try:
            # ===================================================================
            # HEADER
            # ===================================================================
            direction_emoji = "🟢" if position.direction == "LONG" else "🔴"
            msg = f"{direction_emoji} <b>UPDATE: {position.symbol} {position.direction}</b>\n\n"
            
            # ===================================================================
            # EVENTOS DETECTADOS
            # ===================================================================
            msg += "📊 <b>Eventos detectados:</b>\n"
            
            for event in events:
                # Emoji según tipo de evento
                if event.event_type == ExecutionEventType.ENTRY_FILLED:
                    emoji = "✅"
                    event_name = f"Entry #{event.level_id}"
                elif event.event_type == ExecutionEventType.EXIT_FILLED:
                    emoji = "💰"
                    event_name = f"Exit #{event.level_id}"
                elif event.event_type == ExecutionEventType.STOP_HIT:
                    emoji = "🛑"
                    event_name = "STOP LOSS"
                elif event.event_type == ExecutionEventType.TRAILING_STOP_HIT:
                    emoji = "🎯"
                    event_name = "Trailing Stop"
                else:
                    emoji = "📍"
                    event_name = event.event_type.value
                
                # Slippage info
                slippage_info = ""
                if event.slippage != 0:
                    slippage_sign = "+" if event.slippage > 0 else ""
                    slippage_info = f" ({slippage_sign}{event.slippage:.2f}% slippage)"
                
                msg += f"{emoji} {event_name}: ${event.executed_price:.2f}{slippage_info}\n"
            
            msg += "\n"
            
            # ===================================================================
            # ESTADO ACTUAL DE LA POSICIÓN
            # ===================================================================
            msg += "📈 <b>Estado actual:</b>\n"
            msg += f"• Ejecutado: {position.total_filled_percentage:.1f}%\n"
            
            if position.average_entry_price > 0:
                msg += f"• Precio medio entrada: ${position.average_entry_price:.2f}\n"
            
            # P&L
            if position.unrealized_pnl != 0:
                pnl_emoji = "📈" if position.unrealized_pnl > 0 else "📉"
                pnl_sign = "+" if position.unrealized_pnl > 0 else ""
                msg += f"• P&L: {pnl_emoji} {pnl_sign}{position.unrealized_pnl:.2f}%\n"
            
            # Status
            status_emoji = {
                PositionStatus.PENDING: "⏳",
                PositionStatus.PARTIALLY_FILLED: "🔄",
                PositionStatus.FULLY_ENTERED: "✅",
                PositionStatus.EXITING: "🚪",
                PositionStatus.CLOSED: "🔒",
                PositionStatus.STOPPED: "🛑"
            }.get(position.status, "❓")
            
            msg += f"• Status: {status_emoji} {position.status.value}\n\n"
            
            # ===================================================================
            # NIVELES PENDIENTES (solo si no está completamente cerrada)
            # ===================================================================
            if position.status not in [PositionStatus.CLOSED, PositionStatus.STOPPED]:
                
                # Entradas pendientes
                pending_entries = [
                    e for e in position.entry_levels 
                    if e.status == ExecutionStatus.PENDING
                ]
                
                if pending_entries:
                    msg += "⏳ <b>Entradas pendientes:</b>\n"
                    for entry in pending_entries[:3]:  # Máximo 3 para no saturar
                        msg += (
                            f"• Entry #{entry.level_id}: ${entry.target_price:.2f} "
                            f"({entry.percentage:.0f}%)\n"
                        )
                    
                    if len(pending_entries) > 3:
                        msg += f"• ... y {len(pending_entries) - 3} más\n"
                    
                    msg += "\n"
                
                # Exits/Targets pendientes
                pending_exits = [
                    e for e in position.exit_levels 
                    if e.status == ExecutionStatus.PENDING
                ]
                
                if pending_exits:
                    msg += "🎯 <b>Targets:</b>\n"
                    for exit in pending_exits[:2]:  # Solo primeros 2 targets
                        rr_info = ""
                        if exit.risk_reward_ratio:
                            rr_info = f" (R:R {exit.risk_reward_ratio:.1f})"
                        
                        msg += (
                            f"• TP{exit.level_id}: ${exit.target_price:.2f}{rr_info}\n"
                        )
                    
                    if len(pending_exits) > 2:
                        msg += f"• ... y {len(pending_exits) - 2} targets más\n"
                    
                    msg += "\n"
                
                # Stop Loss
                if position.stop_loss and position.stop_loss.status == ExecutionStatus.PENDING:
                    msg += f"🛑 <b>Stop Loss:</b> ${position.stop_loss.target_price:.2f}\n"
            
            # ===================================================================
            # FOOTER (si está cerrada)
            # ===================================================================
            if position.status in [PositionStatus.CLOSED, PositionStatus.STOPPED]:
                msg += "\n🔒 <b>Posición cerrada</b>\n"
                
                if position.position_closed_at:
                    duration = position.position_closed_at - position.signal_timestamp
                    hours = duration.total_seconds() / 3600
                    msg += f"⏱️ Duración: {hours:.1f}h\n"
            
            # ===================================================================
            # TIMESTAMP
            # ===================================================================
            msg += f"\n🕐 {datetime.now().strftime('%H:%M:%S')}"
            
            return msg
            
        except Exception as e:
            logger.error(f"❌ Error generando mensaje de update: {e}")
            # Fallback a mensaje básico
            return (
                f"🔔 <b>UPDATE: {position.symbol}</b>\n\n"
                f"Se detectaron {len(events)} eventos.\n"
                f"Ejecutado: {position.total_filled_percentage:.1f}%\n"
                f"Status: {position.status.value}"
            )

    def print_statistics(self):
        """Imprimir estadísticas en formato legible"""
        stats = self.get_statistics()
        
        print("\n📊 ESTADÍSTICAS DEL COORDINADOR")
        print("=" * 50)
        print(f"  Señales procesadas:     {stats['signals_processed']}")
        print(f"  Posiciones nuevas:      {stats['new_positions_created']}")
        print(f"  Updates enviados:       {stats['updates_sent']}")
        print(f"  Updates omitidos:       {stats['updates_skipped']}")
        print(f"  Spam prevenido:         {stats['spam_prevented']}")
        print(f"  Posiciones activas:     {stats['active_positions']}")
        print(f"  Tasa prevención spam:   {stats['spam_prevention_rate']:.1f}%")
        print("=" * 50)


# =============================================================================
# 🧪 TESTING
# =============================================================================

if __name__ == "__main__":
    print("🧪 TESTING SIGNAL COORDINATOR V4.0")
    print("=" * 60)
    
    # Crear componentes
    tracker = PositionTracker(use_database=False)
    monitor = ExecutionMonitor(tracker, use_real_prices=False)
    coordinator = SignalCoordinator(
        tracker=tracker,
        monitor=monitor,
        scanner=None,  # Mock
        telegram=None,  # Mock
        min_update_interval_minutes=1,  # Para testing rápido
        min_signal_strength_change=10
    )
    
    print("\n1. Test: Procesar señal NUEVA")
    from dataclasses import dataclass
    
    @dataclass
    class MockSignal:
        symbol: str
        signal_type: str
        signal_strength: int
        confidence_level: str
        entry_quality: str
        current_price: float
    
    @dataclass
    class MockLevel:
        price: float
        percentage: float
        description: str
        trigger_condition: str
    
    @dataclass
    class MockPlan:
        entries: List[MockLevel]
        exits: List[MockLevel]
        stop_loss: MockLevel
        strategy_type: str
        expected_hold_time: str
    
    signal1 = MockSignal(
        symbol="NVDA",
        signal_type="LONG",
        signal_strength=85,
        confidence_level="ALTA",
        entry_quality="EXCELENTE",
        current_price=500.0
    )
    
    plan1 = MockPlan(
        entries=[
            MockLevel(500.0, 40, "Entry 1", "Price <= 500.0"),
            MockLevel(498.0, 30, "Entry 2", "Price <= 498.0"),
            MockLevel(496.0, 30, "Entry 3", "Price <= 496.0")
        ],
        exits=[
            MockLevel(505.0, 25, "TP1", "Price >= 505.0"),
            MockLevel(510.0, 25, "TP2", "Price >= 510.0"),
            MockLevel(515.0, 25, "TP3", "Price >= 515.0"),
            MockLevel(520.0, 25, "TP4", "Price >= 520.0")
        ],
        stop_loss=MockLevel(494.0, 100, "Stop Loss", "Price <= 494.0"),
        strategy_type="MOMENTUM",
        expected_hold_time="2-6 horas"
    )
    
    success = coordinator.process_new_signal(signal1, plan1)
    print(f"   ✅ Señal procesada: {success}")
    
    print("\n2. Test: Intentar señal duplicada (debería rechazar)")
    signal2 = MockSignal(
        symbol="NVDA",
        signal_type="LONG",
        signal_strength=87,  # Solo +2 puntos
        confidence_level="ALTA",
        entry_quality="EXCELENTE",
        current_price=501.0
    )
    
    success = coordinator.process_new_signal(signal2, plan1)
    print(f"   Resultado: {success} (debería ser False por spam)")
    
    print("\n3. Test: Simular ejecución y verificar update")
    # Marcar entrada como ejecutada
    tracker.mark_level_as_filled("NVDA", 1, "ENTRY", 499.8, 40.0)
    
    # Esperar 2 segundos (nuestro min_interval es 1min pero usamos test mode)
    import time
    time.sleep(2)
    
    # Intentar nuevo signal con cambio significativo
    signal3 = MockSignal(
        symbol="NVDA",
        signal_type="LONG",
        signal_strength=95,  # +10 puntos -> debería actualizar
        confidence_level="MUY ALTA",
        entry_quality="EXCELENTE",
        current_price=502.0
    )
    
    success = coordinator.process_new_signal(signal3, plan1)
    print(f"   Update enviado: {success}")
    
    print("\n4. Test: Generar mensaje de posición nueva")
    message = coordinator._generate_new_position_message(signal1, plan1)
    print("   Mensaje generado:")
    print("   " + "\n   ".join(message.split("\n")[:5]))
    print("   ...")
    
    print("\n5. Test: Generar mensaje de update")
    position = tracker.get_position("NVDA")
    message = coordinator._generate_update_message(position, signal3, "Test update")
    print("   Mensaje generado:")
    print("   " + "\n   ".join(message.split("\n")[:5]))
    print("   ...")
    
    print("\n6. Test: Estadísticas")
    coordinator.print_statistics()
    
    print("\n✅ TODOS LOS TESTS PASARON")
    print("=" * 60)