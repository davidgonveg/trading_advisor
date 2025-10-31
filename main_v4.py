#!/usr/bin/env python3
"""
🚀 MAIN.PY V4.0 - SISTEMA DE TRADING CON POSITION MANAGER
=========================================================================

🆕 V4.0 NUEVAS FUNCIONALIDADES POSITION MANAGER:
- ✅ Position Tracker: Estado completo de posiciones activas
- ✅ Execution Monitor: Detección automática de ejecuciones
- ✅ Signal Coordinator: Prevención inteligente de spam
- ✅ NO más señales redundantes cada 15 minutos
- ✅ Seguimiento granular de entradas/salidas escalonadas
- ✅ Ajuste automático de niveles basado en ejecuciones

🔄 MANTIENE TODAS LAS FUNCIONALIDADES V3.1:
- Extended Hours (pre/post/overnight)
- Continuous Data Collection 24/5
- Gap detection y auto-filling
- Dynamic Monitor V2.3
- Exit Manager

🎯 MEJORAS CLAVE V4.0:
- Scanner ya NO envía directamente a Telegram
- Signal Coordinator decide si crear posición o actualizar
- Monitor loop detecta ejecuciones automáticamente
- Sistema dual: Scanner + Position Monitor en paralelo
- Base de datos con tracking granular (position_executions)

⚡ CAMBIOS VS V3.1:
- perform_scan() → usa signal_coordinator.process_new_signal()
- Nuevo: monitor_positions_loop() para tracking continuo
- Estadísticas mejoradas con spam prevention
- Mensajes Telegram más informativos (con estado de ejecución)
"""

import logging
import signal
import sys
import time
import threading
from datetime import datetime, timedelta, time as dt_time
from typing import Optional, List, Dict, Any
import pytz

# Importaciones del sistema
try:
    import config
    from scanner import SignalScanner, TradingSignal
    from telegram_bot import TelegramBot
    from exit_manager import ExitManager
    
    # 🆕 V4.0: Position Manager
    from position_manager import (
        PositionTracker,
        ExecutionMonitor,
        SignalCoordinator,
        create_position_manager_system,
        get_version_info
    )
    
    # V3.1: Componentes para extended hours
    from continuous_collector import ContinuousDataCollector, CollectionStatus
    from gap_detector import GapDetector
    from data_validator import DataValidator, ValidationLevel
    
    # Dynamic Monitor (opcional)
    try:
        from dynamic_monitor import DynamicMonitor
        DYNAMIC_MONITOR_AVAILABLE = True
    except ImportError:
        DYNAMIC_MONITOR_AVAILABLE = False
        logging.warning("⚠️ Dynamic Monitor no disponible")
    
    print("✅ Todos los módulos importados correctamente")
    
except ImportError as e:
    print(f"❌ Error importando módulos: {e}")
    print("💡 Asegúrate de tener todos los archivos necesarios")
    sys.exit(1)

