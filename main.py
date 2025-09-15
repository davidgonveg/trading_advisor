#!/usr/bin/env python3
"""
🎯 MAIN.PY V2.3 - INTEGRACIÓN CON DYNAMIC MONITOR
==============================================================

NUEVAS CARACTERÍSTICAS V2.3 - MONITOREO DINÁMICO:
1. 🎯 Frecuencias variables según proximidad a objetivos
2. ⚡ Monitoreo intensivo de posiciones activas
3. 🛡️ Rate limiting inteligente para no exceder APIs
4. 📊 Priorización automática según volatilidad

FLUJO COMPLETO V2.3:
- Detecta señales (como antes)
- Añade automáticamente al monitoreo dinámico
- Ajusta frecuencia según proximidad a entradas/exits
- Reevalúa posiciones con frecuencia inteligente
- Gestiona salidas y alertas optimizadas
"""

import logging
import signal
import sys
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, List
import pytz
import threading

# Importar módulos del sistema
import config
from scanner import SignalScanner, TradingSignal
from telegram_bot import TelegramBot

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

# Importar EXIT MANAGEMENT SYSTEM
try:
    from exit_manager import ExitManager, ExitSignal, ExitUrgency, ActivePosition
    EXIT_MANAGER_AVAILABLE = True
except ImportError:
    EXIT_MANAGER_AVAILABLE = False
    
V3_SYSTEM_AVAILABLE = False

try:
    import config
    if getattr(config, 'USE_ADAPTIVE_TARGETS', False):
        import adaptive_targets
        import position_calculator
        V3_SYSTEM_AVAILABLE = True
        logger.info("✅ Sistema de targets adaptativos V3.0 disponible")
    else:
        logger.info("📊 Sistema V3.0 desactivado en config - usando V2.0")
except ImportError as e:
    logger.warning(f"⚠️ Sistema V3.0 no disponible: {e}")
    logger.info("📊 Usando sistema clásico V2.0")

# Importar DYNAMIC MONITOR (NUEVO)
try:
    from dynamic_monitor import DynamicMonitor, MonitorPriority
    DYNAMIC_MONITOR_AVAILABLE = True
    print("🎯 Dynamic Monitor detectado y cargado")
except ImportError:
    DYNAMIC_MONITOR_AVAILABLE = False
    print("⚠️ dynamic_monitor.py no encontrado - ejecutando sin monitoreo dinámico")

# Importar smart enhancements
try:
    from smart_enhancements import integrate_smart_features
    SMART_FEATURES_AVAILABLE = True
except ImportError:
    SMART_FEATURES_AVAILABLE = False


