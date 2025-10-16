#!/usr/bin/env python3
"""
🚀 MAIN.PY V3.1 - SISTEMA DE TRADING CON EXTENDED HOURS + CONTINUOUS DATA
=========================================================================

🆕 V3.1 NUEVAS FUNCIONALIDADES:
- Integración con ContinuousDataCollector para recolección 24/5
- Soporte completo para Extended Hours (pre/post/overnight)
- Gap detection y auto-filling en paralelo
- Horarios ampliados según configuración
- Dual mode: Collection + Scanning en paralelo

🎯 COMPONENTES INTEGRADOS:
- Scanner: Detección de señales de trading
- TelegramBot: Alertas en tiempo real
- ExitManager: Gestión de salidas automática
- DynamicMonitor: Monitoreo dinámico V2.3
- ContinuousCollector: Recolección 24/5 (NUEVO)
- GapDetector: Detección y análisis de gaps (NUEVO)

⏰ OPERACIÓN:
- Horarios configurables por sesión (config.EXTENDED_TRADING_SESSIONS)
- Collection continua según intervalos dinámicos
- Scanning en horarios definidos (TRADING_SESSIONS)
- Mantenimiento automático de gaps
- Shutdown graceful con save de estado
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
    
    # 🆕 V3.1: Nuevos componentes para extended hours
    from continuous_collector import ContinuousDataCollector, CollectionStatus
    from gap_detector import GapDetector
    from data_validator import DataValidator, ValidationLevel
    
    # Position Management V3.0 (si está disponible)
    try:
        from dynamic_monitor import DynamicMonitor
        DYNAMIC_MONITOR_AVAILABLE = True
    except ImportError:
        DYNAMIC_MONITOR_AVAILABLE = False
        logging.warning("⚠️ Dynamic Monitor no disponible")
    
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

class TradingSystemV31:
    """
    Sistema principal de trading con Extended Hours y Continuous Collection
    """
    
    def __init__(self):
        """Inicializar sistema completo V3.1"""
        logger.info("🚀 Inicializando Trading System V3.1...")
        
        # Componentes principales (existentes)
        self.scanner = SignalScanner()
        self.telegram = TelegramBot()
        # 🔧 FIX: ExitManager no acepta telegram_bot en constructor
        self.exit_manager = ExitManager()
        
        # 🆕 V3.1: Componentes nuevos para extended hours
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
        self.collector_thread = None
        
        # Estadísticas
        self.stats = {
            'system_start': None,
            'total_scans': 0,
            'signals_generated': 0,
            'data_collections': 0,
            'gaps_detected': 0,
            'gaps_filled': 0
        }
        
        # 🆕 V3.1: Inicializar componentes extended hours
        self._initialize_extended_hours_components()
        
        # Signal handlers para shutdown graceful
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        logger.info("✅ Trading System V3.1 inicializado")
    
    def _initialize_extended_hours_components(self):
        """🆕 V3.1: Inicializar componentes de extended hours"""
        try:
            # Verificar si extended hours está habilitado
            if not config.is_extended_hours_enabled():
                logger.info("ℹ️ Extended hours deshabilitado en config")
                return
            
            logger.info("🕐 Inicializando componentes Extended Hours...")
            
            # 1. Gap Detector
            try:
                self.gap_detector = GapDetector()
                logger.info("✅ Gap Detector inicializado")
            except Exception as e:
                logger.warning(f"⚠️ Gap Detector no disponible: {e}")
            
            # 2. Data Validator
            try:
                self.data_validator = DataValidator()
                logger.info("✅ Data Validator inicializado")
            except Exception as e:
                logger.warning(f"⚠️ Data Validator no disponible: {e}")
            
            # 3. Continuous Collector
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
        """
        🆕 V3.1: Verificar horarios de mercado con soporte extended hours
        
        Si extended hours está habilitado, retorna True en más horarios.
        Si no, usa lógica tradicional.
        """
        try:
            # En modo desarrollo, siempre abierto
            if getattr(config, 'DEVELOPMENT_MODE', False):
                return True
            
            now = datetime.now(self.market_tz)
            current_time = now.time()
            weekday = now.weekday()
            
            # Verificar día de semana (0=Lunes, 4=Viernes)
            if weekday not in config.ALLOWED_WEEKDAYS:
                return False
            
            # 🆕 V3.1: Si extended hours habilitado, verificar sesiones extendidas
            if config.is_extended_hours_enabled():
                # Obtener sesión actual
                session_name, session_config = config.get_current_trading_session()
                
                if session_name and session_config and session_config.get('ENABLED', False):
                    logger.debug(f"🕐 En sesión: {session_name}")
                    return True
                
                # Si no hay sesión activa pero es día laborable, considerar abierto
                # (para permitir collection en horarios intermedios)
                return True
            
            # Lógica tradicional (solo TRADING_SESSIONS regulares)
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
            return True  # Default a True para no bloquear
    
    def should_run_scanner_now(self) -> bool:
        """
        🆕 V3.1: Determinar si debe ejecutar scanner ahora
        
        Scanner solo se ejecuta en horarios TRADING_SESSIONS (no extended)
        """
        try:
            if getattr(config, 'DEVELOPMENT_MODE', False):
                return True
            
            now = datetime.now(self.market_tz)
            current_time = now.time()
            weekday = now.weekday()
            
            if weekday not in config.ALLOWED_WEEKDAYS:
                return False
            
            # Usar TRADING_SESSIONS tradicionales para scanner
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
        """Ejecutar escaneo de señales (lógica existente)"""
        try:
            logger.info("🔍 Ejecutando escaneo de mercado...")
            
            # Escanear símbolos configurados
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
        """Procesar y enviar señales (lógica existente mejorada)"""
        try:
            if not signals:
                return
            
            for signal in signals:
                try:
                    # Enviar alerta por Telegram
                    success = self.telegram.send_signal_alert(signal)
                    
                    if success:
                        logger.info(f"📱 Señal {signal.symbol} enviada por Telegram")
                    else:
                        logger.warning(f"⚠️ No se pudo enviar señal {signal.symbol}")
                    
                    # Si exit manager está disponible, registrar posición
                    if self.exit_manager:
                        try:
                            self.exit_manager.add_position_from_signal(signal)
                            logger.info(f"📊 Posición {signal.symbol} registrada en Exit Manager")
                        except Exception as e:
                            logger.error(f"❌ Error registrando posición {signal.symbol}: {e}")
                    
                    time.sleep(1)  # Delay entre envíos
                    
                except Exception as e:
                    logger.error(f"❌ Error procesando señal {signal.symbol}: {e}")
            
        except Exception as e:
            logger.error(f"❌ Error procesando señales: {e}")
    
    def evaluate_exits(self) -> None:
        """Evaluar salidas de posiciones abiertas (lógica existente)"""
        try:
            if not self.exit_manager:
                return
            
            logger.debug("🎯 Evaluando salidas...")
            exit_signals = self.exit_manager.evaluate_all_positions()
            
            if exit_signals:
                logger.info(f"🚨 {len(exit_signals)} alertas de exit generadas")
                
                for exit_signal in exit_signals:
                    try:
                        # Enviar alerta
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
        """
        🆕 V3.1: Loop principal del scanner (separado de collection)
        
        Se ejecuta solo en horarios TRADING_SESSIONS
        """
        try:
            logger.info("🔍 Scanner loop iniciado")
            
            last_scan = datetime.now()
            scan_interval = timedelta(minutes=config.SCAN_INTERVAL)
            
            while self.running and not self.shutdown_event.is_set():
                
                # 1. Verificar si debe ejecutar scanner
                if not self.should_run_scanner_now():
                    logger.debug("💤 Fuera de horarios de scanner, esperando...")
                    if self.shutdown_event.wait(60):  # Check cada minuto
                        break
                    continue
                
                # 2. ¿Toca escaneo?
                now = datetime.now()
                if now - last_scan >= scan_interval:
                    
                    # Escanear señales
                    signals = self.perform_scan()
                    
                    if not self.running:
                        break
                    
                    # Procesar señales
                    if signals:
                        self.process_signals(signals)
                    
                    # Evaluar exits
                    self.evaluate_exits()
                    
                    last_scan = now
                
                # 3. Sleep con verificación de shutdown
                if self.shutdown_event.wait(30):  # Check cada 30s
                    break
            
        except Exception as e:
            logger.error(f"❌ Error en scanner loop: {e}")
        finally:
            logger.info("🏁 Scanner loop finalizado")
    
    def run_maintenance_tasks(self) -> None:
        """
        🆕 V3.1: Tareas de mantenimiento periódicas
        
        - Limpieza de BD
        - Análisis de gaps
        - Validación de datos
        """
        try:
            logger.info("🔧 Ejecutando tareas de mantenimiento...")
            
            # 1. Gap maintenance
            if self.continuous_collector:
                try:
                    maintenance_result = self.continuous_collector.perform_gap_maintenance()
                    
                    if maintenance_result.get('success'):
                        logger.info(f"✅ Gap maintenance: {maintenance_result['gaps_filled']} gaps rellenados")
                        self.stats['gaps_detected'] += maintenance_result.get('total_gaps_found', 0)
                        self.stats['gaps_filled'] += maintenance_result.get('gaps_filled', 0)
                    
                except Exception as e:
                    logger.error(f"❌ Error en gap maintenance: {e}")
            
            # 2. Validación de datos (si está disponible)
            if self.data_validator:
                try:
                    # Validar símbolos principales
                    for symbol in config.SYMBOLS[:3]:  # Top 3
                        report = self.data_validator.validate_symbol_data(
                            symbol,
                            validation_level=ValidationLevel.BASIC,
                            days_back=7
                        )
                        
                        if report.needs_attention:
                            logger.warning(f"⚠️ {symbol}: Requiere atención - Score {report.overall_score:.1f}")
                        
                except Exception as e:
                    logger.error(f"❌ Error en validación de datos: {e}")
            
            # 3. Limpiar logs antiguos si es necesario
            # (implementar según necesidad)
            
            logger.info("✅ Mantenimiento completado")
            
        except Exception as e:
            logger.error(f"❌ Error en maintenance tasks: {e}")
    
    def start_system(self) -> bool:
        """Iniciar sistema completo V3.1"""
        try:
            if self.running:
                logger.warning("⚠️ Sistema ya está ejecutándose")
                return False
            
            logger.info("=" * 70)
            logger.info("🚀 INICIANDO SMART TRADING SYSTEM V3.1")
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
            
            # 🆕 V3.1: Iniciar Continuous Collector si está disponible
            if self.continuous_collector and config.is_extended_hours_enabled():
                logger.info("🕐 Iniciando Continuous Data Collector...")
                collector_success = self.continuous_collector.start_collection()  # ✅ MÉTODO CORRECTO
                
                if collector_success:
                    logger.info("✅ Continuous Collector operacional")
                else:
                    logger.warning("⚠️ Continuous Collector falló, continuando sin él")
            
            # Iniciar Dynamic Monitor si está disponible
            if self.dynamic_monitor:
                logger.info("🎯 Iniciando Dynamic Monitor...")
                monitor_success = self.dynamic_monitor.start_monitoring()
                
                if monitor_success:
                    logger.info("✅ Dynamic Monitor operacional")
                else:
                    logger.warning("⚠️ Dynamic Monitor falló")
            
            # Iniciar thread del scanner
            self.scan_thread = threading.Thread(
                target=self.run_scanner_loop,
                daemon=True,
                name="ScannerLoop"
            )
            self.scan_thread.start()
            
            # Programar maintenance tasks periódicas (cada 6 horas)
            self._schedule_maintenance_tasks()
            
            logger.info("✅ Smart Trading System V3.1 iniciado correctamente")
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
            maintenance_interval = timedelta(hours=6)  # Cada 6 horas
            
            while self.running and not self.shutdown_event.is_set():
                now = datetime.now()
                
                if now - last_maintenance >= maintenance_interval:
                    self.run_maintenance_tasks()
                    last_maintenance = now
                
                # Check cada 30 minutos
                if self.shutdown_event.wait(1800):
                    break
        
        maintenance_thread = threading.Thread(
            target=maintenance_worker,
            daemon=True,
            name="MaintenanceWorker"
        )
        maintenance_thread.start()
    
    def stop_system(self) -> None:
        """Detener sistema completo V3.1"""
        try:
            logger.info("🛑 Deteniendo Smart Trading System V3.1...")
            
            self.running = False
            self.shutdown_event.set()
            
            # 1. Detener Continuous Collector
            if self.continuous_collector:
                logger.info("🕐 Deteniendo Continuous Collector...")
                self.continuous_collector.stop_collection()  # ✅ MÉTODO CORRECTO
            
            # 2. Detener Dynamic Monitor
            if self.dynamic_monitor:
                logger.info("🎯 Deteniendo Dynamic Monitor...")
                self.dynamic_monitor.stop_monitoring()
            
            # 3. Esperar thread del scanner
            if self.scan_thread and self.scan_thread.is_alive():
                logger.info("⏳ Esperando scanner thread...")
                self.scan_thread.join(timeout=15)
            
            # 4. Guardar posiciones
            try:
                if self.exit_manager:
                    self.exit_manager.save_positions()
                    logger.info("💾 Posiciones guardadas")
            except Exception as e:
                logger.error(f"❌ Error guardando posiciones: {e}")
            
            # 5. Mostrar estadísticas finales
            self._log_final_statistics()
            
            # 6. Enviar mensaje de cierre
            try:
                uptime = datetime.now() - self.stats['system_start']
                self.telegram.send_message(
                    f"🛑 <b>Sistema Detenido</b>\n\n"
                    f"⏱️ Uptime: {uptime}\n"
                    f"🔍 Escaneos: {self.stats['total_scans']}\n"
                    f"📊 Señales: {self.stats['signals_generated']}\n"
                    f"🕐 Collections: {self.stats['data_collections']}\n"
                    f"🔧 Gaps rellenados: {self.stats['gaps_filled']}"
                )
            except:
                pass
            
            logger.info("✅ Sistema detenido correctamente")
            
        except Exception as e:
            logger.error(f"❌ Error deteniendo sistema: {e}")
    
    def _send_startup_message(self) -> None:
        """Enviar mensaje de inicio por Telegram"""
        try:
            now = datetime.now(self.market_tz)
            
            # Determinar sesión actual
            session_info = "N/A"
            if config.is_extended_hours_enabled():
                session_name, session_config = config.get_current_trading_session()
                if session_name:
                    session_info = f"{session_name} ({session_config.get('DESCRIPTION', 'N/A')})"
            
            message = (
                f"🚀 <b>Trading System V3.1 Iniciado</b>\n\n"
                f"⏰ Hora: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}\n"
                f"🕐 Extended Hours: {'✅ Activo' if config.is_extended_hours_enabled() else '❌ Desactivado'}\n"
                f"📊 Sesión actual: {session_info}\n"
                f"🎯 Símbolos: {len(config.SYMBOLS)}\n"
                f"🔍 Intervalo scan: {config.SCAN_INTERVAL} min\n\n"
                f"💰 Riesgo/trade: {config.RISK_PER_TRADE}%\n"
                f"🤖 Modo: {'🧪 Desarrollo' if config.DEVELOPMENT_MODE else '🚀 Producción'}"
            )
            
            self.telegram.send_message(message)
            
        except Exception as e:
            logger.error(f"❌ Error enviando mensaje de inicio: {e}")
    
    def _log_system_configuration(self) -> None:
        """Mostrar configuración del sistema"""
        logger.info("=" * 70)
        logger.info("⚙️ CONFIGURACIÓN DEL SISTEMA V3.1")
        logger.info("=" * 70)
        logger.info(f"📊 Símbolos monitoreados: {len(config.SYMBOLS)}")
        logger.info(f"⏰ Intervalo de escaneo: {config.SCAN_INTERVAL} minutos")
        logger.info(f"💰 Riesgo por operación: {config.RISK_PER_TRADE}%")
        logger.info(f"🕐 Extended Hours: {'✅ Habilitado' if config.is_extended_hours_enabled() else '❌ Deshabilitado'}")
        logger.info(f"🤖 Modo desarrollo: {'✅ Sí' if config.DEVELOPMENT_MODE else '❌ No'}")
        logger.info(f"📱 Telegram: {'✅ OK' if self.telegram.initialized else '❌ Error'}")
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
        
        logger.info("=" * 70)
        logger.info("📊 ESTADÍSTICAS FINALES")
        logger.info("=" * 70)
        logger.info(f"⏱️ Uptime: {uptime}")
        logger.info(f"🔍 Total escaneos: {self.stats['total_scans']}")
        logger.info(f"📊 Señales generadas: {self.stats['signals_generated']}")
        logger.info(f"🕐 Data collections: {self.stats['data_collections']}")
        logger.info(f"🔧 Gaps detectados: {self.stats['gaps_detected']}")
        logger.info(f"✅ Gaps rellenados: {self.stats['gaps_filled']}")
        logger.info("=" * 70)


# =============================================================================
# 🎯 FUNCIONES DE UTILIDAD
# =============================================================================

def run_single_scan():
    """Ejecutar un escaneo único sin loop continuo"""
    print("🔍 ESCANEO ÚNICO - TRADING SYSTEM V3.1")
    print("=" * 70)
    
    try:
        # Inicializar componentes necesarios
        scanner = SignalScanner()
        telegram = TelegramBot()
        
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
                    for signal in signals:
                        telegram.send_signal_alert(signal)
                        time.sleep(1)
                    print("✅ Alertas enviadas")
        else:
            print("   ℹ️ No hay señales válidas en este momento")
            print("   💡 El sistema es muy selectivo - esto es normal")
        
        print(f"\n✅ Escaneo completado")
        
    except Exception as e:
        print(f"❌ Error en escaneo: {e}")
        logger.error(f"Error en single scan: {e}", exc_info=True)


def run_data_validation():
    """🆕 V3.1: Ejecutar validación de datos históricos"""
    print("🔍 VALIDACIÓN DE DATOS - TRADING SYSTEM V3.1")
    print("=" * 70)
    
    try:
        # Inicializar data validator
        validator = DataValidator()
        
        # Validar símbolos principales
        print(f"\n📊 Validando {len(config.SYMBOLS[:5])} símbolos principales...")
        
        for symbol in config.SYMBOLS[:5]:
            print(f"\n🎯 {symbol}:")
            
            # 🔧 FIX: Usar firma correcta de validate_symbol
            report = validator.validate_symbol(
                symbol=symbol,
                days_back=30
            )
            
            print(f"   Score: {report.overall_score:.1f}/100")
            print(f"   Status: {report.overall_status.value}")
            
            # 🔧 FIX: Usar critical_issues en lugar de issues
            if report.critical_issues:
                print(f"   🚨 Issues críticos: {len(report.critical_issues)}")
                for issue in report.critical_issues[:3]:  # Mostrar top 3
                    print(f"      • {issue}")
            
            # 🔧 NUEVO: Mostrar warnings también
            if report.warnings:
                print(f"   ⚠️ Warnings: {len(report.warnings)}")
                for warning in report.warnings[:2]:
                    print(f"      • {warning}")
            
            if report.recommendations:
                print(f"   💡 Recomendaciones:")
                for rec in report.recommendations[:2]:
                    print(f"      • {rec}")
        
        print(f"\n✅ Validación completada")
        
    except Exception as e:
        print(f"❌ Error en validación: {e}")
        logger.error(f"Error en data validation: {e}", exc_info=True)



def run_gap_analysis():
    """🆕 V3.1: Ejecutar análisis de gaps en datos"""
    print("🔧 ANÁLISIS DE GAPS - TRADING SYSTEM V3.1")
    print("=" * 70)
    
    try:
        # Inicializar gap detector
        gap_detector = GapDetector()
        
        print(f"\n📊 Analizando gaps en {len(config.SYMBOLS[:3])} símbolos...")
        
        total_gaps = 0
        total_fillable = 0
        
        for symbol in config.SYMBOLS[:3]:
            print(f"\n🎯 {symbol}:")
            
            # Obtener datos recientes
            from indicators import TechnicalIndicators
            indicators = TechnicalIndicators()
            data = indicators.get_all_indicators(symbol)
            
            if 'market_data' in data and not data['market_data'].empty:
                # Generar reporte de calidad
                report = gap_detector.analyze_data_quality(
                    data['market_data'],
                    symbol,
                    expected_interval_minutes=15
                )
                
                print(f"   Gaps detectados: {report.total_gaps}")
                
                # 🔧 FIX: Calcular fillable_gaps manualmente
                fillable_gaps = len([
                    gap for gap in report.gaps_detected 
                    if hasattr(gap, 'is_fillable') and gap.is_fillable
                ])
                
                print(f"   Gaps rellenables: {fillable_gaps}")
                print(f"   Completitud: {report.completeness_pct:.1f}%")
                
                # 🔧 FIX: Usar overall_quality_score en lugar de quality_score
                print(f"   Score calidad: {report.overall_quality_score:.1f}/100")
                
                total_gaps += report.total_gaps
                total_fillable += fillable_gaps
                
                # Mostrar gaps críticos
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
    """🆕 V3.1: Test del continuous collector"""
    print("🕐 TEST CONTINUOUS COLLECTOR - TRADING SYSTEM V3.1")
    print("=" * 70)
    
    try:
        # Inicializar collector
        collector = ContinuousDataCollector()
        
        print(f"📊 Collector configurado:")
        print(f"   Símbolos: {len(collector.symbols)}")
        print(f"   Sesiones: {len(collector.sessions)}")
        print(f"   Status: {collector.status.value}")
        
        # Mostrar sesiones
        print(f"\n🕐 Sesiones configuradas:")
        for session in collector.sessions:
            enabled = "✅" if session.enabled else "❌"
            print(f"   {enabled} {session.name}: {session.start_time}-{session.end_time} "
                  f"(cada {session.interval_minutes}min)")
        
        # Test recolección forzada
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
    print("📊 ESTADO DEL SISTEMA - TRADING SYSTEM V3.1")
    print("=" * 70)
    
    try:
        # Verificar componentes
        print("\n🔧 COMPONENTES:")
        
        components = {
            'Scanner': True,
            'Telegram Bot': True,
            'Exit Manager': True,
            'Dynamic Monitor': DYNAMIC_MONITOR_AVAILABLE,
            'Continuous Collector': True,
            'Gap Detector': True,
            'Data Validator': True,
        }
        
        for name, available in components.items():
            status = "✅" if available else "❌"
            print(f"   {status} {name}")
        
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
                
                # Contar registros
                cursor.execute("SELECT COUNT(*) FROM indicators_data")
                indicators_count = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM signals_sent")
                signals_count = cursor.fetchone()[0]
                
                print(f"   ✅ Conectada")
                print(f"   Indicators: {indicators_count:,} registros")
                print(f"   Signals: {signals_count:,} registros")
                
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
        description='🚀 Smart Trading System V3.1 - Extended Hours',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos de uso:
  python main.py                      # Modo interactivo
  python main.py --auto               # Trading automático
  python main.py --scan               # Escaneo único
  python main.py --status             # Estado del sistema
  python main.py --validate           # Validar datos
  python main.py --gaps               # Analizar gaps
  python main.py --test-collector     # Test collector
        """
    )
    
    parser.add_argument('--auto', action='store_true',
                       help='Iniciar trading automático')
    parser.add_argument('--scan', action='store_true',
                       help='Ejecutar escaneo único')
    parser.add_argument('--status', action='store_true',
                       help='Mostrar estado del sistema')
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
            system = TradingSystemV31()
            
            if system.start_system():
                # Mantener sistema ejecutándose
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
        print("🚀 SMART TRADING SYSTEM V3.1 - MENÚ PRINCIPAL")
        print("=" * 70)
        print("\n📋 OPCIONES:")
        print("1. 🚀 Iniciar trading automático")
        print("2. 🔍 Escaneo único de mercado")
        print("3. 📊 Estado del sistema")
        print("4. ✅ Validar calidad de datos")
        print("5. 🔧 Analizar gaps en datos")
        print("6. 🕐 Test continuous collector")
        print("7. 📖 Ayuda y documentación")
        print("0. 🚪 Salir")
        
        try:
            choice = input("\n👉 Elige una opción (0-7): ").strip()
            
            if choice == '0':
                print("👋 ¡Hasta pronto!")
                break
            
            elif choice == '1':
                print("\n🚀 Iniciando trading automático...")
                print("⚠️ Presiona Ctrl+C para detener")
                time.sleep(2)
                
                system = TradingSystemV31()
                
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
                run_data_validation()
                input("\n📱 Presiona Enter para continuar...")
            
            elif choice == '5':
                run_gap_analysis()
                input("\n📱 Presiona Enter para continuar...")
            
            elif choice == '6':
                run_collector_test()
                input("\n📱 Presiona Enter para continuar...")
            
            elif choice == '7':
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
    print("\n📖 AYUDA - TRADING SYSTEM V3.1")
    print("=" * 70)
    
    print("\n🎯 CARACTERÍSTICAS V3.1:")
    print("• ✅ Extended Hours: Monitoreo 24/5 (pre/post/overnight)")
    print("• ✅ Continuous Collection: Recolección automática de datos")
    print("• ✅ Gap Detection: Detección y relleno automático de gaps")
    print("• ✅ Data Validation: Validación de calidad para backtesting")
    print("• ✅ Dynamic Monitor: Monitoreo adaptativo de posiciones")
    print("• ✅ Multi-threaded: Scanner + Collector en paralelo")
    
    print("\n🔧 COMPONENTES:")
    print("• Scanner: Detección de señales de trading")
    print("• Telegram Bot: Alertas en tiempo real")
    print("• Exit Manager: Gestión automática de salidas")
    print("• Continuous Collector: Recolección 24/5 de datos")
    print("• Gap Detector: Análisis y relleno de gaps")
    print("• Data Validator: Validación de calidad de datos")
    
    print("\n⏰ HORARIOS EXTENDED:")
    print("• PRE_MARKET: 04:00-09:30 (cada 30 min)")
    print("• MORNING: 10:00-12:00 (cada 15 min)")
    print("• AFTERNOON: 13:30-15:30 (cada 15 min)")
    print("• POST_MARKET: 16:00-20:00 (cada 30 min)")
    print("• OVERNIGHT: 20:00-04:00 (cada 2 horas)")
    
    print("\n🚀 FLUJO DE TRABAJO:")
    print("1. Configurar extended hours en config.py")
    print("2. Verificar estado: python main.py --status")
    print("3. Validar datos: python main.py --validate")
    print("4. Test collector: python main.py --test-collector")
    print("5. Escaneo único: python main.py --scan")
    print("6. Trading auto: python main.py --auto")
    
    print("\n💡 CONSEJOS:")
    print("• El continuous collector rellena gaps automáticamente")
    print("• Validar datos antes de backtesting es crítico")
    print("• Extended hours mejora la calidad de datos")
    print("• El sistema es dual: collection + scanning paralelo")
    print("• Revisar logs en logs/trading_system.log")
    
    print("\n🆘 SOLUCIÓN DE PROBLEMAS:")
    print("• Sin collector: Verificar config.CONTINUOUS_DATA_CONFIG")
    print("• Gaps excesivos: Ejecutar python main.py --gaps")
    print("• Datos incompletos: Ejecutar validación completa")
    print("• Errores de BD: Verificar database/connection.py")


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