# Configurar logging
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, 'INFO'),
    format=config.LOG_FORMAT,
    handlers=[
        logging.FileHandler(config.LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class TradingSystemV40:
    """
    Sistema principal de trading V4.0 con Position Manager integrado
    """
    
    def __init__(self):
        """Inicializar sistema completo V4.0"""
        logger.info("🚀 Inicializando Trading System V4.0...")
        
        # Componentes principales (existentes)
        self.scanner = SignalScanner()
        self.telegram = TelegramBot()
        self.exit_manager = ExitManager()
        
        # 🆕 V4.0: Position Manager System
        logger.info("🔧 Inicializando Position Manager V4.0...")
        self.position_tracker, self.execution_monitor, self.signal_coordinator = \
            create_position_manager_system(
                use_database=True,
                use_real_prices=True,
                tolerance_pct=0.15,  # ±0.15% tolerancia para ejecuciones
                min_update_interval_minutes=30  # Mínimo 30min entre updates
            )
        
        # Conectar coordinator con scanner y telegram
        self.signal_coordinator.scanner = self.scanner
        self.signal_coordinator.telegram = self.telegram
        
        # Mostrar versión de Position Manager
        pm_version = get_version_info()
        logger.info(f"✅ Position Manager {pm_version['version']} - Status: {pm_version['status']}")
        
        # V3.1: Componentes para extended hours
        self.continuous_collector = None
        self.gap_detector = None
        self.data_validator = None
        
        # Dynamic Monitor (si está disponible)
        self.dynamic_monitor = None
        if DYNAMIC_MONITOR_AVAILABLE:
            try:
                self.dynamic_monitor = DynamicMonitor()
                logger.info("✅ Dynamic Monitor V2.3 integrado")
            except Exception as e:
                logger.warning(f"⚠️ No se pudo iniciar Dynamic Monitor: {e}")
        
        # Control de ejecución
        self.running = False
        self.shutdown_event = threading.Event()
        self.market_tz = pytz.timezone(config.MARKET_TIMEZONE)
        
        # Threads
        self.scan_thread = None
        self.monitor_thread = None  # 🆕 V4.0: Thread para position monitor
        self.collector_thread = None
        
        # Estadísticas
        self.stats = {
            'system_start': None,
            'total_scans': 0,
            'signals_generated': 0,
            'positions_created': 0,  # 🆕 V4.0
            'updates_sent': 0,  # 🆕 V4.0
            'spam_prevented': 0,  # 🆕 V4.0
            'data_collections': 0,
            'gaps_detected': 0,
            'gaps_filled': 0,
            'executions_detected': 0  # 🆕 V4.0
        }
        
        # V3.1: Inicializar componentes extended hours
        self._initialize_extended_hours_components()
        
        # Signal handlers para shutdown graceful
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        logger.info("✅ Trading System V4.0 inicializado")
    
    def _initialize_extended_hours_components(self):
        """V3.1: Inicializar componentes de extended hours"""
        try:
            if not config.is_extended_hours_enabled():
                logger.info("ℹ️ Extended hours deshabilitado en config")
                return
            
            logger.info("🕐 Inicializando componentes Extended Hours...")
            
            # Gap Detector
            try:
                self.gap_detector = GapDetector()
                logger.info("✅ Gap Detector inicializado")
            except Exception as e:
                logger.warning(f"⚠️ Gap Detector no disponible: {e}")
            
            # Data Validator
            try:
                self.data_validator = DataValidator()
                logger.info("✅ Data Validator inicializado")
            except Exception as e:
                logger.warning(f"⚠️ Data Validator no disponible: {e}")
            
            # Continuous Collector
            try:
                self.continuous_collector = ContinuousDataCollector()
                logger.info("✅ Continuous Collector inicializado")
                logger.info(f"   📊 Sesiones configuradas: {len(self.continuous_collector.sessions)}")
                logger.info(f"   🎯 Símbolos a monitorear: {len(self.continuous_collector.symbols)}")
            except Exception as e:
                logger.error(f"❌ Error inicializando Continuous Collector: {e}")
                self.continuous_collector = None
            
            if self.continuous_collector:
                logger.info("✅ Sistema Extended Hours completo operacional")
            else:
                logger.warning("⚠️ Sistema funcionará sin continuous collection")
                
        except Exception as e:
            logger.error(f"❌ Error inicializando extended hours: {e}")
    
    def _signal_handler(self, signum, frame):
        """Manejar señales del sistema para shutdown graceful"""
        logger.info(f"📡 Señal {signum} recibida")
        self.stop_system()
    
    def is_market_open_now(self) -> bool:
        """V3.1: Verificar horarios de mercado con soporte extended hours"""
        try:
            if getattr(config, 'DEVELOPMENT_MODE', False):
                return True
            
            now = datetime.now(self.market_tz)
            current_time = now.time()
            weekday = now.weekday()
            
            if weekday not in config.ALLOWED_WEEKDAYS:
                return False
            
            # Si extended hours habilitado
            if config.is_extended_hours_enabled():
                session_name, session_config = config.get_current_trading_session()
                
                if session_name and session_config and session_config.get('ENABLED', False):
                    logger.debug(f"🕐 En sesión: {session_name}")
                    return True
                
                return True  # Día laborable = considerar abierto
            
            # Lógica tradicional
            sessions = config.TRADING_SESSIONS
            
            morning_start = dt_time.fromisoformat(sessions['MORNING']['START'])
            morning_end = dt_time.fromisoformat(sessions['MORNING']['END'])
            afternoon_start = dt_time.fromisoformat(sessions['AFTERNOON']['START'])
            afternoon_end = dt_time.fromisoformat(sessions['AFTERNOON']['END'])
            
            in_morning = morning_start <= current_time <= morning_end
            in_afternoon = afternoon_start <= current_time <= afternoon_end
            
            return in_morning or in_afternoon
            
        except Exception as e:
            logger.error(f"❌ Error verificando horarios: {e}")
            return True
    
    def should_run_scanner_now(self) -> bool:
        """V3.1: Determinar si debe ejecutar scanner ahora"""
        try:
            if getattr(config, 'DEVELOPMENT_MODE', False):
                return True
            
            now = datetime.now(self.market_tz)
            current_time = now.time()
            weekday = now.weekday()
            
            if weekday not in config.ALLOWED_WEEKDAYS:
                return False
            
            sessions = config.TRADING_SESSIONS
            
            morning_start = dt_time.fromisoformat(sessions['MORNING']['START'])
            morning_end = dt_time.fromisoformat(sessions['MORNING']['END'])
            afternoon_start = dt_time.fromisoformat(sessions['AFTERNOON']['START'])
            afternoon_end = dt_time.fromisoformat(sessions['AFTERNOON']['END'])
            
            in_morning = morning_start <= current_time <= morning_end
            in_afternoon = afternoon_start <= current_time <= afternoon_end
            
            return in_morning or in_afternoon
            
        except Exception as e:
            logger.error(f"❌ Error verificando horarios scanner: {e}")
            return False
    
    def perform_scan(self) -> List[TradingSignal]:
        """Ejecutar escaneo de señales"""
        try:
            logger.info("🔍 Ejecutando escaneo de mercado...")
            
            symbols = config.TEST_SYMBOLS if config.TEST_MODE else config.SYMBOLS
            signals = self.scanner.scan_multiple_symbols(symbols)
            
            self.stats['total_scans'] += 1
            self.stats['signals_generated'] += len(signals)
            
            if signals:
                logger.info(f"✅ {len(signals)} señales detectadas")
            else:
                logger.debug("ℹ️ No hay señales en este momento")
            
            return signals
            
        except Exception as e:
            logger.error(f"❌ Error en escaneo: {e}")
            return []
    
    def process_signals(self, signals: List[TradingSignal]) -> None:
        """
        🔧 V4.0: Procesar señales usando Signal Coordinator
        
        CAMBIO CLAVE vs V3.1:
        - Ya NO envía directamente por Telegram
        - Usa signal_coordinator.process_new_signal()
        - Coordinator decide si crear nueva posición o actualizar
        """
        try:
            if not signals:
                return
            
            for signal in signals:
                try:
                    # 🆕 V4.0: Procesar con coordinator
                    success = self.signal_coordinator.process_new_signal(signal)
                    
                    if success:
                        self.stats['positions_created'] += 1
                        logger.info(f"✅ Señal {signal.symbol} procesada correctamente")
                    else:
                        self.stats['spam_prevented'] += 1
                        logger.debug(f"⏭️ Update omitido para {signal.symbol} (spam prevention)")
                    
                    # Exit manager (mantener por compatibilidad)
                    if self.exit_manager:
                        try:
                            self.exit_manager.add_position_from_signal(signal)
                        except Exception as e:
                            logger.error(f"❌ Error registrando en exit manager: {e}")
                    
                    time.sleep(1)  # Delay entre procesos
                    
                except Exception as e:
                    logger.error(f"❌ Error procesando señal {signal.symbol}: {e}")
            
        except Exception as e:
            logger.error(f"❌ Error procesando señales: {e}")
    
    def evaluate_exits(self) -> None:
        """Evaluar salidas de posiciones abiertas (mantener por compatibilidad)"""
        try:
            if not self.exit_manager:
                return
            
            logger.debug("🎯 Evaluando salidas...")
            exit_signals = self.exit_manager.evaluate_all_positions()
            
            if exit_signals:
                logger.info(f"🚨 {len(exit_signals)} alertas de exit generadas")
                
                for exit_signal in exit_signals:
                    try:
                        self.telegram.send_exit_alert(
                            exit_signal['symbol'],
                            exit_signal
                        )
                        time.sleep(1)
                    except Exception as e:
                        logger.error(f"❌ Error enviando exit alert: {e}")
            
        except Exception as e:
            logger.error(f"❌ Error evaluando exits: {e}")
    
    def run_scanner_loop(self) -> None:
        """Loop principal del scanner"""
        try:
            logger.info("🔍 Scanner loop iniciado (V4.0)")
            
            last_scan = datetime.now()
            scan_interval = timedelta(minutes=config.SCAN_INTERVAL)
            
            while self.running and not self.shutdown_event.is_set():
                
                # Verificar si debe ejecutar scanner
                if not self.should_run_scanner_now():
                    logger.debug("💤 Fuera de horarios de scanner, esperando...")
                    if self.shutdown_event.wait(60):
                        break
                    continue
                
                # ¿Toca escaneo?
                now = datetime.now()
                if now - last_scan >= scan_interval:
                    
                    signals = self.perform_scan()
                    
                    if not self.running:
                        break
                    
                    # 🔧 V4.0: Procesar con coordinator
                    if signals:
                        self.process_signals(signals)
                    
                    # Evaluar exits (compatibilidad)
                    self.evaluate_exits()
                    
                    last_scan = now
                
                # Sleep con verificación de shutdown
                if self.shutdown_event.wait(30):
                    break
            
        except Exception as e:
            logger.error(f"❌ Error en scanner loop: {e}")
        finally:
            logger.info("🏁 Scanner loop finalizado")
    
    def monitor_positions_loop(self) -> None:
        """
        🆕 V4.0: Loop de monitoreo de posiciones - FIXED
        
        NUEVA FUNCIONALIDAD:
        - Monitorea todas las posiciones activas cada 5min
        - Detecta ejecuciones de niveles automáticamente
        - Envía notificaciones cuando se ejecutan entradas/salidas
        - Actualiza métricas en tiempo real (P&L, % ejecutado, etc)
        """
        try:
            logger.info("🎯 Position Monitor loop iniciado (V4.0)")
            
            monitor_interval = 300  # 5 minutos
            
            while self.running and not self.shutdown_event.is_set():
                
                try:
                    # Monitorear todas las posiciones activas
                    events_by_position = self.execution_monitor.monitor_all_positions()
                    
                    if events_by_position:
                        logger.info(f"📊 Eventos detectados en {len(events_by_position)} posiciones")
                        
                        # Procesar cada posición con eventos
                        for position_id, events in events_by_position.items():
                            try:
                                # Obtener posición
                                position = self.position_tracker.get_position_by_id(position_id)
                                
                                if not position:
                                    logger.warning(f"⚠️ Posición {position_id[:8]}... no encontrada")
                                    continue
                                
                                # ✅ FIX: Verificar si debe enviar update
                                if self.signal_coordinator.should_send_update_for_events(position, events):
                                    
                                    # ✅ FIX: Usar método correcto
                                    message = self.signal_coordinator.generate_update_message(
                                        position, 
                                        events
                                    )
                                    
                                    # Enviar mensaje
                                    if message and self.telegram.send_message(message):
                                        self.stats['executions_detected'] += len(events)
                                        self.stats['updates_sent'] += 1
                                        logger.info(f"📱 Update enviado: {position.symbol} ({len(events)} eventos)")
                                    
                                    time.sleep(1)  # Delay entre mensajes
                                
                                else:
                                    logger.debug(f"⏭️ Update omitido para {position.symbol} (intervalo mínimo)")
                                    self.stats['spam_prevented'] += 1
                            
                            except Exception as e:
                                logger.error(f"❌ Error procesando eventos de {position_id[:8]}: {e}")
                                continue
                    
                    else:
                        logger.debug("ℹ️ No hay eventos en posiciones activas")
                    
                    # Actualizar estadísticas del coordinator
                    try:
                        coord_stats = self.signal_coordinator.get_statistics()
                        self.stats['updates_sent'] = coord_stats['updates_sent']
                        self.stats['spam_prevented'] = coord_stats['spam_prevented']
                    except Exception as e:
                        logger.debug(f"No se pudieron actualizar stats del coordinator: {e}")
                    
                except Exception as e:
                    logger.error(f"❌ Error en monitoreo de posiciones: {e}")
                
                # Sleep con verificación de shutdown
                if self.shutdown_event.wait(monitor_interval):
                    break
            
        except Exception as e:
            logger.error(f"❌ Error en position monitor loop: {e}")
        finally:
            logger.info("🏁 Position Monitor loop finalizado")
    
    def run_maintenance_tasks(self) -> None:
        """V3.1: Tareas de mantenimiento periódicas"""
        try:
            logger.info("🔧 Ejecutando tareas de mantenimiento...")
            
            # Gap maintenance
            if self.continuous_collector:
                try:
                    maintenance_result = self.continuous_collector.perform_gap_maintenance()
                    
                    if maintenance_result.get('success'):
                        logger.info(f"✅ Gap maintenance: {maintenance_result['gaps_filled']} gaps rellenados")
                        self.stats['gaps_detected'] += maintenance_result.get('total_gaps_found', 0)
                        self.stats['gaps_filled'] += maintenance_result.get('gaps_filled', 0)
                    
                except Exception as e:
                    logger.error(f"❌ Error en gap maintenance: {e}")
            
            # Validación de datos
            if self.data_validator:
                try:
                    for symbol in config.SYMBOLS[:3]:
                        report = self.data_validator.validate_symbol(
                            symbol,
                            days_back=7
                        )
                        
                        if report.needs_attention:
                            logger.warning(f"⚠️ {symbol}: Requiere atención - Score {report.overall_score:.1f}")
                        
                except Exception as e:
                    logger.error(f"❌ Error en validación de datos: {e}")
            
            logger.info("✅ Mantenimiento completado")
            
        except Exception as e:
            logger.error(f"❌ Error en maintenance tasks: {e}")
    
    def start_system(self) -> bool:
        """Iniciar sistema completo V4.0"""
        try:
            if self.running:
                logger.warning("⚠️ Sistema ya está ejecutándose")
                return False
            
            logger.info("=" * 70)
            logger.info("🚀 INICIANDO SMART TRADING SYSTEM V4.0")
            logger.info("=" * 70)
            
            # Verificar componentes críticos
            if not self.telegram.initialized:
                logger.error("❌ Telegram bot no inicializado")
                return False
            
            # Enviar mensaje de inicio
            self._send_startup_message()
            
            # Mostrar configuración
            self._log_system_configuration()
            
            # Iniciar sistema
            self.running = True
            self.stats['system_start'] = datetime.now()
            
            # Continuous Collector (V3.1)
            if self.continuous_collector and config.is_extended_hours_enabled():
                logger.info("🕐 Iniciando Continuous Data Collector...")
                collector_success = self.continuous_collector.start_collection()
                
                if collector_success:
                    logger.info("✅ Continuous Collector operacional")
                else:
                    logger.warning("⚠️ Continuous Collector falló")
            
            # Dynamic Monitor (opcional)
            if self.dynamic_monitor:
                logger.info("🎯 Iniciando Dynamic Monitor...")
                monitor_success = self.dynamic_monitor.start_monitoring()
                
                if monitor_success:
                    logger.info("✅ Dynamic Monitor operacional")
                else:
                    logger.warning("⚠️ Dynamic Monitor falló")
            
            # 🔧 V4.0: Iniciar thread del scanner
            self.scan_thread = threading.Thread(
                target=self.run_scanner_loop,
                daemon=True,
                name="ScannerLoop-V4"
            )
            self.scan_thread.start()
            
            # 🆕 V4.0: Iniciar thread del position monitor
            self.monitor_thread = threading.Thread(
                target=self.monitor_positions_loop,
                daemon=True,
                name="PositionMonitor-V4"
            )
            self.monitor_thread.start()
            
            # Programar maintenance tasks periódicas
            self._schedule_maintenance_tasks()
            
            logger.info("✅ Smart Trading System V4.0 iniciado correctamente")
            logger.info("🎯 Monitoreo activo - Presiona Ctrl+C para detener")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error iniciando sistema: {e}")
            self.running = False
            return False
    
    def _schedule_maintenance_tasks(self) -> None:
        """Programar tareas de mantenimiento periódicas"""
        def maintenance_worker():
            last_maintenance = datetime.now()
            maintenance_interval = timedelta(hours=6)
            
            while self.running and not self.shutdown_event.is_set():
                now = datetime.now()
                
                if now - last_maintenance >= maintenance_interval:
                    self.run_maintenance_tasks()
                    last_maintenance = now
                
                if self.shutdown_event.wait(1800):  # Check cada 30min
                    break
        
        maintenance_thread = threading.Thread(
            target=maintenance_worker,
            daemon=True,
            name="MaintenanceWorker"
        )
        maintenance_thread.start()
    
    def stop_system(self) -> None:
        """Detener sistema completo V4.0"""
        try:
            logger.info("🛑 Deteniendo Smart Trading System V4.0...")
            
            self.running = False
            self.shutdown_event.set()
            
            # Detener Continuous Collector
            if self.continuous_collector:
                logger.info("🕐 Deteniendo Continuous Collector...")
                self.continuous_collector.stop_collection()
            
            # Detener Dynamic Monitor
            if self.dynamic_monitor:
                logger.info("🎯 Deteniendo Dynamic Monitor...")
                self.dynamic_monitor.stop_monitoring()
            
            # Esperar threads
            if self.scan_thread and self.scan_thread.is_alive():
                logger.info("⏳ Esperando scanner thread...")
                self.scan_thread.join(timeout=15)
            
            # 🆕 V4.0: Esperar position monitor thread
            if self.monitor_thread and self.monitor_thread.is_alive():
                logger.info("⏳ Esperando position monitor thread...")
                self.monitor_thread.join(timeout=15)
            
            # Guardar posiciones
            try:
                if self.exit_manager:
                    self.exit_manager.save_positions()
                    logger.info("💾 Posiciones guardadas")
            except Exception as e:
                logger.error(f"❌ Error guardando posiciones: {e}")
            
            # Mostrar estadísticas finales
            self._log_final_statistics()
            
            # Enviar mensaje de cierre
            try:
                uptime = datetime.now() - self.stats['system_start']
                
                # 🆕 V4.0: Estadísticas mejoradas
                coord_stats = self.signal_coordinator.get_statistics()
                pm_summary = self.position_tracker.get_active_positions_summary()
                
                message = (
                    f"🛑 <b>Sistema Detenido V4.0</b>\n\n"
                    f"⏱️ Uptime: {uptime}\n"
                    f"🔍 Escaneos: {self.stats['total_scans']}\n"
                    f"📊 Señales: {self.stats['signals_generated']}\n"
                    f"🎯 Posiciones creadas: {self.stats['positions_created']}\n"
                    f"📱 Updates enviados: {self.stats['updates_sent']}\n"
                    f"🛡️ Spam prevenido: {self.stats['spam_prevented']}\n"
                    f"⚡ Ejecuciones detectadas: {self.stats['executions_detected']}\n"
                    f"🕐 Collections: {self.stats['data_collections']}\n"
                    f"🔧 Gaps rellenados: {self.stats['gaps_filled']}\n\n"
                    f"📊 Posiciones activas: {pm_summary['total_positions']}\n"
                    f"💹 P&L total: {pm_summary.get('total_unrealized_pnl', 0):.2f}%"
                )
                
                self.telegram.send_message(message)
            except:
                pass
            
            logger.info("✅ Sistema detenido correctamente")
            
        except Exception as e:
            logger.error(f"❌ Error deteniendo sistema: {e}")
    
    def _send_startup_message(self) -> None:
        """Enviar mensaje de inicio por Telegram"""
        try:
            now = datetime.now(self.market_tz)
            
            session_info = "N/A"
            if config.is_extended_hours_enabled():
                session_name, session_config = config.get_current_trading_session()
                if session_name:
                    session_info = f"{session_name} ({session_config.get('DESCRIPTION', 'N/A')})"
            
            # 🆕 V4.0: Información de Position Manager
            pm_version = get_version_info()
            
            message = (
                f"🚀 <b>Trading System V4.0 Iniciado</b>\n\n"
                f"⏰ Hora: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}\n"
                f"🕐 Extended Hours: {'✅ Activo' if config.is_extended_hours_enabled() else '❌ Desactivado'}\n"
                f"📊 Sesión actual: {session_info}\n"
                f"🎯 Símbolos: {len(config.SYMBOLS)}\n"
                f"🔍 Intervalo scan: {config.SCAN_INTERVAL} min\n\n"
                f"🆕 <b>Position Manager {pm_version['version']}</b>\n"
                f"✅ Tracking granular de posiciones\n"
                f"✅ Detección automática de ejecuciones\n"
                f"✅ Prevención inteligente de spam\n\n"
                f"💰 Riesgo/trade: {config.RISK_PER_TRADE}%\n"
                f"🤖 Modo: {'🧪 Desarrollo' if config.DEVELOPMENT_MODE else '🚀 Producción'}"
            )
            
            self.telegram.send_message(message)
            
        except Exception as e:
            logger.error(f"❌ Error enviando mensaje de inicio: {e}")
    
    def _log_system_configuration(self) -> None:
        """Mostrar configuración del sistema"""
        logger.info("=" * 70)
        logger.info("⚙️ CONFIGURACIÓN DEL SISTEMA V4.0")
        logger.info("=" * 70)
        logger.info(f"📊 Símbolos monitoreados: {len(config.SYMBOLS)}")
        logger.info(f"⏰ Intervalo de escaneo: {config.SCAN_INTERVAL} minutos")
        logger.info(f"💰 Riesgo por operación: {config.RISK_PER_TRADE}%")
        logger.info(f"🕐 Extended Hours: {'✅ Habilitado' if config.is_extended_hours_enabled() else '❌ Deshabilitado'}")
        logger.info(f"🤖 Modo desarrollo: {'✅ Sí' if config.DEVELOPMENT_MODE else '❌ No'}")
        logger.info(f"📱 Telegram: {'✅ OK' if self.telegram.initialized else '❌ Error'}")
        
        # 🆕 V4.0: Info de Position Manager
        pm_version = get_version_info()
        logger.info(f"🎯 Position Manager: ✅ {pm_version['version']} ({pm_version['status']})")
        logger.info(f"   • Position Tracker: ✅ Operacional")
        logger.info(f"   • Execution Monitor: ✅ Operacional")
        logger.info(f"   • Signal Coordinator: ✅ Operacional")
        logger.info(f"   • Tolerancia ejecución: ±0.15%")
        logger.info(f"   • Min intervalo updates: 30 minutos")
        
        logger.info(f"🎯 Dynamic Monitor: {'✅ Disponible' if self.dynamic_monitor else '❌ No disponible'}")
        logger.info(f"🕐 Continuous Collector: {'✅ Disponible' if self.continuous_collector else '❌ No disponible'}")
        
        # Mostrar sesiones configuradas si extended hours activo
        if config.is_extended_hours_enabled():
            logger.info("🕐 Sesiones Extended Hours configuradas:")
            for name, conf in config.EXTENDED_TRADING_SESSIONS.items():
                if conf.get('ENABLED'):
                    logger.info(f"   • {name}: {conf['START']}-{conf['END']} (cada {conf['DATA_INTERVAL']}min)")
        
        logger.info("=" * 70)
    
    def _log_final_statistics(self) -> None:
        """Mostrar estadísticas finales"""
        if not self.stats['system_start']:
            return
        
        uptime = datetime.now() - self.stats['system_start']
        
        # 🆕 V4.0: Estadísticas del coordinator
        coord_stats = self.signal_coordinator.get_statistics()
        pm_summary = self.position_tracker.get_active_positions_summary()
        
        logger.info("=" * 70)
        logger.info("📊 ESTADÍSTICAS FINALES V4.0")
        logger.info("=" * 70)
        logger.info(f"⏱️ Uptime: {uptime}")
        logger.info(f"🔍 Total escaneos: {self.stats['total_scans']}")
        logger.info(f"📊 Señales generadas: {self.stats['signals_generated']}")
        
        # 🆕 V4.0: Estadísticas de Position Manager
        logger.info("\n🎯 POSITION MANAGER:")
        logger.info(f"   Posiciones creadas: {self.stats['positions_created']}")
        logger.info(f"   Updates enviados: {self.stats['updates_sent']}")
        logger.info(f"   Spam prevenido: {self.stats['spam_prevented']}")
        logger.info(f"   Ejecuciones detectadas: {self.stats['executions_detected']}")
        logger.info(f"   Tasa prevención spam: {coord_stats.get('spam_prevention_rate', 0):.1f}%")
        logger.info(f"   Posiciones activas: {pm_summary['total_positions']}")
        
        if pm_summary['total_positions'] > 0:
            logger.info(f"   P&L total no realizado: {pm_summary.get('total_unrealized_pnl', 0):+.2f}%")
            logger.info(f"   Posiciones LONG: {pm_summary['by_direction']['LONG']}")
            logger.info(f"   Posiciones SHORT: {pm_summary['by_direction']['SHORT']}")
        
        # V3.1: Estadísticas de data collection
        logger.info(f"\n🕐 DATA COLLECTION:")
        logger.info(f"   Collections: {self.stats['data_collections']}")
        logger.info(f"   Gaps detectados: {self.stats['gaps_detected']}")
        logger.info(f"   Gaps rellenados: {self.stats['gaps_filled']}")
        logger.info("=" * 70)


# =============================================================================
# 🎯 FUNCIONES DE UTILIDAD
# =============================================================================

def run_single_scan():
    """Ejecutar un escaneo único sin loop continuo"""
    print("🔍 ESCANEO ÚNICO - TRADING SYSTEM V4.0")
    print("=" * 70)
    
    try:
        # Inicializar componentes necesarios
        scanner = SignalScanner()
        telegram = TelegramBot()
        
        # 🆕 V4.0: Inicializar position manager para el scan
        tracker, monitor, coordinator = create_position_manager_system(
            use_database=False,  # No DB para scan único
            use_real_prices=False
        )
        coordinator.scanner = scanner
        coordinator.telegram = telegram
        
        # Verificar horarios
        now = datetime.now(pytz.timezone(config.MARKET_TIMEZONE))
        print(f"⏰ Hora actual: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        
        is_market_open = scanner.is_market_open()
        print(f"🏛️ Mercado: {'🟢 ABIERTO' if is_market_open else '🔴 CERRADO'}")
        
        if not is_market_open and not config.DEVELOPMENT_MODE:
            print("⚠️ Mercado cerrado - Activar DEVELOPMENT_MODE para escanear")
            return
        
        # Escanear
        print(f"\n🔍 Escaneando {len(config.SYMBOLS)} símbolos...")
        signals = scanner.scan_multiple_symbols(config.SYMBOLS)
        
        # Mostrar resultados
        print(f"\n📊 RESULTADOS:")
        print(f"   Señales detectadas: {len(signals)}")
        
        if signals:
            print(f"\n🎯 SEÑALES:")
            for i, signal in enumerate(signals, 1):
                print(f"\n   {i}. {signal.symbol} - {signal.signal_type}")
                print(f"      💪 Fuerza: {signal.signal_strength}/100")
                print(f"      🎯 Calidad: {signal.entry_quality}")
                print(f"      💰 Precio: ${signal.current_price:.2f}")
            
            # Preguntar si enviar alertas
            if telegram.initialized:
                response = input("\n📱 ¿Enviar alertas por Telegram? (y/N): ").lower().strip()
                if response == 'y':
                    # 🔧 V4.0: Usar coordinator para enviar
                    for signal in signals:
                        coordinator.process_new_signal(signal)
                        time.sleep(1)
                    print("✅ Alertas enviadas")
        else:
            print("   ℹ️ No hay señales válidas en este momento")
            print("   💡 El sistema es muy selectivo - esto es normal")
        
        print(f"\n✅ Escaneo completado")
        
    except Exception as e:
        print(f"❌ Error en escaneo: {e}")
        logger.error(f"Error en single scan: {e}", exc_info=True)


def run_position_status():
    """🆕 V4.0: Mostrar estado de posiciones activas"""
    print("📊 ESTADO DE POSICIONES - TRADING SYSTEM V4.0")
    print("=" * 70)
    
    try:
        # Inicializar position manager
        tracker, monitor, coordinator = create_position_manager_system(
            use_database=True,
            use_real_prices=False
        )
        
        # Obtener resumen
        summary = tracker.get_active_positions_summary()
        
        print(f"\n📈 RESUMEN GENERAL:")
        print(f"   Total posiciones activas: {summary['total_positions']}")
        
        if summary['total_positions'] == 0:
            print("   ℹ️ No hay posiciones activas")
            return
        
        print(f"   LONG: {summary['by_direction']['LONG']}")
        print(f"   SHORT: {summary['by_direction']['SHORT']}")
        print(f"   P&L total no realizado: {summary.get('total_unrealized_pnl', 0):+.2f}%")
        print(f"   P&L promedio: {summary.get('average_pnl', 0):+.2f}%")
        
        # Por status
        if summary['by_status']:
            print(f"\n📊 POR ESTADO:")
            for status, count in summary['by_status'].items():
                print(f"   {status}: {count}")
        
        # Detalle de cada posición
        if summary.get('positions'):
            print(f"\n🎯 DETALLE DE POSICIONES:")
            for symbol, pos_data in summary['positions'].items():
                print(f"\n   {symbol} ({pos_data['direction']}):")
                print(f"      Status: {pos_data['status']}")
                print(f"      P&L: {pos_data['pnl']:+.2f}%")
                print(f"      % Ejecutado: {pos_data['filled_percentage']:.1f}%")
        
        # Estadísticas del coordinator
        coord_stats = coordinator.get_statistics()
        print(f"\n📱 ESTADÍSTICAS DE MENSAJES:")
        print(f"   Señales procesadas: {coord_stats['signals_processed']}")
        print(f"   Posiciones nuevas: {coord_stats['new_positions_created']}")
        print(f"   Updates enviados: {coord_stats['updates_sent']}")
        print(f"   Updates omitidos: {coord_stats['updates_skipped']}")
        print(f"   Spam prevenido: {coord_stats['spam_prevented']}")
        print(f"   Tasa prevención: {coord_stats['spam_prevention_rate']:.1f}%")
        
        print(f"\n✅ Estado verificado")
        
    except Exception as e:
        print(f"❌ Error verificando posiciones: {e}")
        logger.error(f"Error en position status: {e}", exc_info=True)


def run_data_validation():
    """V3.1: Ejecutar validación de datos históricos"""
    print("🔍 VALIDACIÓN DE DATOS - TRADING SYSTEM V4.0")
    print("=" * 70)
    
    try:
        from data_validator import DataValidator, ValidationLevel
        
        validator = DataValidator(validation_level=ValidationLevel.STANDARD)
        
        print(f"\n📊 Validando {len(config.SYMBOLS[:5])} símbolos principales...")
        
        for symbol in config.SYMBOLS[:5]:
            print(f"\n🎯 {symbol}:")
            
            report = validator.validate_symbol(
                symbol=symbol,
                days_back=30
            )
            
            print(f"   Score: {report.overall_score:.1f}/100")
            print(f"   Status: {report.overall_status.value}")
            print(f"   Backtest ready: {'✅' if report.backtest_ready else '❌'}")
            
            if report.critical_issues:
                print(f"   🚨 Issues críticos: {len(report.critical_issues)}")
                for issue in report.critical_issues[:3]:
                    print(f"      • {issue}")
            
            if report.warnings:
                print(f"   ⚠️ Warnings: {len(report.warnings)}")
                for warning in report.warnings[:2]:
                    print(f"      • {warning}")
            
            if report.recommendations:
                print(f"   💡 Recomendaciones:")
                for rec in report.recommendations[:2]:
                    print(f"      • {rec}")
        
        print("\n✅ Validación completada")
        
    except Exception as e:
        print(f"❌ Error en validación: {e}")
        logger.error(f"Error en data validation: {e}", exc_info=True)


def run_gap_analysis():
    """V3.1: Ejecutar análisis de gaps en datos"""
    print("🔧 ANÁLISIS DE GAPS - TRADING SYSTEM V4.0")
    print("=" * 70)
    
    try:
        gap_detector = GapDetector()
        
        print(f"\n📊 Analizando gaps en {len(config.SYMBOLS[:3])} símbolos...")
        
        total_gaps = 0
        total_fillable = 0
        
        for symbol in config.SYMBOLS[:3]:
            print(f"\n🎯 {symbol}:")
            
            from indicators import TechnicalIndicators
            indicators = TechnicalIndicators()
            data = indicators.get_all_indicators(symbol)
            
            if 'market_data' in data and not data['market_data'].empty:
                report = gap_detector.analyze_data_quality(
                    data['market_data'],
                    symbol,
                    expected_interval_minutes=15
                )
                
                print(f"   Gaps detectados: {report.total_gaps}")
                
                fillable_gaps = len([
                    gap for gap in report.gaps_detected 
                    if hasattr(gap, 'is_fillable') and gap.is_fillable
                ])
                
                print(f"   Gaps rellenables: {fillable_gaps}")
                print(f"   Completitud: {report.completeness_pct:.1f}%")
                print(f"   Score calidad: {report.overall_quality_score:.1f}/100")
                
                total_gaps += report.total_gaps
                total_fillable += fillable_gaps
                
                critical_gaps = [g for g in report.gaps_detected 
                                if hasattr(g, 'severity') and g.severity.value in ['HIGH', 'CRITICAL']]
                
                if critical_gaps:
                    print(f"   ⚠️ Gaps críticos: {len(critical_gaps)}")
                    for gap in critical_gaps[:2]:
                        duration = gap.duration_minutes if hasattr(gap, 'duration_minutes') else 0
                        gap_type = gap.gap_type.value if hasattr(gap, 'gap_type') else 'UNKNOWN'
                        print(f"      • {gap_type}: {duration:.0f} min")
        
        print(f"\n📊 RESUMEN TOTAL:")
        print(f"   Total gaps: {total_gaps}")
        print(f"   Rellenables: {total_fillable}")
        if total_gaps > 0:
            print(f"   Tasa rellenable: {(total_fillable/total_gaps*100):.1f}%")
        else:
            print(f"   Tasa rellenable: N/A (sin gaps)")
        
        print(f"\n✅ Análisis completado")
        
    except Exception as e:
        print(f"❌ Error en análisis: {e}")
        logger.error(f"Error en gap analysis: {e}", exc_info=True)


def run_collector_test():
    """V3.1: Test del continuous collector"""
    print("🕐 TEST CONTINUOUS COLLECTOR - TRADING SYSTEM V4.0")
    print("=" * 70)
    
    try:
        collector = ContinuousDataCollector()
        
        print(f"📊 Collector configurado:")
        print(f"   Símbolos: {len(collector.symbols)}")
        print(f"   Sesiones: {len(collector.sessions)}")
        print(f"   Status: {collector.status.value}")
        
        print(f"\n🕐 Sesiones configuradas:")
        for session in collector.sessions:
            enabled = "✅" if session.enabled else "❌"
            print(f"   {enabled} {session.name}: {session.start_time}-{session.end_time} "
                  f"(cada {session.interval_minutes}min)")
        
        print(f"\n🔧 Ejecutando recolección forzada de test...")
        test_symbols = collector.symbols[:2]
        
        results = collector.force_collection_now(test_symbols)
        
        print(f"\n📊 Resultados:")
        for result in results:
            status = "✅" if result.success else "❌"
            print(f"   {status} {result.symbol}:")
            print(f"      Puntos: {result.data_points}")
            print(f"      Gaps: {result.gaps_detected} detectados, {result.gaps_filled} rellenados")
            print(f"      Tiempo: {result.collection_time_ms:.0f}ms")
        
        print(f"\n✅ Test completado")
        
    except Exception as e:
        print(f"❌ Error en test: {e}")
        logger.error(f"Error en collector test: {e}", exc_info=True)


def show_system_status():
    """Mostrar estado actual del sistema"""
    print("📊 ESTADO DEL SISTEMA - TRADING SYSTEM V4.0")
    print("=" * 70)
    
    try:
        # Verificar componentes
        print("\n🔧 COMPONENTES:")
        
        # 🆕 V4.0: Incluir Position Manager
        pm_version = get_version_info()
        
        components = {
            'Scanner': True,
            'Telegram Bot': True,
            'Exit Manager': True,
            f"Position Manager {pm_version['version']}": True,  # 🆕 V4.0
            'Dynamic Monitor': DYNAMIC_MONITOR_AVAILABLE,
            'Continuous Collector': True,
            'Gap Detector': True,
            'Data Validator': True,
        }
        
        for name, available in components.items():
            status = "✅" if available else "❌"
            print(f"   {status} {name}")
        
        # 🆕 V4.0: Estado de Position Manager
        print(f"\n🎯 POSITION MANAGER:")
        print(f"   Version: {pm_version['version']}")
        print(f"   Status: {pm_version['status']}")
        for component, status in pm_version['components'].items():
            print(f"   • {component}: {status}")
        
        # Verificar configuración
        print("\n⚙️ CONFIGURACIÓN:")
        print(f"   Extended Hours: {'✅' if config.is_extended_hours_enabled() else '❌'}")
        print(f"   Modo desarrollo: {'✅' if config.DEVELOPMENT_MODE else '❌'}")
        print(f"   Símbolos: {len(config.SYMBOLS)}")
        print(f"   Intervalo scan: {config.SCAN_INTERVAL} min")
        print(f"   Riesgo/trade: {config.RISK_PER_TRADE}%")
        
        # Horarios
        print("\n⏰ HORARIOS:")
        now = datetime.now(pytz.timezone(config.MARKET_TIMEZONE))
        print(f"   Hora actual: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        
        if config.is_extended_hours_enabled():
            session_name, session_config = config.get_current_trading_session()
            if session_name:
                print(f"   Sesión actual: {session_name}")
                print(f"   Descripción: {session_config.get('DESCRIPTION', 'N/A')}")
            else:
                print(f"   Sesión actual: Ninguna")
        
        # Base de datos
        print("\n🗄️ BASE DE DATOS:")
        try:
            from database.connection import get_connection
            conn = get_connection()
            if conn:
                cursor = conn.cursor()
                
                cursor.execute("SELECT COUNT(*) FROM indicators_data")
                indicators_count = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM signals_sent")
                signals_count = cursor.fetchone()[0]
                
                # 🆕 V4.0: Contar registros de position_executions
                try:
                    cursor.execute("SELECT COUNT(*) FROM position_executions")
                    executions_count = cursor.fetchone()[0]
                    print(f"   ✅ Conectada")
                    print(f"   Indicators: {indicators_count:,} registros")
                    print(f"   Signals: {signals_count:,} registros")
                    print(f"   Position Executions: {executions_count:,} registros")
                except:
                    print(f"   ✅ Conectada")
                    print(f"   Indicators: {indicators_count:,} registros")
                    print(f"   Signals: {signals_count:,} registros")
                    print(f"   Position Executions: Tabla no creada")
                
                conn.close()
            else:
                print(f"   ❌ No conectada")
        except Exception as e:
            print(f"   ❌ Error: {e}")
        
        print(f"\n✅ Estado verificado")
        
    except Exception as e:
        print(f"❌ Error verificando estado: {e}")
        logger.error(f"Error en system status: {e}", exc_info=True)


# =============================================================================
# 🚀 FUNCIÓN PRINCIPAL Y CLI
# =============================================================================

def main():
    """Función principal con interfaz CLI mejorada"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='🚀 Smart Trading System V4.0 - Con Position Manager',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos de uso:
  python main_v4.py                      # Modo interactivo
  python main_v4.py --auto               # Trading automático
  python main_v4.py --scan               # Escaneo único
  python main_v4.py --status             # Estado del sistema
  python main_v4.py --positions          # Estado de posiciones (NUEVO V4.0)
  python main_v4.py --validate           # Validar datos
  python main_v4.py --gaps               # Analizar gaps
  python main_v4.py --test-collector     # Test collector
        """
    )
    
    parser.add_argument('--auto', action='store_true',
                       help='Iniciar trading automático')
    parser.add_argument('--scan', action='store_true',
                       help='Ejecutar escaneo único')
    parser.add_argument('--status', action='store_true',
                       help='Mostrar estado del sistema')
    parser.add_argument('--positions', action='store_true',
                       help='🆕 V4.0: Mostrar estado de posiciones activas')
    parser.add_argument('--validate', action='store_true',
                       help='Validar calidad de datos')
    parser.add_argument('--gaps', action='store_true',
                       help='Analizar gaps en datos')
    parser.add_argument('--test-collector', action='store_true',
                       help='Test del continuous collector')
    
    args = parser.parse_args()
    
    # Ejecutar según argumentos
    try:
        if args.auto:
            # Trading automático
            system = TradingSystemV40()
            
            if system.start_system():
                try:
                    while system.running:
                        time.sleep(1)
                except KeyboardInterrupt:
                    logger.info("📡 Interrupción de usuario")
                finally:
                    system.stop_system()
            else:
                logger.error("❌ No se pudo iniciar el sistema")
                return 1
        
        elif args.scan:
            run_single_scan()
        
        elif args.status:
            show_system_status()
        
        elif args.positions:
            run_position_status()
        
        elif args.validate:
            run_data_validation()
        
        elif args.gaps:
            run_gap_analysis()
        
        elif args.test_collector:
            run_collector_test()
        
        else:
            # Modo interactivo
            run_interactive_mode()
        
        return 0
        
    except KeyboardInterrupt:
        print("\n👋 Programa interrumpido por el usuario")
        return 0
    except Exception as e:
        logger.error(f"❌ Error en programa principal: {e}", exc_info=True)
        return 1


def run_interactive_mode():
    """Modo interactivo con menú"""
    while True:
        print("\n" + "=" * 70)
        print("🚀 SMART TRADING SYSTEM V4.0 - MENÚ PRINCIPAL")
        print("=" * 70)
        print("\n📋 OPCIONES:")
        print("1. 🚀 Iniciar trading automático")
        print("2. 🔍 Escaneo único de mercado")
        print("3. 📊 Estado del sistema")
        print("4. 🎯 Estado de posiciones (NUEVO V4.0)")
        print("5. ✅ Validar calidad de datos")
        print("6. 🔧 Analizar gaps en datos")
        print("7. 🕐 Test continuous collector")
        print("8. 📖 Ayuda y documentación")
        print("0. 🚪 Salir")
        
        try:
            choice = input("\n👉 Elige una opción (0-8): ").strip()
            
            if choice == '0':
                print("👋 ¡Hasta pronto!")
                break
            
            elif choice == '1':
                print("\n🚀 Iniciando trading automático...")
                print("⚠️ Presiona Ctrl+C para detener")
                time.sleep(2)
                
                system = TradingSystemV40()
                
                if system.start_system():
                    try:
                        while system.running:
                            time.sleep(1)
                    except KeyboardInterrupt:
                        print("\n📡 Deteniendo sistema...")
                    finally:
                        system.stop_system()
                else:
                    print("❌ No se pudo iniciar el sistema")
                
                input("\n📱 Presiona Enter para continuar...")
            
            elif choice == '2':
                run_single_scan()
                input("\n📱 Presiona Enter para continuar...")
            
            elif choice == '3':
                show_system_status()
                input("\n📱 Presiona Enter para continuar...")
            
            elif choice == '4':
                run_position_status()
                input("\n📱 Presiona Enter para continuar...")
            
            elif choice == '5':
                run_data_validation()
                input("\n📱 Presiona Enter para continuar...")
            
            elif choice == '6':
                run_gap_analysis()
                input("\n📱 Presiona Enter para continuar...")
            
            elif choice == '7':
                run_collector_test()
                input("\n📱 Presiona Enter para continuar...")
            
            elif choice == '8':
                show_help()
                input("\n📱 Presiona Enter para continuar...")
            
            else:
                print("❌ Opción no válida")
                time.sleep(1)
        
        except (KeyboardInterrupt, EOFError):
            print("\n👋 Saliendo...")
            break
        except Exception as e:
            print(f"❌ Error: {e}")
            logger.error(f"Error en modo interactivo: {e}", exc_info=True)


def show_help():
    """Mostrar ayuda detallada"""
    print("\n📖 AYUDA - TRADING SYSTEM V4.0")
    print("=" * 70)
    
    print("\n🎯 CARACTERÍSTICAS V4.0:")
    print("• ✅ Position Manager: Tracking completo de posiciones")
    print("• ✅ Execution Monitor: Detección automática de ejecuciones")
    print("• ✅ Signal Coordinator: Prevención inteligente de spam")
    print("• ✅ NO más señales redundantes cada 15 minutos")
    print("• ✅ Seguimiento granular de entradas/salidas escalonadas")
    print("• ✅ Ajuste automático de niveles basado en ejecuciones")
    
    print("\n✨ MEJORAS VS V3.1:")
    print("• NO más spam de señales (30min mínimo entre updates)")
    print("• Detección automática cuando se ejecutan niveles")
    print("• Mensajes Telegram con estado de ejecución en tiempo real")
    print("• Base de datos con tracking granular (position_executions)")
    print("• Estadísticas mejoradas (spam prevention, ejecuciones, etc)")
    
    print("\n🔧 COMPONENTES:")
    print("• Scanner: Detección de señales de trading")
    print("• Position Manager: Gestión inteligente de posiciones")
    print("  ├─ Position Tracker: Estado de posiciones")
    print("  ├─ Execution Monitor: Detección de ejecuciones")
    print("  └─ Signal Coordinator: Coordinación de señales")
    print("• Telegram Bot: Alertas en tiempo real")
    print("• Exit Manager: Gestión automática de salidas")
    print("• Continuous Collector: Recolección 24/5 de datos")
    print("• Gap Detector: Análisis y relleno de gaps")
    print("• Data Validator: Validación de calidad de datos")
    
    print("\n🚀 FLUJO DE TRABAJO V4.0:")
    print("1. Scanner detecta señal → Coordinator evalúa")
    print("2. ¿Posición nueva? → Crear y enviar alerta")
    print("3. ¿Posición existe? → Evaluar si actualizar (anti-spam)")
    print("4. Monitor vigila precios cada 5min")
    print("5. ¿Nivel ejecutado? → Notificar automáticamente")
    print("6. Tracking granular en BD (position_executions)")
    
    print("\n💡 CONSEJOS:")
    print("• El sistema es selectivo: pocas señales, alta calidad")
    print("• Position Manager previene spam automáticamente")
    print("• Monitoreo cada 5min detecta ejecuciones automáticamente")
    print("• Revisar logs en logs/trading_system.log")
    print("• Usar --positions para ver estado de posiciones activas")
    
    print("\n🆘 SOLUCIÓN DE PROBLEMAS:")
    print("• Sin señales: Normal, el sistema es muy selectivo")
    print("• Spam de mensajes: No debería ocurrir con V4.0")
    print("• Verificar estado: python main_v4.py --status")
    print("• Ver posiciones: python main_v4.py --positions")


# =============================================================================
# 🎬 ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except Exception as e:
        logger.error(f"❌ Error fatal: {e}", exc_info=True)
        sys.exit(1)