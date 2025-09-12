#!/usr/bin/env python3
"""
🚀 MAIN.PY - SISTEMA DE TRADING AUTOMATIZADO V2.2 CON EXIT MANAGEMENT
===================================================================

NUEVAS CARACTERÍSTICAS V2.2:
1. 🚪 Exit Management System - Reevaluación inteligente de posiciones
2. 📱 Alertas de deterioro por Telegram
3. 💼 Seguimiento automático de posiciones activas
4. 📊 Dashboard de posiciones en tiempo real

FLUJO COMPLETO:
- Detecta señales de entrada (como antes)
- Añade automáticamente a seguimiento
- Reevalúa posiciones cada ciclo
- Alerta cuando condiciones se deterioran
- Gestiona salidas inteligentes
"""

import logging
import signal
import sys
import time
from datetime import datetime, timedelta, time as dt_time
from typing import Optional, Dict, List
import pytz
import threading

# Importar módulos del sistema
import config
from scanner import SignalScanner, TradingSignal
from telegram_bot import TelegramBot

# Importar EXIT MANAGEMENT SYSTEM (NUEVO)
try:
    from exit_manager import ExitManager, ExitSignal, ExitUrgency, ActivePosition
    EXIT_MANAGER_AVAILABLE = True
    print("🚪 Exit Manager detectado y cargado")
except ImportError:
    EXIT_MANAGER_AVAILABLE = False
    print("⚠️ exit_manager.py no encontrado - ejecutando sin exit management")

# Importar smart enhancements
try:
    from smart_enhancements import integrate_smart_features
    SMART_FEATURES_AVAILABLE = True
    print("📈 Smart enhancements detectados y cargados")
except ImportError:
    SMART_FEATURES_AVAILABLE = False
    print("⚠️ smart_enhancements.py no encontrado - ejecutando sin mejoras extras")