class SmartTradingSystemV23WithDynamicMonitoring:
    """
    Sistema de trading v2.3 con monitoreo dinámico integrado
    """
    
    def __init__(self):
        """Inicializar sistema completo v2.3 con monitoreo dinámico"""
        logger.info("🚀 Inicializando Smart Trading System v2.3 con Dynamic Monitoring")
        
        # Componentes principales
        self.scanner = SignalScanner()
        self.telegram = TelegramBot()
        
        # Exit Manager
        if EXIT_MANAGER_AVAILABLE:
            self.exit_manager = ExitManager()
            logger.info("✅ Exit Manager activado")
        else:
            self.exit_manager = None
            logger.warning("⚠️ Exit Manager no disponible")
        
        # 🎯 NUEVO: Dynamic Monitor
        if DYNAMIC_MONITOR_AVAILABLE:
            self.dynamic_monitor = DynamicMonitor()
            logger.info("✅ Dynamic Monitor activado")
        else:
            self.dynamic_monitor = None
            logger.warning("⚠️ Dynamic Monitor no disponible")
        
        self.running = False
        
        # Configuración de timezone
        self.market_tz = pytz.timezone(config.MARKET_TIMEZONE)
        
        # Estado del sistema
        self.total_scans = 0
        self.signals_sent = 0
        self.exit_alerts_sent = 0
        self.positions_tracked = 0
        self.dynamic_updates = 0  # NUEVO contador
        self.consecutive_errors = 0
        self.max_consecutive_errors = 5
        self.last_scan_time = None
        
        # Threading para control
        self.scan_thread = None
        self.shutdown_event = threading.Event()
        
        # Smart features
        self.smart_components = None
        if SMART_FEATURES_AVAILABLE:
            try:
                self.smart_components = integrate_smart_features()
                self._setup_enhanced_data_fetch()
                logger.info("✅ Smart enhancements activados")
            except Exception as e:
                logger.warning(f"⚠️ Error cargando smart enhancements: {e}")
        
        logger.info("✅ Smart Trading System v2.3 inicializado correctamente")
    
    def _setup_enhanced_data_fetch(self):
        """Reemplazar get_market_data con versión mejorada en TODOS los componentes"""
        try:
            if self.smart_components and 'enhanced_data_fetch' in self.smart_components:
                enhanced_fetch = self.smart_components['enhanced_data_fetch']
                
                # Reemplazar en scanner
                self.scanner.indicators.get_market_data = enhanced_fetch
                
                # Reemplazar en exit manager si está disponible
                if self.exit_manager:
                    self.exit_manager.indicators.get_market_data = enhanced_fetch
                
                # 🎯 NUEVO: Reemplazar en dynamic monitor
                if self.dynamic_monitor:
                    self.dynamic_monitor.indicators.get_market_data = enhanced_fetch
                
                logger.info("🔧 Enhanced data fetch configurado en todos los componentes")
        except Exception as e:
            logger.error(f"❌ Error configurando enhanced fetch: {e}")
    
    def is_market_open_now(self) -> bool:
        """Verificar si mercado está abierto AHORA"""
        return self.scanner.is_market_open()
    
    def perform_scan_with_dynamic_integration(self) -> List[TradingSignal]:
        """🎯 NUEVO: Escaneo integrado con dynamic monitor y V3.0"""
        try:
            # 🆕 V3.0: Loggear si se están usando targets adaptativos
            if V3_SYSTEM_AVAILABLE:
                logger.info("🎯 Escaneo con targets adaptativos V3.0 activado")
            else:
                logger.info("📊 Escaneo con sistema clásico V2.0")
            
            logger.info(f"🔍 Iniciando escaneo #{self.total_scans + 1} con integración dinámica")
            
            # 1. Realizar escaneo normal
            signals = self.scanner.scan_multiple_symbols(config.SYMBOLS)
            
            # Actualizar contadores
            self.total_scans += 1
            self.last_scan_time = datetime.now(self.market_tz)
            
            # 2. 🎯 NUEVO: Integrar con dynamic monitor
            if self.dynamic_monitor and signals:
                logger.info(f"🎯 Integrando {len(signals)} señales con Dynamic Monitor...")
                
                for signal in signals:
                    try:
                        # Añadir señal al monitoreo dinámico
                        success = self.dynamic_monitor.add_monitor_target(
                            symbol=signal.symbol,
                            signal=signal,
                            reason=f"Nueva señal {signal.signal_type} {'V3.0' if V3_SYSTEM_AVAILABLE else 'V2.0'}"
                        )
                        
                        if success:
                            version_info = " (V3.0)" if V3_SYSTEM_AVAILABLE else " (V2.0)"
                            logger.info(f"📊 {signal.symbol}: Añadido a monitoreo dinámico{version_info}")
                        else:
                            logger.warning(f"⚠️ {signal.symbol}: No se pudo añadir a monitoreo dinámico")
                    
                    except Exception as e:
                        logger.error(f"❌ Error integrando {signal.symbol} con dynamic monitor: {e}")
            
            # 3. Sincronizar con exit manager si está disponible
            if self.dynamic_monitor and self.exit_manager:
                try:
                    self.dynamic_monitor.sync_with_exit_manager()
                except Exception as e:
                    logger.error(f"❌ Error sincronizando con exit manager: {e}")
            
            # Log resultado
            if signals:
                version_msg = "con targets adaptativos V3.0" if V3_SYSTEM_AVAILABLE else "con sistema clásico V2.0"
                logger.info(f"✅ Escaneo completado: {len(signals)} señales detectadas e integradas {version_msg}")
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
    
    def perform_exit_evaluation_enhanced(self) -> List[ExitSignal]:
        """🎯 NUEVO: Evaluación de exits mejorada con dynamic monitor"""
        try:
            if not self.exit_manager:
                return []
            
            logger.info("🚪 Evaluando posiciones activas con integración dinámica...")
            
            # Verificar si hay posiciones
            positions_summary = self.exit_manager.get_positions_summary()
            total_positions = positions_summary.get('total_positions', 0)
            
            if total_positions == 0:
                logger.debug("📊 No hay posiciones activas para evaluar")
                return []
            
            # 1. Evaluar exits normalmente
            exit_signals = self.exit_manager.evaluate_all_positions()
            
            # 2. 🎯 NUEVO: Actualizar prioridades en dynamic monitor
            if self.dynamic_monitor and exit_signals:
                logger.info(f"🎯 Actualizando prioridades en Dynamic Monitor...")
                
                for exit_signal in exit_signals:
                    symbol = exit_signal.symbol
                    
                    # Verificar si está en monitoreo dinámico
                    if symbol in self.dynamic_monitor.monitor_targets:
                        target = self.dynamic_monitor.monitor_targets[symbol]
                        
                        # Forzar alta prioridad si exit es urgente
                        if exit_signal.urgency in [ExitUrgency.EXIT_URGENT, ExitUrgency.EXIT_RECOMMENDED]:
                            target.priority = MonitorPriority.CRITICAL
                            target.reason = f"Exit {exit_signal.urgency.value} ({exit_signal.exit_score} pts)"
                            
                            logger.info(f"📊 {symbol}: Prioridad elevada a CRITICAL por exit {exit_signal.urgency.value}")
                        
                        elif exit_signal.urgency == ExitUrgency.EXIT_WATCH:
                            target.priority = MonitorPriority.HIGH
                            target.reason = f"Exit WATCH ({exit_signal.exit_score} pts)"
            
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
            logger.error(f"❌ Error en evaluación de exits mejorada: {e}")
            return []
    
    def process_signals_with_dynamic_integration(self, signals: List[TradingSignal]) -> None:
        """🎯 NUEVO: Procesar señales con integración dinámica completa"""
        try:
            if not signals:
                return
            
            logger.info(f"📱 Procesando {len(signals)} señales con integración dinámica...")
            
            for signal in signals:
                try:
                    # 1. Enviar alerta de señal (como antes)
                    success = self.telegram.send_signal_alert(signal)
                    
                    if success:
                        self.signals_sent += 1
                        logger.info(f"✅ Alerta enviada: {signal.symbol} {signal.signal_type}")
                        
                        # 2. Añadir al exit manager (como antes)
                        if self.exit_manager and signal.position_plan:
                            entry_price = signal.current_price
                            added = self.exit_manager.add_position(signal, entry_price)
                            
                            if added:
                                self.positions_tracked += 1
                                logger.info(f"💼 {signal.symbol}: Añadido al seguimiento de posiciones")
                        
                        # 3. 🎯 NUEVO: Verificar que está en dynamic monitor
                        if self.dynamic_monitor:
                            if signal.symbol not in self.dynamic_monitor.monitor_targets:
                                # Añadir al monitoreo dinámico si no está
                                self.dynamic_monitor.add_monitor_target(
                                    symbol=signal.symbol,
                                    signal=signal,
                                    reason="Procesamiento de señal"
                                )
                                logger.info(f"🎯 {signal.symbol}: Añadido a Dynamic Monitor")
                            else:
                                # Actualizar datos si ya está
                                target = self.dynamic_monitor.monitor_targets[signal.symbol]
                                target.last_signal = signal
                                target.reason = f"Señal actualizada {signal.signal_type}"
                                logger.info(f"🎯 {signal.symbol}: Dynamic Monitor actualizado")
                    else:
                        logger.error(f"❌ Error enviando: {signal.symbol}")
                    
                    # Delay entre envíos
                    time.sleep(1)
                except Exception as e:
                    logger.error(f"❌ Error procesando {signal.symbol}: {e}")
        except Exception as e:
            logger.error(f"❌ Error procesando señales con integración dinámica: {e}")
    
    def run_integrated_loop_v23(self) -> None:
        """🎯 NUEVO: Loop principal v2.3 con monitoreo dinámico integrado"""
        try:
            logger.info("🚀 Iniciando Integrated Loop v2.3 con Dynamic Monitoring")
            
            # 1. 🎯 NUEVO: Iniciar dynamic monitor si está disponible
            if self.dynamic_monitor:
                success = self.dynamic_monitor.start_dynamic_monitoring()
                if success:
                    logger.info("✅ Dynamic Monitor iniciado en paralelo")
                else:
                    logger.error("❌ Error iniciando Dynamic Monitor")
            
            # 2. Loop principal (similar pero integrado)
            last_full_scan = datetime.now()
            scan_interval = timedelta(minutes=config.SCAN_INTERVAL)
            
            while self.running and not self.shutdown_event.is_set():
                
                # 3. ¿Mercado abierto?
                if not self.is_market_open_now():
                    if not config.DEVELOPMENT_MODE:
                        logger.info("🏛️ Mercado cerrado - Modo sleep")
                        if self.shutdown_event.wait(300):  # 5 min
                            break
                        continue
                    else:
                        logger.info("💻 Modo desarrollo - Continuando fuera de horario")
                
                # 4. ¿Toca escaneo completo?
                now = datetime.now()
                if now - last_full_scan >= scan_interval:
                    
                    # Escanear nuevas señales con integración dinámica
                    signals = self.perform_scan_with_dynamic_integration()
                    
                    if not self.running:
                        break
                    
                    # Procesar señales con integración
                    if signals:
                        self.process_signals_with_dynamic_integration(signals)
                    
                    # Evaluar exits con integración
                    if self.exit_manager:
                        exit_signals = self.perform_exit_evaluation_enhanced()
                        
                        if not self.running:
                            break
                        
                        # Procesar alertas de exit
                        if exit_signals:
                            self.process_exit_signals(exit_signals)
                    
                    last_full_scan = now
                
                # 5. 🎯 NUEVO: Obtener stats del dynamic monitor
                if self.dynamic_monitor:
                    try:
                        dynamic_stats = self.dynamic_monitor.get_monitoring_stats()
                        self.dynamic_updates = dynamic_stats.get('total_updates', 0)
                        
                        # Log stats cada 10 escaneos
                        if self.total_scans % 10 == 0 and self.total_scans > 0:
                            logger.info(f"📊 Dynamic Monitor Stats:")
                            logger.info(f"   Targets activos: {dynamic_stats['total_targets']}")
                            logger.info(f"   Updates dinámicos: {self.dynamic_updates}")
                            logger.info(f"   CRITICAL: {dynamic_stats['targets_by_priority'].get('CRITICAL', 0)}")
                            logger.info(f"   HIGH: {dynamic_stats['targets_by_priority'].get('HIGH', 0)}")
                    except Exception as e:
                        logger.error(f"❌ Error obteniendo stats dynamic monitor: {e}")
                
                # 6. Sleep hasta próximo ciclo (más corto que antes)
                # El dynamic monitor maneja las actualizaciones frecuentes
                sleep_seconds = min(60, scan_interval.total_seconds() / 4)  # 1/4 del intervalo
                
                if self.shutdown_event.wait(sleep_seconds):
                    break
            
            # 7. 🎯 NUEVO: Detener dynamic monitor
            if self.dynamic_monitor:
                logger.info("🛑 Deteniendo Dynamic Monitor...")
                self.dynamic_monitor.stop_dynamic_monitoring()
            
            logger.info("🏁 Integrated Loop v2.3 terminado")
            
        except Exception as e:
            logger.error(f"❌ Error crítico en integrated loop v2.3: {e}")
            self.telegram.send_system_alert("ERROR", f"Error crítico v2.3: {str(e)}")
    
    def process_exit_signals(self, exit_signals: List[ExitSignal]) -> None:
        """Procesar señales de exit (igual que antes)"""
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
            
            # Formatear mensaje (usar el método del exit_manager o crear uno aquí)
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
    
    def format_exit_alert(self, exit_signal: ExitSignal) -> str:
        """Formatear alerta de exit para Telegram (copiado del exit_manager)"""
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
            
            # 🎯 NUEVO: Añadir info de dynamic monitor
            if self.dynamic_monitor and position.symbol in self.dynamic_monitor.monitor_targets:
                target = self.dynamic_monitor.monitor_targets[position.symbol]
                message_lines.append(f"• <b>Monitor dinámico:</b> {target.priority.value} ({target.update_count} updates)")
            
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
            for reason in exit_signal.technical_reasons[:4]:  # Máximo 4 razones
                message_lines.append(f"• {reason}")
            message_lines.append("")
            
            # === FOOTER ===
            if exit_signal.urgency == ExitUrgency.EXIT_URGENT:
                footer_msg = "🚨 <i>Sistema v2.3 - Acción requerida</i>"
            elif exit_signal.urgency == ExitUrgency.EXIT_RECOMMENDED:
                footer_msg = "⚠️ <i>Sistema v2.3 - Salida recomendada</i>"
            else:
                footer_msg = "👀 <i>Sistema v2.3 - Vigilancia requerida</i>"
            
            message_lines.append(footer_msg)
            
            return "\n".join(message_lines)
            
        except Exception as e:
            logger.error(f"❌ Error formateando alerta exit v2.3: {e}")
            return f"❌ Error formateando alerta exit para {exit_signal.symbol}"
    
    def start_automatic_mode_v23(self) -> None:
        """🎯 NUEVO: Iniciar modo automático v2.3 con dynamic monitoring"""
        try:
            logger.info("🤖 Iniciando modo automático SMART v2.3 con Dynamic Monitoring")
            
            # Mostrar info del sistema v2.3
            self._show_system_info_v23()
            
            # Mensaje de inicio v2.3
            self._send_startup_message_v23()
            
            # Configurar señales
            signal.signal(signal.SIGINT, self._signal_handler)
            signal.signal(signal.SIGTERM, self._signal_handler)
            
            self.running = True
            
            # Thread principal v2.3 CON DYNAMIC MONITORING
            self.scan_thread = threading.Thread(
                target=self.run_integrated_loop_v23,
                name="IntegratedLoopV23",
                daemon=False
            )
            self.scan_thread.start()
            
            logger.info("✅ Sistema v2.3 iniciado - Presiona Ctrl+C para detener")
            
            # Esperar
            try:
                self.scan_thread.join()
            except KeyboardInterrupt:
                self._graceful_shutdown_v23()
        except Exception as e:
            logger.error(f"❌ Error en modo automático v2.3: {e}")
            self.telegram.send_system_alert("ERROR", f"Error v2.3: {str(e)}")
    
    def _show_system_info_v23(self):
        """Mostrar información detallada v2.3 con info V3.0"""
        logger.info("=" * 70)
        if V3_SYSTEM_AVAILABLE:
            logger.info("🚀 SMART TRADING SYSTEM V2.3 CON TARGETS ADAPTATIVOS V3.0")
        else:
            logger.info("🚀 SMART TRADING SYSTEM V2.3 CON DYNAMIC MONITORING")
        logger.info("=" * 70)
        
        # Componentes
        logger.info("🔧 COMPONENTES:")
        logger.info(f"   📊 Scanner: ✅")
        logger.info(f"   📱 Telegram: ✅")
        logger.info(f"   🚪 Exit Manager: {'✅' if self.exit_manager else '❌'}")
        logger.info(f"   🎯 Dynamic Monitor: {'✅' if self.dynamic_monitor else '❌'}")
        logger.info(f"   🔥 Smart Features: {'✅' if self.smart_components else '❌'}")
        logger.info(f"   🎯 Targets Adaptativos V3.0: {'✅' if V3_SYSTEM_AVAILABLE else '❌'}")
        
        # Símbolos y configuración
        logger.info(f"📊 SÍMBOLOS: {len(config.SYMBOLS)}")
        logger.info(f"   {', '.join(config.SYMBOLS)}")
        
        # Información V3.0
        if V3_SYSTEM_AVAILABLE:
            logger.info("🎯 CONFIGURACIÓN V3.0:")
            logger.info("   • Targets basados en análisis técnico real")
            logger.info("   • R:R máximo realista: 6.0 (no más 10R)")
            logger.info("   • Fibonacci, VWAP, Bollinger como targets")
            logger.info("   • Fallback automático a V2.0 si falla")
        
        # Posiciones activas (resto igual)
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
        
        # Dynamic Monitor info (resto igual)
        if self.dynamic_monitor:
            monitor_stats = self.dynamic_monitor.get_monitoring_stats()
            logger.info(f"🎯 DYNAMIC MONITOR:")
            logger.info(f"   Targets activos: {monitor_stats['total_targets']}")
            logger.info(f"   CRITICAL: {monitor_stats['targets_by_priority'].get('CRITICAL', 0)}")
            logger.info(f"   HIGH: {monitor_stats['targets_by_priority'].get('HIGH', 0)}")
            logger.info(f"   NORMAL: {monitor_stats['targets_by_priority'].get('NORMAL', 0)}")
        
        logger.info("=" * 70)
    
    def _send_startup_message_v23(self):
        """Enviar mensaje de inicio v2.3"""
        try:
            market_status = "🟢 ABIERTO" if self.is_market_open_now() else "🔴 CERRADO"
            
            message_parts = [
                "🚀 <b>Smart Trading System v2.3</b>",
                "🎯 <b>CON DYNAMIC MONITORING</b>",
                "",
                f"🏛️ <b>Mercado:</b> {market_status}",
                f"📊 <b>Símbolos:</b> {len(config.SYMBOLS)}",
                f"⏰ <b>Intervalo base:</b> {config.SCAN_INTERVAL} min"
            ]
            
            # Información de componentes
            message_parts.extend([
                "",
                "🔧 <b>Componentes activos:</b>",
                f"• 📊 Scanner: ✅",
                f"• 🚪 Exit Manager: {'✅' if self.exit_manager else '❌'}",
                f"• 🎯 Dynamic Monitor: {'✅' if self.dynamic_monitor else '❌'}",
                f"• 🔥 Smart Features: {'✅' if self.smart_components else '❌'}"
            ])
            
            # Información de posiciones
            if self.exit_manager:
                positions_summary = self.exit_manager.get_positions_summary()
                total_positions = positions_summary.get('total_positions', 0)
                message_parts.append(f"• 💼 Posiciones activas: {total_positions}")
                
                if total_positions > 0:
                    long_pos = positions_summary.get('long_positions', 0)
                    short_pos = positions_summary.get('short_positions', 0)
                    total_pnl = positions_summary.get('total_unrealized_pnl', 0)
                    pnl_emoji = "🟢" if total_pnl >= 0 else "🔴"
                    
                    message_parts.extend([
                        f"  🟢 LONG: {long_pos} | 🔴 SHORT: {short_pos}",
                        f"  {pnl_emoji} PnL total: {total_pnl:+.1f}%"
                    ])
            
            # 🎯 NUEVO: Dynamic Monitor info
            if self.dynamic_monitor:
                monitor_stats = self.dynamic_monitor.get_monitoring_stats()
                message_parts.extend([
                    "",
                    "🎯 <b>Dynamic Monitor:</b>",
                    "• ⚡ Frecuencias variables",
                    "• 🎯 Proximidad a objetivos",
                    "• 🛡️ Rate limiting inteligente",
                    f"• 📊 {monitor_stats['total_targets']} targets activos"
                ])
            
            message = "\n".join(message_parts)
            self.telegram.send_system_alert("START", message)
        except Exception as e:
            logger.error(f"❌ Error mensaje inicio v2.3: {e}")
            self.telegram.send_startup_message()  # Fallback
    
    def _signal_handler(self, signum, frame):
        """Handler señales del sistema"""
        logger.info(f"📢 Señal {signum} - Shutdown v2.3...")
        self._graceful_shutdown_v23()
    
    def _graceful_shutdown_v23(self):
        """🎯 NUEVO: Shutdown gradual v2.3 con dynamic monitor"""
        logger.info("🛑 Iniciando graceful shutdown v2.3...")
        
        self.running = False
        self.shutdown_event.set()
        
        # 1. Detener dynamic monitor primero
        if self.dynamic_monitor:
            logger.info("🎯 Deteniendo Dynamic Monitor...")
            self.dynamic_monitor.stop_dynamic_monitoring()
        
        # 2. Esperar thread principal
        if self.scan_thread and self.scan_thread.is_alive():
            logger.info("⏳ Esperando thread principal...")
            self.scan_thread.join(timeout=15)
            
            if self.scan_thread.is_alive():
                logger.warning("⚠️ Thread no terminó en tiempo esperado")
        
        # 3. Guardar posiciones antes de cerrar
        try:
            if self.exit_manager:
                self.exit_manager.save_positions()
                logger.info("💾 Posiciones guardadas")
        except Exception as e:
            logger.error(f"❌ Error guardando posiciones: {e}")
        
        # 4. Stats finales v2.3
        stats_parts = [
            "📊 <b>Estadísticas Finales v2.3:</b>",
            f"• Escaneos: {self.total_scans}",
            f"• Señales enviadas: {self.signals_sent}",
            f"• Alertas EXIT: {self.exit_alerts_sent}",
            f"• Posiciones trackeadas: {self.positions_tracked}",
            f"• Updates dinámicos: {self.dynamic_updates}",
            f"• Errores consecutivos: {self.consecutive_errors}"
        ]
        
        # Dynamic monitor stats
        if self.dynamic_monitor:
            try:
                final_dynamic_stats = self.dynamic_monitor.get_monitoring_stats()
                stats_parts.extend([
                    "",
                    "🎯 <b>Dynamic Monitor:</b>",
                    f"• Targets procesados: {final_dynamic_stats['total_targets']}",
                    f"• Updates críticos: {final_dynamic_stats['critical_updates']}",
                    f"• Updates altos: {final_dynamic_stats['high_updates']}",
                    f"• Updates normales: {final_dynamic_stats['normal_updates']}"
                ])
            except Exception as e:
                stats_parts.append(f"• Error stats dynamic: {str(e)[:50]}")
        
        # Exit manager stats
        if self.exit_manager:
            positions_summary = self.exit_manager.get_positions_summary()
            total_positions = positions_summary.get('total_positions', 0)
            stats_parts.append(f"• Posiciones finales: {total_positions}")
            
            if total_positions > 0:
                total_pnl = positions_summary.get('total_unrealized_pnl', 0)
                pnl_emoji = "🟢" if total_pnl >= 0 else "🔴"
                stats_parts.append(f"• {pnl_emoji} PnL final: {total_pnl:+.1f}%")
        
        stats_message = "\n".join(stats_parts)
        
        self.telegram.send_system_alert("INFO", f"Sistema v2.3 detenido.\n\n{stats_message}")
        logger.info("✅ Shutdown v2.3 completado")
    
    def get_system_status_v23(self) -> Dict:
        """🎯 NUEVO: Estado completo del sistema v2.3"""
        base_status = {
            'version': '2.3',
            'running': self.running,
            'market_open': self.is_market_open_now(),
            'total_scans': self.total_scans,
            'signals_sent': self.signals_sent,
            'exit_alerts_sent': self.exit_alerts_sent,
            'positions_tracked': self.positions_tracked,
            'dynamic_updates': self.dynamic_updates,
            'consecutive_errors': self.consecutive_errors,
            'components': {
                'scanner': True,
                'telegram': True,
                'exit_manager': self.exit_manager is not None,
                'dynamic_monitor': self.dynamic_monitor is not None,
                'smart_features': self.smart_components is not None
            },
            'last_scan': self.last_scan_time.isoformat() if self.last_scan_time else None
        }
        
        # Stats de posiciones
        if self.exit_manager:
            try:
                positions_summary = self.exit_manager.get_positions_summary()
                base_status['positions'] = positions_summary
            except Exception as e:
                base_status['positions_error'] = str(e)
        
        # 🎯 NUEVO: Stats de dynamic monitor
        if self.dynamic_monitor:
            try:
                base_status['dynamic_monitor_stats'] = self.dynamic_monitor.get_monitoring_stats()
            except Exception as e:
                base_status['dynamic_monitor_error'] = str(e)
        
        # Smart stats
        if self.smart_components:
            try:
                base_status['smart_stats'] = self.smart_components['get_stats']()
            except Exception as e:
                base_status['smart_stats_error'] = str(e)
        
        return base_status