# Configurar logging
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, 'INFO'),
    format=config.LOG_FORMAT,
    handlers=[
        logging.FileHandler(config.LOG_FILE, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class SmartTradingSystemWithExitManagement:
    """
    Sistema de trading con exit management integrado
    """
    
    def __init__(self):
        """Inicializar sistema completo con exit management"""
        logger.info("🚀 Inicializando Smart Trading System v2.2")
        
        # Componentes principales
        self.scanner = SignalScanner()
        self.telegram = TelegramBot()
        
        # 🚪 NUEVOS COMPONENTES EXIT MANAGEMENT
        if EXIT_MANAGER_AVAILABLE:
            self.exit_manager = ExitManager()
            logger.info("✅ Exit Manager activado")
        else:
            self.exit_manager = None
            logger.warning("⚠️ Exit Manager no disponible")
        
        self.running = False
        
        # Configuración de timezone
        self.market_tz = pytz.timezone(config.MARKET_TIMEZONE)
        
        # Estado del sistema
        self.total_scans = 0
        self.signals_sent = 0
        self.exit_alerts_sent = 0  # NUEVO contador
        self.positions_tracked = 0  # NUEVO contador
        self.consecutive_errors = 0
        self.max_consecutive_errors = 5
        self.last_scan_time = None
        self.next_scan_time = None
        
        # Threading para control
        self.scan_thread = None
        self.shutdown_event = threading.Event()
        
        # Horarios EXPANDIDOS
        self.market_sessions = [
            {
                'name': 'MORNING',
                'start': dt_time(9, 30),
                'end': dt_time(11, 30)
            },
            {
                'name': 'AFTERNOON',
                'start': dt_time(13, 30),
                'end': dt_time(15, 30)
            }
        ]
        
        self.scan_interval_minutes = config.SCAN_INTERVAL
        
        # Smart features
        self.smart_components = None
        if SMART_FEATURES_AVAILABLE:
            try:
                self.smart_components = integrate_smart_features()
                self._setup_enhanced_data_fetch()
                logger.info("✅ Smart enhancements activados")
            except Exception as e:
                logger.warning(f"⚠️ Error cargando smart enhancements: {e}")
                self.smart_components = None
        
        logger.info("✅ Smart Trading System v2.2 inicializado correctamente")
    
    def _setup_enhanced_data_fetch(self):
        """Reemplazar get_market_data con versión mejorada"""
        try:
            if self.smart_components and 'enhanced_data_fetch' in self.smart_components:
                enhanced_fetch = self.smart_components['enhanced_data_fetch']
                
                # Reemplazar en scanner
                self.scanner.indicators.get_market_data = enhanced_fetch
                
                # Reemplazar en exit manager si está disponible
                if self.exit_manager:
                    self.exit_manager.indicators.get_market_data = enhanced_fetch
                
                logger.info("🔧 Enhanced data fetch configurado")
        except Exception as e:
            logger.error(f"❌ Error configurando enhanced fetch: {e}")
    
    def is_market_open_now(self) -> bool:
        """Verificar si mercado está abierto AHORA"""
        try:
            now = datetime.now(self.market_tz)
            current_time = now.time()
            weekday = now.weekday()
            
            if weekday not in config.ALLOWED_WEEKDAYS:
                return False
            
            for session in self.market_sessions:
                if session['start'] <= current_time <= session['end']:
                    return True
            
            return False
        except Exception as e:
            logger.error(f"❌ Error verificando mercado: {e}")
            return False
    
    def get_next_market_session(self) -> Optional[datetime]:
        """Calcular próxima sesión de mercado"""
        try:
            now = datetime.now(self.market_tz)
            current_date = now.date()
            current_weekday = now.weekday()
            
            # Buscar próxima sesión HOY
            if current_weekday in config.ALLOWED_WEEKDAYS:
                for session in self.market_sessions:
                    session_start = datetime.combine(current_date, session['start'])
                    session_start = self.market_tz.localize(session_start)
                    
                    if session_start > now:
                        return session_start
            
            # Buscar próximo día hábil
            days_ahead = 1
            while days_ahead <= 7:
                future_date = current_date + timedelta(days=days_ahead)
                future_weekday = future_date.weekday()
                
                if future_weekday in config.ALLOWED_WEEKDAYS:
                    first_session = min(self.market_sessions, key=lambda x: x['start'])
                    next_session = datetime.combine(future_date, first_session['start'])
                    next_session = self.market_tz.localize(next_session)
                    return next_session
                
                days_ahead += 1
            
            return None
        except Exception as e:
            logger.error(f"❌ Error calculando próxima sesión: {e}")
            return None
    
    def smart_sleep_until_market(self) -> bool:
        """Dormir hasta próxima sesión"""
        try:
            if self.is_market_open_now():
                return True
            
            next_session = self.get_next_market_session()
            if not next_session:
                return False
            
            now = datetime.now(self.market_tz)
            total_sleep = (next_session - now).total_seconds()
            
            if total_sleep <= 0:
                return True
            
            hours = int(total_sleep // 3600)
            minutes = int((total_sleep % 3600) // 60)
            logger.info(f"😴 Mercado cerrado - Durmiendo {hours}h {minutes}m")
            
            # Dormir en chunks
            chunk_size = 300  # 5 minutos
            slept = 0
            
            while slept < total_sleep and not self.shutdown_event.is_set():
                sleep_chunk = min(chunk_size, total_sleep - slept)
                
                if self.shutdown_event.wait(sleep_chunk):
                    return False
                
                slept += sleep_chunk
                
                # Log progreso cada 30 minutos
                if slept % 1800 == 0:
                    remaining = total_sleep - slept
                    rem_hours = int(remaining // 3600)
                    rem_minutes = int((remaining % 3600) // 60)
                    logger.info(f"⏳ Durmiendo... {rem_hours}h {rem_minutes}m restantes")
            
            return not self.shutdown_event.is_set()
        except Exception as e:
            logger.error(f"❌ Error en smart sleep: {e}")
            return False
    
    def perform_scan(self) -> List[TradingSignal]:
        """Realizar escaneo con smart features"""
        try:
            logger.info(f"🔍 Iniciando escaneo #{self.total_scans + 1}")
            
            # Verificar mercado sigue abierto
            if not config.DEVELOPMENT_MODE and not self.is_market_open_now():
                logger.warning("⚠️ Mercado cerrado durante escaneo")
                return []
            
            # Realizar escaneo
            signals = self.scanner.scan_multiple_symbols(config.SYMBOLS)
            
            # Actualizar contadores
            self.total_scans += 1
            self.last_scan_time = datetime.now(self.market_tz)
            
            # Log resultado
            if signals:
                logger.info(f"✅ Escaneo completado: {len(signals)} señales detectadas")
                for signal in signals:
                    logger.info(f"   {signal.symbol}: {signal.signal_type} ({signal.signal_strength} pts)")
            else:
                logger.info("📊 Escaneo completado: Sin señales válidas")
            
            # Reset contador de errores
            self.consecutive_errors = 0
            
            return signals
        except Exception as e:
            self.consecutive_errors += 1
            logger.error(f"❌ Error escaneo #{self.consecutive_errors}: {e}")
            
            if self.consecutive_errors >= self.max_consecutive_errors:
                logger.critical(f"💥 Máximo errores alcanzado ({self.max_consecutive_errors})")
                self.running = False
            
            return []
    
    def perform_exit_evaluation(self) -> List[ExitSignal]:
        """🚪 NUEVA FUNCIÓN: Evaluar todas las posiciones para posibles salidas"""
        try:
            if not self.exit_manager:
                return []
            
            logger.info("🚪 Evaluando posiciones activas para exits...")
            
            # Verificar si hay posiciones
            positions_summary = self.exit_manager.get_positions_summary()
            total_positions = positions_summary.get('total_positions', 0)
            
            if total_positions == 0:
                logger.debug("📊 No hay posiciones activas para evaluar")
                return []
            
            logger.info(f"📊 Evaluando {total_positions} posiciones activas")
            
            # Evaluar todas las posiciones
            exit_signals = self.exit_manager.evaluate_all_positions()
            
            if exit_signals:
                logger.info(f"🚨 {len(exit_signals)} alertas de exit generadas")
                
                # Log resumen por urgencia
                urgent = sum(1 for s in exit_signals if s.urgency == ExitUrgency.EXIT_URGENT)
                recommended = sum(1 for s in exit_signals if s.urgency == ExitUrgency.EXIT_RECOMMENDED)
                watch = sum(1 for s in exit_signals if s.urgency == ExitUrgency.EXIT_WATCH)
                
                logger.info(f"   🚨 Urgente: {urgent} | ⚠️ Recomendado: {recommended} | 👀 Vigilar: {watch}")
                
                for signal in exit_signals:
                    logger.info(f"   {signal.symbol}: {signal.urgency.value} ({signal.exit_score} pts)")
            else:
                logger.info("✅ No hay alertas de exit necesarias")
            
            return exit_signals
            
        except Exception as e:
            logger.error(f"❌ Error en evaluación de exits: {e}")
            return []
    
    def format_exit_alert(self, exit_signal: ExitSignal) -> str:
        """Formatear alerta de exit para Telegram"""
        try:
            position = exit_signal.position
            urgency_emojis = {
                ExitUrgency.EXIT_WATCH: "👀",
                ExitUrgency.EXIT_RECOMMENDED: "⚠️", 
                ExitUrgency.EXIT_URGENT: "🚨"
            }
            urgency_emoji = urgency_emojis.get(exit_signal.urgency, "📊")
            
            # Color de PnL
            pnl_emoji = "🟢" if position.unrealized_pnl_pct >= 0 else "🔴"
            
            # Hora actual en España
            spain_tz = pytz.timezone('Europe/Madrid')
            spain_time = exit_signal.timestamp.astimezone(spain_tz)
            time_str = spain_time.strftime("%H:%M")
            
            # Construir mensaje
            message_lines = []
            
            # === CABECERA DE EXIT ===
            message_lines.append(f"{urgency_emoji} <b>ALERTA EXIT - {position.symbol}</b>")
            message_lines.append(f"🎯 <b>Posición:</b> {position.direction} | <b>Urgencia:</b> {exit_signal.urgency.value}")
            message_lines.append(f"📊 <b>Deterioro:</b> {exit_signal.exit_score}/100 puntos")
            message_lines.append(f"⏰ <b>Hora:</b> {time_str} España")
            message_lines.append("")
            
            # === ESTADO ACTUAL DE LA POSICIÓN ===
            message_lines.append("💼 <b>ESTADO POSICIÓN:</b>")
            message_lines.append(f"• <b>Precio entrada:</b> ${position.entry_price:.2f}")
            message_lines.append(f"• <b>Precio actual:</b> ${position.current_price:.2f}")
            message_lines.append(f"• <b>PnL no realizado:</b> {pnl_emoji} {position.unrealized_pnl_pct:+.1f}%")
            
            days_held = (datetime.now() - position.entry_time).days
            if days_held == 0:
                time_held = "< 1 día"
            else:
                time_held = f"{days_held} días"
            message_lines.append(f"• <b>Tiempo mantenida:</b> {time_held}")
            message_lines.append("")
            
            # === RECOMENDACIÓN CLARA ===
            message_lines.append("🎯 <b>RECOMENDACIÓN:</b>")
            if exit_signal.exit_percentage == 100:
                message_lines.append(f"🚨 <b>SALIR COMPLETAMENTE</b>")
            elif exit_signal.exit_percentage > 0:
                message_lines.append(f"⚠️ <b>SALIR {exit_signal.exit_percentage}% DE LA POSICIÓN</b>")
            else:
                message_lines.append(f"👀 <b>VIGILAR DE CERCA</b>")
            
            message_lines.append(f"💡 <i>{exit_signal.recommended_action}</i>")
            message_lines.append("")
            
            # === RAZONES TÉCNICAS ===
            message_lines.append("📉 <b>DETERIORO DETECTADO:</b>")
            for i, reason in enumerate(exit_signal.technical_reasons[:4], 1):  # Máximo 4 razones
                message_lines.append(f"• {reason}")
            message_lines.append("")
            
            # === MÉTRICAS ADICIONALES ===
            message_lines.append("📊 <b>ANÁLISIS:</b>")
            
            # Cambio de momentum
            momentum_change = exit_signal.momentum_change
            momentum_emoji = "📈" if momentum_change > 0 else "📉"
            message_lines.append(f"• <b>Momentum:</b> {momentum_emoji} {momentum_change:+.1f}% desde entrada")
            
            # Reversión de tendencia
            if exit_signal.trend_reversal:
                message_lines.append("• <b>Tendencia:</b> 🔄 Reversión detectada")
            
            # Divergencia de volumen
            if exit_signal.volume_divergence:
                message_lines.append("• <b>Volumen:</b> ⚠️ Divergencia preocupante")
            
            message_lines.append("")
            
            # === FOOTER ===
            if exit_signal.urgency == ExitUrgency.EXIT_URGENT:
                footer_msg = "🚨 <i>Acción requerida - Condiciones críticas</i>"
            elif exit_signal.urgency == ExitUrgency.EXIT_RECOMMENDED:
                footer_msg = "⚠️ <i>Salida recomendada - Riesgo elevado</i>"
            else:
                footer_msg = "👀 <i>Vigilancia requerida - Deterioro detectado</i>"
            
            message_lines.append(footer_msg)
            
            return "\n".join(message_lines)
            
        except Exception as e:
            logger.error(f"❌ Error formateando alerta exit: {e}")
            return f"❌ Error formateando alerta exit para {exit_signal.symbol}"
    
    def send_exit_alert(self, exit_signal: ExitSignal) -> bool:
        """Enviar alerta de exit por Telegram"""
        try:
            # Verificar si las alertas de exit están habilitadas
            if not config.ALERT_TYPES.get('EXIT_ALERTS', True):
                logger.info(f"📵 Alertas de exit deshabilitadas - No enviando {exit_signal.symbol}")
                return True
            
            # Solo enviar si es urgencia mínima
            if exit_signal.urgency == ExitUrgency.NO_EXIT or exit_signal.urgency == ExitUrgency.EXIT_WATCH:
                logger.debug(f"📊 {exit_signal.symbol}: Exit urgency muy baja - No enviando")
                return True
            
            # Formatear mensaje
            message = self.format_exit_alert(exit_signal)
            
            # Enviar mensaje
            success = self.telegram.send_message(message)
            
            if success:
                self.exit_alerts_sent += 1
                # Actualizar contador en la posición
                exit_signal.position.exit_alerts_sent += 1
                logger.info(f"✅ Alerta EXIT enviada: {exit_signal.symbol} - {exit_signal.urgency.value}")
            else:
                logger.error(f"❌ Error enviando alerta exit: {exit_signal.symbol}")
            
            return success
            
        except Exception as e:
            logger.error(f"❌ Error en send_exit_alert: {e}")
            return False
    
    def process_signals(self, signals: List[TradingSignal]) -> None:
        """Procesar y enviar señales + añadir al exit manager"""
        try:
            if not signals:
                return
            
            logger.info(f"📱 Procesando {len(signals)} señales...")
            
            for signal in signals:
                try:
                    # 1. Enviar alerta de señal (como antes)
                    success = self.telegram.send_signal_alert(signal)
                    
                    if success:
                        self.signals_sent += 1
                        logger.info(f"✅ Alerta enviada: {signal.symbol} {signal.signal_type}")
                        
                        # 2. 🚪 NUEVO: Añadir al exit manager para seguimiento
                        if self.exit_manager and signal.position_plan:
                            # Usar precio actual como precio de entrada simulado
                            entry_price = signal.current_price
                            added = self.exit_manager.add_position(signal, entry_price)
                            
                            if added:
                                self.positions_tracked += 1
                                logger.info(f"💼 {signal.symbol}: Añadido al seguimiento de posiciones")
                            else:
                                logger.warning(f"⚠️ {signal.symbol}: No se pudo añadir al seguimiento")
                        elif not self.exit_manager:
                            logger.debug("📊 Exit Manager no disponible")
                        else:
                            logger.warning(f"⚠️ {signal.symbol}: Sin plan de posición - No se puede seguir")
                    else:
                        logger.error(f"❌ Error enviando: {signal.symbol}")
                    
                    # Delay entre envíos
                    time.sleep(1)
                except Exception as e:
                    logger.error(f"❌ Error procesando {signal.symbol}: {e}")
        except Exception as e:
            logger.error(f"❌ Error procesando señales: {e}")
    
    def process_exit_signals(self, exit_signals: List[ExitSignal]) -> None:
        """🚪 NUEVA FUNCIÓN: Procesar señales de exit"""
        try:
            if not exit_signals:
                return
            
            logger.info(f"🚪 Procesando {len(exit_signals)} alertas de exit...")
            
            # Filtrar solo alertas que requieren notificación
            alertas_a_enviar = [
                signal for signal in exit_signals 
                if signal.urgency in [ExitUrgency.EXIT_RECOMMENDED, ExitUrgency.EXIT_URGENT]
            ]
            
            if not alertas_a_enviar:
                logger.info("👀 Solo alertas de vigilancia - No enviando notificaciones")
                return
            
            logger.info(f"📱 Enviando {len(alertas_a_enviar)} alertas críticas...")
            
            # Enviar alertas una por una
            sent = 0
            for exit_signal in alertas_a_enviar:
                success = self.send_exit_alert(exit_signal)
                if success:
                    sent += 1
                
                # Delay entre alertas para evitar spam
                time.sleep(2)
            
            if sent > 0:
                logger.info(f"✅ {sent} alertas de exit enviadas exitosamente")
            
            # Guardar posiciones actualizadas
            if self.exit_manager:
                self.exit_manager.save_positions()
            
        except Exception as e:
            logger.error(f"❌ Error procesando exit signals: {e}")
    
    def calculate_next_scan_time(self) -> datetime:
        """Calcular próximo escaneo dentro de sesión"""
        try:
            now = datetime.now(self.market_tz)
            next_scan = now + timedelta(minutes=self.scan_interval_minutes)
            next_time = next_scan.time()
            
            # ¿Está dentro de alguna sesión?
            for session in self.market_sessions:
                if session['start'] <= next_time <= session['end']:
                    self.next_scan_time = next_scan
                    return next_scan
            
            # Fuera de sesión → próxima sesión
            next_session = self.get_next_market_session()
            if next_session:
                self.next_scan_time = next_session
                return next_session
            
            # Fallback
            self.next_scan_time = next_scan
            return next_scan
        except Exception as e:
            logger.error(f"❌ Error calculando próximo escaneo: {e}")
            fallback = datetime.now(self.market_tz) + timedelta(minutes=15)
            self.next_scan_time = fallback
            return fallback
    
    def run_smart_scanning_loop_with_exits(self) -> None:
        """🚪 Loop principal MEJORADO con exit management"""
        try:
            logger.info("🎯 Iniciando Smart Scanning Loop v2.2 con Exit Management")
            
            while self.running and not self.shutdown_event.is_set():
                
                # 1. ¿Mercado abierto?
                if not self.is_market_open_now():
                    if not config.DEVELOPMENT_MODE:
                        logger.info("🏛️ Mercado cerrado - Esperando...")
                        if not self.smart_sleep_until_market():
                            break
                        continue
                    else:
                        logger.info("💻 Modo desarrollo - Escaneando fuera de horario")
                
                # 2. Escanear nuevas señales
                signals = self.perform_scan()
                
                if not self.running:
                    break
                
                # 3. Procesar señales (incluye añadir al exit manager)
                if signals:
                    self.process_signals(signals)
                
                # 4. 🚪 NUEVO: Evaluar exits de posiciones existentes
                if self.exit_manager:
                    exit_signals = self.perform_exit_evaluation()
                    
                    if not self.running:
                        break
                    
                    # 5. 🚪 NUEVO: Procesar alertas de exit
                    if exit_signals:
                        self.process_exit_signals(exit_signals)
                
                # 6. Próximo escaneo
                next_scan = self.calculate_next_scan_time()
                now = datetime.now(self.market_tz)
                
                if next_scan <= now:
                    logger.info("⚡ Próximo escaneo inmediato")
                    continue
                
                # 7. Sleep hasta próximo escaneo
                sleep_seconds = (next_scan - now).total_seconds()
                
                if sleep_seconds > 300:  # > 5 min
                    hours = int(sleep_seconds // 3600)
                    minutes = int((sleep_seconds % 3600) // 60)
                    logger.info(f"⏳ Próximo escaneo: {next_scan.strftime('%H:%M')} ({hours}h {minutes}m)")
                    if not self.smart_sleep_until_market():
                        break
                else:
                    logger.info(f"⏳ Próximo escaneo en {sleep_seconds/60:.1f} min")
                    if self.shutdown_event.wait(sleep_seconds):
                        break
            
            logger.info("🏁 Smart Scanning Loop v2.2 terminado")
        except Exception as e:
            logger.error(f"❌ Error crítico en loop: {e}")
            self.telegram.send_system_alert("ERROR", f"Error crítico: {str(e)}")
    
    def start_automatic_mode(self) -> None:
        """Iniciar modo automático completo con exit management"""
        try:
            logger.info("🤖 Iniciando modo automático SMART v2.2 con Exit Management")
            
            # Mostrar info del sistema
            self._show_system_info()
            
            # Mensaje de inicio mejorado
            self._send_startup_message()
            
            # Configurar señales
            signal.signal(signal.SIGINT, self._signal_handler)
            signal.signal(signal.SIGTERM, self._signal_handler)
            
            self.running = True
            
            # Thread principal CON EXIT MANAGEMENT
            self.scan_thread = threading.Thread(
                target=self.run_smart_scanning_loop_with_exits,
                name="SmartScanningLoopWithExits",
                daemon=False
            )
            self.scan_thread.start()
            
            logger.info("✅ Sistema v2.2 iniciado - Presiona Ctrl+C para detener")
            
            # Esperar
            try:
                self.scan_thread.join()
            except KeyboardInterrupt:
                self._graceful_shutdown()
        except Exception as e:
            logger.error(f"❌ Error en modo automático: {e}")
            self.telegram.send_system_alert("ERROR", f"Error: {str(e)}")
    
    def _show_system_info(self):
        """Mostrar información detallada v2.2"""
        logger.info("=" * 60)
        logger.info("🚀 SMART TRADING SYSTEM V2.2 CON EXIT MANAGEMENT")
        logger.info("=" * 60)
        
        # Horarios
        logger.info("📅 HORARIOS EXPANDIDOS:")
        for session in self.market_sessions:
            start_dt = datetime.combine(datetime.today(), session['start'])
            end_dt = datetime.combine(datetime.today(), session['end'])
            duration = end_dt - start_dt
            logger.info(f"   {session['name']}: {session['start']}-{session['end']} ({duration})")
        
        # Símbolos
        logger.info(f"📊 SÍMBOLOS: {len(config.SYMBOLS)}")
        logger.info(f"   {', '.join(config.SYMBOLS)}")
        
        # Posiciones activas
        if self.exit_manager:
            positions_summary = self.exit_manager.get_positions_summary()
            total_positions = positions_summary.get('total_positions', 0)
            logger.info(f"💼 POSICIONES ACTIVAS: {total_positions}")
            
            if total_positions > 0:
                long_pos = positions_summary.get('long_positions', 0)
                short_pos = positions_summary.get('short_positions', 0)
                total_pnl = positions_summary.get('total_unrealized_pnl', 0)
                
                logger.info(f"   🟢 LONG: {long_pos} | 🔴 SHORT: {short_pos}")
                logger.info(f"   📈 PnL total: {total_pnl:+.1f}%")
        
        logger.info("🚪 EXIT MANAGEMENT: ACTIVO" if self.exit_manager else "🚪 EXIT MANAGEMENT: NO DISPONIBLE")
        logger.info("=" * 60)
    
    def _send_startup_message(self):
        """Enviar mensaje de inicio mejorado v2.2"""
        try:
            market_status = "🟢 ABIERTO" if self.is_market_open_now() else "🔴 CERRADO"
            next_session = self.get_next_market_session()
            
            message_parts = [
                "🚀 <b>Smart Trading System v2.2</b>",
                "🚪 <b>CON EXIT MANAGEMENT</b>",
                "",
                f"🏛️ <b>Mercado:</b> {market_status}",
                f"📊 <b>Símbolos:</b> {len(config.SYMBOLS)}",
                f"⏰ <b>Intervalo:</b> {config.SCAN_INTERVAL} min"
            ]
            
            # Información de posiciones
            if self.exit_manager:
                positions_summary = self.exit_manager.get_positions_summary()
                total_positions = positions_summary.get('total_positions', 0)
                message_parts.append(f"💼 <b>Posiciones activas:</b> {total_positions}")
                
                if total_positions > 0:
                    long_pos = positions_summary.get('long_positions', 0)
                    short_pos = positions_summary.get('short_positions', 0)
                    total_pnl = positions_summary.get('total_unrealized_pnl', 0)
                    pnl_emoji = "🟢" if total_pnl >= 0 else "🔴"
                    
                    message_parts.extend([
                        f"• 🟢 LONG: {long_pos} | 🔴 SHORT: {short_pos}",
                        f"• {pnl_emoji} PnL total: {total_pnl:+.1f}%"
                    ])
            
            message_parts.extend([
                "",
                "📅 <b>Horarios expandidos:</b>"
            ])
            
            for session in self.market_sessions:
                start_dt = datetime.combine(datetime.today(), session['start'])
                end_dt = datetime.combine(datetime.today(), session['end'])
                duration = end_dt - start_dt
                message_parts.append(f"• {session['name']}: {session['start']}-{session['end']} ({duration})")
            
            if next_session and not self.is_market_open_now():
                message_parts.append("")
                message_parts.append(f"🕒 <b>Próxima sesión:</b> {next_session.strftime('%H:%M del %d/%m')}")
            
            if self.smart_components:
                message_parts.extend([
                    "",
                    "🔥 <b>Smart Features:</b>",
                    "• 🛡️ Rate Limiting",
                    "• 💾 Data Caching", 
                    "• 🔄 Error Recovery",
                    "• 📈 Performance Monitor"
                ])
            
            if self.exit_manager:
                message_parts.extend([
                    "",
                    "🚪 <b>Exit Management:</b>",
                    "• 🔍 Reevaluación automática",
                    "• 📱 Alertas de deterioro",
                    "• 🎯 Salidas inteligentes"
                ])
            
            message = "\n".join(message_parts)
            self.telegram.send_system_alert("START", message)
        except Exception as e:
            logger.error(f"❌ Error mensaje inicio: {e}")
            self.telegram.send_startup_message()  # Fallback
    
    def _signal_handler(self, signum, frame):
        """Handler señales del sistema"""
        logger.info(f"📢 Señal {signum} - Shutdown...")
        self._graceful_shutdown()
    
    def _graceful_shutdown(self):
        """Shutdown gradual con estadísticas v2.2"""
        logger.info("🛑 Iniciando graceful shutdown...")
        
        self.running = False
        self.shutdown_event.set()
        
        # Esperar thread
        if self.scan_thread and self.scan_thread.is_alive():
            logger.info("⏳ Esperando thread...")
            self.scan_thread.join(timeout=10)
        
        # Guardar posiciones antes de cerrar
        try:
            if self.exit_manager:
                self.exit_manager.save_positions()
                logger.info("💾 Posiciones guardadas")
        except Exception as e:
            logger.error(f"❌ Error guardando posiciones: {e}")
        
        # Stats finales v2.2
        stats_parts = [
            "📊 <b>Estadísticas Finales v2.2:</b>",
            f"• Escaneos: {self.total_scans}",
            f"• Señales enviadas: {self.signals_sent}",
            f"• Alertas EXIT: {self.exit_alerts_sent}",
            f"• Posiciones trackeadas: {self.positions_tracked}",
            f"• Errores consecutivos: {self.consecutive_errors}"
        ]
        
        if self.exit_manager:
            positions_summary = self.exit_manager.get_positions_summary()
            total_positions = positions_summary.get('total_positions', 0)
            stats_parts.append(f"• Posiciones activas: {total_positions}")
            
            if total_positions > 0:
                total_pnl = positions_summary.get('total_unrealized_pnl', 0)
                pnl_emoji = "🟢" if total_pnl >= 0 else "🔴"
                stats_parts.append(f"• {pnl_emoji} PnL total: {total_pnl:+.1f}%")
        
        stats_message = "\n".join(stats_parts)
        
        self.telegram.send_system_alert("INFO", f"Sistema v2.2 detenido.\n\n{stats_message}")
        logger.info("✅ Shutdown v2.2 completado")
    
    def get_system_status(self) -> Dict:
        """Estado completo del sistema v2.2"""
        base_status = {
            'version': '2.2',
            'running': self.running,
            'market_open': self.is_market_open_now(),
            'total_scans': self.total_scans,
            'signals_sent': self.signals_sent,
            'exit_alerts_sent': self.exit_alerts_sent,
            'positions_tracked': self.positions_tracked,
            'consecutive_errors': self.consecutive_errors,
            'smart_features': self.smart_components is not None,
            'exit_management': self.exit_manager is not None,
            'last_scan': self.last_scan_time.isoformat() if self.last_scan_time else None,
            'next_scan': self.next_scan_time.isoformat() if self.next_scan_time else None
        }
        
        next_session = self.get_next_market_session()
        if next_session:
            base_status['next_market_session'] = next_session.isoformat()
        
        # Stats de posiciones
        if self.exit_manager:
            try:
                positions_summary = self.exit_manager.get_positions_summary()
                base_status['positions'] = positions_summary
            except Exception as e:
                base_status['positions_error'] = str(e)
        
        # Smart stats
        if self.smart_components:
            try:
                base_status['smart_stats'] = self.smart_components['get_stats']()
            except Exception as e:
                base_status['smart_stats_error'] = str(e)
        
        return base_status


# =============================================================================
# 🎯 MODOS DE OPERACIÓN V2.2
# =============================================================================

def mode_interactive_v2():
    """Modo interactivo completo v2.2 con exit management"""
    system = SmartTradingSystemWithExitManagement()
    
    while True:
        try:
            print("\n🚀 SMART TRADING SYSTEM V2.2 CON EXIT MANAGEMENT")
            print("=" * 60)
            print("1. 🔍 Escaneo único")
            print("2. 🤖 Modo automático")
            print("3. 📊 Estado del sistema")
            print("4. 🚪 Gestión de posiciones")  # NUEVO
            print("5. 🧪 Tests")
            print("6. ⚙️ Configuración")
            print("7. 🏛️ Estado mercado")
            print("8. 📈 Smart Features stats")
            print("9. 🚪 Exit Management demo")  # NUEVO
            print("10. ❌ Salir")
            print()
            
            choice = input("Opción (1-10): ").strip()
            
            if choice == "1":
                logger.info("🔍 Escaneo único...")
                signals = system.perform_scan()
                
                if signals:
                    print(f"\n✅ {len(signals)} señales:")
                    for i, signal in enumerate(signals, 1):
                        print(f"{i}. {signal.symbol} - {signal.signal_type} ({signal.signal_strength} pts)")
                        print(f"   Precio: ${signal.current_price:.2f}")
                        if signal.position_plan:
                            print(f"   R:R: 1:{signal.position_plan.max_risk_reward:.1f}")
                    
                    send = input("\n📱 ¿Enviar por Telegram y añadir a seguimiento? (y/n): ").lower()
                    if send == 'y':
                        system.process_signals(signals)
                else:
                    print("📊 Sin señales detectadas")
            
            elif choice == "2":
                print("🤖 Iniciando automático v2.2...")
                system.start_automatic_mode()
                break
            
            elif choice == "3":
                status = system.get_system_status()
                print("\n📊 ESTADO DEL SISTEMA V2.2:")
                print("=" * 50)
                print(f"Version: {status.get('version', 'N/A')}")
                print(f"Running: {'✅' if status['running'] else '❌'}")
                print(f"Market Open: {'✅' if status['market_open'] else '❌'}")
                print(f"Smart Features: {'✅' if status['smart_features'] else '❌'}")
                print(f"Exit Management: {'✅' if status['exit_management'] else '❌'}")
                print(f"Scans: {status['total_scans']}")
                print(f"Signals: {status['signals_sent']}")
                print(f"Exit Alerts: {status['exit_alerts_sent']}")
                print(f"Positions Tracked: {status['positions_tracked']}")
                print(f"Errors: {status['consecutive_errors']}")
            
            elif choice == "4":  # NUEVO - Gestión de posiciones
                if not system.exit_manager:
                    print("❌ Exit Manager no disponible")
                    continue
                
                print("\n💼 GESTIÓN DE POSICIONES:")
                print("=" * 50)
                
                positions_summary = system.exit_manager.get_positions_summary()
                total_positions = positions_summary.get('total_positions', 0)
                
                if total_positions == 0:
                    print("📊 No hay posiciones activas")
                else:
                    print(f"📈 Total posiciones: {total_positions}")
                    print(f"🟢 LONG: {positions_summary.get('long_positions', 0)}")
                    print(f"🔴 SHORT: {positions_summary.get('short_positions', 0)}")
                    print(f"⚠️ Con deterioro: {positions_summary.get('positions_with_deterioration', 0)}")
                    print(f"📊 PnL total: {positions_summary.get('total_unrealized_pnl', 0):+.1f}%")
                    print(f"⏰ Días promedio: {positions_summary.get('avg_days_held', 0):.1f}")
                    print("")
                    
                    # Evaluar exits
                    evaluar = input("🚪 ¿Evaluar exits ahora? (y/n): ").lower()
                    if evaluar == 'y':
                        print("🔍 Evaluando exits...")
                        exit_signals = system.perform_exit_evaluation()
                        
                        if exit_signals:
                            print(f"\n🚨 {len(exit_signals)} alertas generadas:")
                            for signal in exit_signals:
                                print(f"• {signal.symbol}: {signal.urgency.value} ({signal.exit_score} pts)")
                                print(f"  Recomendación: Salir {signal.exit_percentage}%")
                        else:
                            print("✅ No hay alertas de exit necesarias")
            
            elif choice == "5":
                print("🧪 Ejecutando tests v2.2...")
                
                # Test Telegram
                print("📱 Test Telegram...")
                system.telegram.send_test_message()
                
                # Test Exit Manager
                if system.exit_manager:
                    print("🚪 Test Exit Manager...")
                    try:
                        exit_signals = system.exit_manager.evaluate_all_positions()
                        print(f"✅ Exit Manager: {len(exit_signals)} evaluaciones realizadas")
                    except Exception as e:
                        print(f"❌ Error Exit Manager: {e}")
                else:
                    print("❌ Exit Manager no disponible")
                
                print("✅ Tests completados")
            
            elif choice == "6":
                print("\n⚙️ CONFIGURACIÓN V2.2:")
                print("=" * 50)
                print(f"Símbolos: {len(config.SYMBOLS)}")
                print(f"Exit Management: {'✅ ACTIVO' if system.exit_manager else '❌ NO DISPONIBLE'}")
                if system.exit_manager:
                    print(f"  Umbrales deterioro: {system.exit_manager.deterioration_thresholds}")
            
            elif choice == "7":
                market_open = system.is_market_open_now()
                print(f"\n🏛️ ESTADO MERCADO:")
                print(f"Abierto: {'✅ SÍ' if market_open else '❌ NO'}")
            
            elif choice == "8":
                if system.smart_components:
                    try:
                        stats = system.smart_components['get_stats']()
                        print("\n📈 SMART FEATURES STATS:")
                        print("✅ Smart Features funcionando")
                    except Exception as e:
                        print(f"❌ Error obteniendo stats: {e}")
                else:
                    print("⚠️ Smart Features no disponibles")
            
            elif choice == "9":  # NUEVO - Exit Management demo
                if system.exit_manager:
                    print("🚪 EXIT MANAGEMENT DEMO...")
                    try:
                        from exit_manager import test_exit_manager
                        test_exit_manager()
                    except Exception as e:
                        print(f"❌ Error en demo: {e}")
                else:
                    print("❌ Exit Manager no disponible")
            
            elif choice == "10":
                print("👋 ¡Hasta luego!")
                break
            
            else:
                print("❌ Opción no válida")
        
        except KeyboardInterrupt:
            print("\n👋 Saliendo...")
            break
        except Exception as e:
            logger.error(f"❌ Error en modo interactivo: {e}")

def main():
    """Función principal v2.2 con exit management"""
    try:
        # Validar configuración
        config_errors = config.validate_config()
        if config_errors:
            logger.error("❌ ERRORES DE CONFIGURACIÓN:")
            for error in config_errors:
                logger.error(f"  {error}")
            return 1
        
        # Info componentes
        if SMART_FEATURES_AVAILABLE:
            logger.info("🔥 Smart Features disponibles")
        else:
            logger.info("📊 Smart Features no disponibles")
        
        if EXIT_MANAGER_AVAILABLE:
            logger.info("🚪 Exit Management System disponible")
        else:
            logger.info("⚠️ Exit Management System no disponible")
        
        # Determinar modo
        if len(sys.argv) > 1:
            mode = sys.argv[1].lower()
            
            if mode == "auto":
                logger.info("🤖 Modo automático v2.2")
                system = SmartTradingSystemWithExitManagement()
                system.start_automatic_mode()
            
            elif mode == "scan":
                logger.info("🔍 Modo escaneo único")
                system = SmartTradingSystemWithExitManagement()
                signals = system.perform_scan()
                
                if signals:
                    print("\n✅ SEÑALES DETECTADAS:")
                    print("=" * 40)
                    for signal in signals:
                        print(f"{signal.symbol} - {signal.signal_type}")
                        print(f"  Fuerza: {signal.signal_strength}/100")
                        print(f"  Precio: ${signal.current_price:.2f}")
                        print(f"  Confianza: {signal.confidence_level}")
                        print()
                else:
                    print("📊 No se detectaron señales válidas")
            
            elif mode == "exits":  # NUEVO modo
                logger.info("🚪 Modo evaluación de exits")
                system = SmartTradingSystemWithExitManagement()
                
                if not system.exit_manager:
                    print("❌ Exit Manager no disponible")
                    return 1
                
                exit_signals = system.perform_exit_evaluation()
                
                if exit_signals:
                    print("\n🚨 ALERTAS DE EXIT DETECTADAS:")
                    print("=" * 50)
                    for signal in exit_signals:
                        print(f"{signal.symbol} - {signal.urgency.value}")
                        print(f"  Score deterioro: {signal.exit_score}/100")
                        print(f"  PnL actual: {signal.position.unrealized_pnl_pct:+.1f}%")
                        print(f"  Recomendación: Salir {signal.exit_percentage}%")
                        print()
                else:
                    print("✅ No hay alertas de exit necesarias")
            
            elif mode == "test":
                logger.info("🧪 Modo testing completo v2.2")
                system = SmartTradingSystemWithExitManagement()
                
                print("🧪 EJECUTANDO TESTS COMPLETOS V2.2")
                print("=" * 60)
                
                # Test 1: Telegram
                print("1. 📱 Test Telegram...")
                try:
                    success = system.telegram.send_test_message()
                    print(f"   Resultado: {'✅ OK' if success else '❌ FALLO'}")
                except Exception as e:
                    print(f"   ❌ Error: {e}")
                
                # Test 2: Exit Manager (NUEVO)
                print("2. 🚪 Test Exit Manager...")
                if system.exit_manager:
                    try:
                        positions_summary = system.exit_manager.get_positions_summary()
                        print(f"   ✅ Exit Manager funcionando")
                        print(f"   Posiciones activas: {positions_summary.get('total_positions', 0)}")
                    except Exception as e:
                        print(f"   ❌ Error: {e}")
                else:
                    print("   ❌ Exit Manager no disponible")
                
                print("✅ Todos los tests v2.2 completados")
            
            else:
                print(f"❌ Modo '{mode}' no reconocido")
                print("Modos disponibles: auto, scan, exits, test")
                return 1
        else:
            # Sin argumentos = modo interactivo v2.2
            mode_interactive_v2()
        
        return 0
        
    except Exception as e:
        logger.error(f"💥 Error crítico: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())