# =============================================================================
# 🎯 MODOS DE OPERACIÓN V2.3
# =============================================================================

def mode_interactive_v23():
    """🎯 NUEVO: Modo interactivo v2.3 con dynamic monitoring"""
    system = SmartTradingSystemV23WithDynamicMonitoring()
    
    while True:
        try:
            print("\n🚀 SMART TRADING SYSTEM V2.3 CON DYNAMIC MONITORING")
            print("=" * 70)
            print("1. 🔍 Escaneo único")
            print("2. 🤖 Modo automático v2.3")
            print("3. 📊 Estado del sistema v2.3")
            print("4. 🚪 Gestión de posiciones")
            print("5. 🎯 Dynamic Monitor")  # NUEVO
            print("6. 🧪 Tests v2.3")
            print("7. ⚙️ Configuración")
            print("8. 🏛️ Estado mercado")
            print("9. 📈 Smart Features stats")
            print("10. 📱 Test Telegram")
            print("11. ❌ Salir")
            print()
            
            choice = input("Opción (1-11): ").strip()
            
            if choice == "1":
                logger.info("🔍 Escaneo único v2.3...")
                signals = system.perform_scan_with_dynamic_integration()
                
                if signals:
                    print(f"\n✅ {len(signals)} señales:")
                    for i, signal in enumerate(signals, 1):
                        print(f"{i}. {signal.symbol} - {signal.signal_type} ({signal.signal_strength} pts)")
                        print(f"   Precio: ${signal.current_price:.2f}")
                        if signal.position_plan:
                            print(f"   R:R: 1:{signal.position_plan.max_risk_reward:.1f}")
                    
                    send = input("\n📱 ¿Enviar por Telegram y añadir a seguimiento? (y/n): ").lower()
                    if send == 'y':
                        system.process_signals_with_dynamic_integration(signals)
                else:
                    print("📊 Sin señales detectadas")
            
            elif choice == "2":
                print("🤖 Iniciando automático v2.3...")
                system.start_automatic_mode_v23()
                break
            
            elif choice == "3":
                status = system.get_system_status_v23()
                print("\n📊 ESTADO DEL SISTEMA V2.3:")
                print("=" * 60)
                print(f"Version: {status.get('version', 'N/A')}")
                print(f"Running: {'✅' if status['running'] else '❌'}")
                print(f"Market Open: {'✅' if status['market_open'] else '❌'}")
                
                components = status.get('components', {})
                print("\nComponentes:")
                for comp, active in components.items():
                    print(f"  {comp}: {'✅' if active else '❌'}")
                
                print(f"\nEstadísticas:")
                print(f"  Escaneos: {status['total_scans']}")
                print(f"  Señales: {status['signals_sent']}")
                print(f"  Alertas EXIT: {status['exit_alerts_sent']}")
                print(f"  Updates dinámicos: {status['dynamic_updates']}")
            
            elif choice == "4":
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
                    print(f"📊 PnL total: {positions_summary.get('total_unrealized_pnl', 0):+.1f}%")
            
            elif choice == "5":  # 🎯 NUEVO - Dynamic Monitor
                if not system.dynamic_monitor:
                    print("❌ Dynamic Monitor no disponible")
                    continue
                
                print("\n🎯 DYNAMIC MONITOR:")
                print("=" * 50)
                
                stats = system.dynamic_monitor.get_monitoring_stats()
                print(f"Running: {'✅' if stats['running'] else '❌'}")
                print(f"Targets totales: {stats['total_targets']}")
                print(f"Updates totales: {stats['total_updates']}")
                
                print("\nPor prioridad:")
                for priority, count in stats['targets_by_priority'].items():
                    if count > 0:
                        print(f"  {priority}: {count}")
                
                # Mostrar próximas actualizaciones
                next_updates = system.dynamic_monitor.get_next_update_schedule()
                if next_updates:
                    print(f"\nPróximas actualizaciones:")
                    for next_time, symbol, priority in next_updates[:5]:
                        time_diff = (next_time - datetime.now()).total_seconds() / 60
                        print(f"  {symbol}: {priority.value} en {time_diff:.1f} min")
                
                # Opciones adicionales
                print("\nAcciones disponibles:")
                print("a. Iniciar dynamic monitor")
                print("b. Detener dynamic monitor")
                print("c. Sincronizar con exit manager")
                
                sub_choice = input("Acción (a/b/c/enter para continuar): ").strip().lower()
                
                if sub_choice == 'a':
                    success = system.dynamic_monitor.start_dynamic_monitoring()
                    print(f"Resultado: {'✅ OK' if success else '❌ FALLO'}")
                elif sub_choice == 'b':
                    success = system.dynamic_monitor.stop_dynamic_monitoring()
                    print(f"Resultado: {'✅ OK' if success else '❌ FALLO'}")
                elif sub_choice == 'c':
                    system.dynamic_monitor.sync_with_exit_manager()
                    print("✅ Sincronización completada")
            
            elif choice == "6":
                print("🧪 Ejecutando tests v2.3...")
                
                # Test Telegram
                print("📱 Test Telegram...")
                system.telegram.send_test_message()
                
                # Test Dynamic Monitor
                if system.dynamic_monitor:
                    print("🎯 Test Dynamic Monitor...")
                    try:
                        success = system.dynamic_monitor.add_monitor_target("SPY", reason="Test")
                        print(f"✅ Dynamic Monitor: {'OK' if success else 'FALLO'}")
                        if success:
                            system.dynamic_monitor.remove_monitor_target("SPY", "Test completado")
                    except Exception as e:
                        print(f"❌ Error Dynamic Monitor: {e}")
                else:
                    print("❌ Dynamic Monitor no disponible")
                
                print("✅ Tests v2.3 completados")
            
            elif choice == "7":
                print("\n⚙️ CONFIGURACIÓN V2.3:")
                print("=" * 50)
                print(f"Símbolos: {len(config.SYMBOLS)}")
                print(f"Intervalo base: {config.SCAN_INTERVAL} min")
                print(f"Dynamic Monitor: {'✅ ACTIVO' if system.dynamic_monitor else '❌ NO DISPONIBLE'}")
                if system.dynamic_monitor:
                    print(f"  Frecuencias dinámicas: CRITICAL(2min) HIGH(5min) NORMAL(15min)")
                
                print(f"Exit Management: {'✅ ACTIVO' if system.exit_manager else '❌ NO DISPONIBLE'}")
                print(f"Smart Features: {'✅ ACTIVO' if system.smart_components else '❌ NO DISPONIBLE'}")
            
            elif choice == "8":
                market_open = system.is_market_open_now()
                print(f"\n🏛️ ESTADO MERCADO:")
                print(f"Abierto: {'✅ SÍ' if market_open else '❌ NO'}")
                
                if market_open:
                    print("📊 Sistema puede escanear normalmente")
                else:
                    print("😴 Sistema en modo sleep hasta próxima sesión")
            
            elif choice == "9":
                if system.smart_components:
                    try:
                        stats = system.smart_components['get_stats']()
                        print("\n📈 SMART FEATURES STATS:")
                        print("✅ Smart Features funcionando")
                        
                        # Rate limiter stats
                        if 'rate_limiter' in stats:
                            rl_stats = stats['rate_limiter']
                            print(f"🛡️ Rate Limiter:")
                            print(f"  Requests última hora: {rl_stats.get('requests_last_hour', 0)}")
                            print(f"  Uso: {rl_stats.get('usage_percentage', '0%')}")
                        
                        # Cache stats
                        if 'cache' in stats:
                            cache_stats = stats['cache']
                            print(f"💾 Cache:")
                            print(f"  Entradas totales: {cache_stats.get('total_entries', 0)}")
                            print(f"  Tamaño: {cache_stats.get('cache_size_mb', '0')} MB")
                    except Exception as e:
                        print(f"❌ Error obteniendo stats: {e}")
                else:
                    print("⚠️ Smart Features no disponibles")
            
            elif choice == "10":
                print("📱 Test Telegram...")
                success = system.telegram.send_test_message()
                print(f"Resultado: {'✅ OK' if success else '❌ FALLO'}")
            
            elif choice == "11":
                print("👋 ¡Hasta luego!")
                break
            
            else:
                print("❌ Opción no válida")
        
        except KeyboardInterrupt:
            print("\n👋 Saliendo...")
            break
        except Exception as e:
            logger.error(f"❌ Error en modo interactivo v2.3: {e}")

def main_v23():
    """🎯 NUEVO: Función principal v2.3 con dynamic monitoring"""
    try:
        # Validar configuración
        config_errors = config.validate_config()
        if config_errors:
            logger.error("❌ ERRORES DE CONFIGURACIÓN:")
            for error in config_errors:
                logger.error(f"  {error}")
            return 1
        
        # Info componentes v2.3
        logger.info("🔧 COMPONENTES DISPONIBLES V2.3:")
        logger.info(f"   📊 Scanner: ✅")
        logger.info(f"   📱 Telegram: ✅")
        logger.info(f"   🚪 Exit Manager: {'✅' if EXIT_MANAGER_AVAILABLE else '❌'}")
        logger.info(f"   🎯 Dynamic Monitor: {'✅' if DYNAMIC_MONITOR_AVAILABLE else '❌'}")
        logger.info(f"   🔥 Smart Features: {'✅' if SMART_FEATURES_AVAILABLE else '❌'}")
        
        # Determinar modo
        if len(sys.argv) > 1:
            mode = sys.argv[1].lower()
            
            if mode == "auto":
                logger.info("🤖 Modo automático v2.3 con Dynamic Monitoring")
                system = SmartTradingSystemV23WithDynamicMonitoring()
                system.start_automatic_mode_v23()
            
            elif mode == "scan":
                logger.info("🔍 Modo escaneo único v2.3")
                system = SmartTradingSystemV23WithDynamicMonitoring()
                signals = system.perform_scan_with_dynamic_integration()
                
                if signals:
                    print("\n✅ SEÑALES DETECTADAS V2.3:")
                    print("=" * 50)
                    for signal in signals:
                        print(f"{signal.symbol} - {signal.signal_type}")
                        print(f"  Fuerza: {signal.signal_strength}/100")
                        print(f"  Precio: ${signal.current_price:.2f}")
                        print(f"  Confianza: {signal.confidence_level}")
                        
                        # Mostrar si se añadió a dynamic monitor
                        if system.dynamic_monitor and signal.symbol in system.dynamic_monitor.monitor_targets:
                            target = system.dynamic_monitor.monitor_targets[signal.symbol]
                            print(f"  🎯 Dynamic Monitor: {target.priority.value}")
                        print()
                else:
                    print("📊 No se detectaron señales válidas")
            
            elif mode == "exits":
                logger.info("🚪 Modo evaluación de exits v2.3")
                system = SmartTradingSystemV23WithDynamicMonitoring()
                
                if not system.exit_manager:
                    print("❌ Exit Manager no disponible")
                    return 1
                
                exit_signals = system.perform_exit_evaluation_enhanced()
                
                if exit_signals:
                    print("\n🚨 ALERTAS DE EXIT DETECTADAS V2.3:")
                    print("=" * 60)
                    for signal in exit_signals:
                        print(f"{signal.symbol} - {signal.urgency.value}")
                        print(f"  Score deterioro: {signal.exit_score}/100")
                        print(f"  PnL actual: {signal.position.unrealized_pnl_pct:+.1f}%")
                        print(f"  Recomendación: Salir {signal.exit_percentage}%")
                        
                        # Mostrar info de dynamic monitor si aplica
                        if system.dynamic_monitor and signal.symbol in system.dynamic_monitor.monitor_targets:
                            target = system.dynamic_monitor.monitor_targets[signal.symbol]
                            print(f"  🎯 Monitor: {target.priority.value} ({target.update_count} updates)")
                        print()
                else:
                    print("✅ No hay alertas de exit necesarias")
            
            elif mode == "dynamic":  # 🎯 NUEVO modo
                logger.info("🎯 Modo Dynamic Monitor v2.3")
                system = SmartTradingSystemV23WithDynamicMonitoring()
                
                if not system.dynamic_monitor:
                    print("❌ Dynamic Monitor no disponible")
                    return 1
                
                # Añadir algunos targets para demo
                print("📊 Añadiendo targets de demo...")
                system.dynamic_monitor.add_monitor_target("SPY", reason="Demo mode")
                system.dynamic_monitor.add_monitor_target("QQQ", reason="Demo mode")
                
                # Iniciar monitoreo
                print("🚀 Iniciando Dynamic Monitor...")
                success = system.dynamic_monitor.start_dynamic_monitoring()
                
                if success:
                    try:
                        print("⏳ Ejecutando por 5 minutos... (Ctrl+C para detener)")
                        time.sleep(300)  # 5 minutos
                    except KeyboardInterrupt:
                        print("\n⏸️ Detenido por usuario")
                    
                    system.dynamic_monitor.stop_dynamic_monitoring()
                    
                    # Stats finales
                    stats = system.dynamic_monitor.get_monitoring_stats()
                    print(f"\n📈 RESULTADOS:")
                    print(f"Updates totales: {stats['total_updates']}")
                    print(f"Targets procesados: {stats['total_targets']}")
                else:
                    print("❌ Error iniciando Dynamic Monitor")
            
            elif mode == "test":
                logger.info("🧪 Modo testing completo v2.3")
                system = SmartTradingSystemV23WithDynamicMonitoring()
                
                print("🧪 EJECUTANDO TESTS COMPLETOS V2.3")
                print("=" * 70)
                
                # Test 1: Telegram
                print("1. 📱 Test Telegram...")
                try:
                    success = system.telegram.send_test_message()
                    print(f"   Resultado: {'✅ OK' if success else '❌ FALLO'}")
                except Exception as e:
                    print(f"   ❌ Error: {e}")
                
                # Test 2: Exit Manager
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
                
                # Test 3: Dynamic Monitor (NUEVO)
                print("3. 🎯 Test Dynamic Monitor...")
                if system.dynamic_monitor:
                    try:
                        # Test básico
                        success = system.dynamic_monitor.add_monitor_target("SPY", reason="Test")
                        if success:
                            print("   ✅ Añadir target: OK")
                            success = system.dynamic_monitor.update_monitor_target("SPY")
                            print(f"   ✅ Actualizar target: {'OK' if success else 'FALLO'}")
                            system.dynamic_monitor.remove_monitor_target("SPY", "Test completado")
                            print("   ✅ Remover target: OK")
                        else:
                            print("   ❌ Error añadiendo target")
                    except Exception as e:
                        print(f"   ❌ Error: {e}")
                else:
                    print("   ❌ Dynamic Monitor no disponible")
                
                # Test 4: Smart Features
                print("4. 🔥 Test Smart Features...")
                if system.smart_components:
                    try:
                        stats = system.smart_components['get_stats']()
                        print("   ✅ Smart Features funcionando")
                    except Exception as e:
                        print(f"   ❌ Error: {e}")
                else:
                    print("   ❌ Smart Features no disponible")
                
                print("\n✅ Todos los tests v2.3 completados")
            
            elif mode == "status":  # 🎯 NUEVO modo
                logger.info("📊 Modo status v2.3")
                system = SmartTradingSystemV23WithDynamicMonitoring()
                
                status = system.get_system_status_v23()
                
                print(f"\n📊 ESTADO COMPLETO DEL SISTEMA V2.3:")
                print("=" * 70)
                print(f"Versión: {status['version']}")
                print(f"Running: {'✅' if status['running'] else '❌'}")
                print(f"Market Open: {'✅' if status['market_open'] else '❌'}")
                
                print(f"\nComponentes:")
                components = status.get('components', {})
                for comp, active in components.items():
                    print(f"  {comp}: {'✅' if active else '❌'}")
                
                print(f"\nEstadísticas:")
                print(f"  Escaneos: {status['total_scans']}")
                print(f"  Señales: {status['signals_sent']}")
                print(f"  Alertas EXIT: {status['exit_alerts_sent']}")
                print(f"  Posiciones: {status['positions_tracked']}")
                print(f"  Updates dinámicos: {status['dynamic_updates']}")
                
                # Dynamic Monitor stats
                if 'dynamic_monitor_stats' in status:
                    dm_stats = status['dynamic_monitor_stats']
                    print(f"\nDynamic Monitor:")
                    print(f"  Targets activos: {dm_stats.get('total_targets', 0)}")
                    print(f"  Updates totales: {dm_stats.get('total_updates', 0)}")
                    print(f"  CRITICAL: {dm_stats.get('critical_updates', 0)}")
                    print(f"  HIGH: {dm_stats.get('high_updates', 0)}")
                
                # Posiciones
                if 'positions' in status:
                    pos_stats = status['positions']
                    if pos_stats.get('total_positions', 0) > 0:
                        print(f"\nPosiciones activas:")
                        print(f"  Total: {pos_stats['total_positions']}")
                        print(f"  LONG: {pos_stats.get('long_positions', 0)}")
                        print(f"  SHORT: {pos_stats.get('short_positions', 0)}")
                        print(f"  PnL total: {pos_stats.get('total_unrealized_pnl', 0):+.1f}%")
            
            else:
                print(f"❌ Modo '{mode}' no reconocido")
                print("Modos disponibles v2.3: auto, scan, exits, dynamic, test, status")
                return 1
        else:
            # Sin argumentos = modo interactivo v2.3
            mode_interactive_v23()
        
        return 0
        
    except Exception as e:
        logger.error(f"💥 Error crítico v2.3: {e}")
        return 1

if __name__ == "__main__":
    print("🎯 Smart Trading System v2.3 con Dynamic Monitoring")
    print("=" * 70)
    sys.exit(main_v23())