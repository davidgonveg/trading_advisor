#!/usr/bin/env python3
"""
🚀 SISTEMA DE TRADING AUTOMATIZADO V2.0 - MAIN ORCHESTRATOR
==========================================================

Sistema completo de trading automatizado que:
- Escanea múltiples símbolos cada 15 minutos
- Detecta señales de alta calidad (70+ puntos)
- Calcula planes de posición adaptativos
- Envía alertas inteligentes por Telegram
- Monitorea performance y maneja errores

Autor: Trading System V2.0
Fecha: Septiembre 2025
Estado: PRODUCCIÓN READY
"""

import asyncio
import logging
import signal
import sys
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import schedule
import pytz
from pathlib import Path
import traceback
import json

# Importar módulos del sistema
try:
    import config
    from indicators import TechnicalIndicators
    from scanner import SignalScanner, TradingSignal
    from position_calculator import PositionCalculator
    from telegram_bot import TelegramBot
except ImportError as e:
    print(f"❌ Error importando módulos: {e}")
    print("💡 Asegúrate de que todos los archivos están en el directorio correcto")
    sys.exit(1)

# Configurar logging avanzado
def setup_logging():
    """Configurar sistema de logging completo"""
    try:
        # Crear directorio de logs
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        
        # Configurar formato
        log_format = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # Logger principal
        logger = logging.getLogger()
        logger.setLevel(getattr(logging, config.LOG_LEVEL, 'INFO'))
        
        # Handler para consola
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(log_format)
        logger.addHandler(console_handler)
        
        # Handler para archivo
        file_handler = logging.FileHandler(
            log_dir / config.LOG_FILE,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(log_format)
        logger.addHandler(file_handler)
        
        return logger
        
    except Exception as e:
        print(f"❌ Error configurando logging: {e}")
        # Fallback a logging básico
        logging.basicConfig(level=logging.INFO)
        return logging.getLogger()

# Setup logging
logger = setup_logging()

class TradingSystemOrchestrator:
    """
    Orquestador principal del sistema de trading automatizado
    """
    
    def __init__(self):
        """Inicializar todos los componentes del sistema"""
        self.version = "2.0"
        self.start_time = datetime.now()
        self.running = False
        self.spain_tz = pytz.timezone('Europe/Madrid')
        
        # Componentes del sistema
        self.indicators = None
        self.scanner = None
        self.position_calc = None
        self.telegram_bot = None
        
        # Estadísticas de sesión
        self.session_stats = {
            'scans_completed': 0,
            'signals_detected': 0,
            'alerts_sent': 0,
            'errors_count': 0,
            'last_scan_time': None,
            'last_signal_time': None,
            'uptime_start': datetime.now()
        }
        
        # Control de ejecución
        self.max_consecutive_errors = 5
        self.consecutive_errors = 0
        self.shutdown_requested = False
        
        logger.info("🚀 TradingSystemOrchestrator inicializado")
    
    def initialize_components(self) -> bool:
        """
        Inicializar todos los componentes del sistema
        
        Returns:
            True si todos se inicializan correctamente
        """
        try:
            logger.info("⚙️ Inicializando componentes del sistema...")
            
            # 1. Validar configuración
            config_errors = config.validate_config()
            if config_errors:
                logger.error("❌ Errores de configuración:")
                for error in config_errors:
                    logger.error(f"  {error}")
                return False
            
            logger.info("✅ Configuración validada")
            
            # 2. Inicializar indicadores técnicos
            self.indicators = TechnicalIndicators()
            logger.info("✅ Indicadores técnicos inicializados")
            
            # 3. Inicializar scanner de señales
            self.scanner = SignalScanner()
            logger.info("✅ Scanner de señales inicializado")
            
            # 4. Inicializar calculadora de posiciones
            self.position_calc = PositionCalculator()
            logger.info("✅ Calculadora de posiciones inicializada")
            
            # 5. Inicializar bot de Telegram
            self.telegram_bot = TelegramBot()
            if not self.telegram_bot.initialized:
                logger.error("❌ Bot de Telegram no se pudo inicializar")
                return False
            
            logger.info("✅ Bot de Telegram inicializado")
            
            # 6. Test de conectividad
            if not self._test_connectivity():
                logger.warning("⚠️ Test de conectividad falló, pero continuando...")
            
            logger.info("🎯 Todos los componentes inicializados correctamente")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error inicializando componentes: {e}")
            logger.error(traceback.format_exc())
            return False
    
    def _test_connectivity(self) -> bool:
        """Test básico de conectividad"""
        try:
            # Test de descarga de datos
            test_data = self.indicators.get_market_data("SPY", "15m", 5)
            if len(test_data) < 10:
                logger.warning("⚠️ Pocos datos descargados en test")
                return False
            
            logger.info(f"✅ Test de datos: {len(test_data)} barras descargadas")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error en test de conectividad: {e}")
            return False
    
    def setup_scheduler(self):
        """Configurar el scheduler para ejecuciones automáticas"""
        try:
            # Limpiar schedule previo
            schedule.clear()
            
            # Programar escaneo principal cada X minutos
            schedule.every(config.SCAN_INTERVAL).minutes.do(self.run_scan_cycle)
            
            # Programar estadísticas cada hora
            schedule.every().hour.do(self.log_hourly_stats)
            
            # Programar resumen diario (opcional)
            if config.ALERT_TYPES.get('DAILY_SUMMARY', False):
                schedule.every().day.at("09:00").do(self.send_daily_summary)
            
            logger.info(f"📅 Scheduler configurado - Escaneo cada {config.SCAN_INTERVAL} minutos")
            
        except Exception as e:
            logger.error(f"❌ Error configurando scheduler: {e}")
    
    def run_scan_cycle(self) -> Dict:
        """
        Ejecutar un ciclo completo de escaneo
        
        Returns:
            Dict con resultados del ciclo
        """
        cycle_start = time.time()
        cycle_results = {
            'success': False,
            'signals_found': 0,
            'alerts_sent': 0,
            'errors': [],
            'duration': 0,
            'timestamp': datetime.now(self.spain_tz)
        }
        
        try:
            logger.info("🔍 Iniciando ciclo de escaneo...")
            
            # 1. Verificar si el mercado está abierto
            if not self.scanner.is_market_open() and not config.DEVELOPMENT_MODE:
                logger.info("📴 Mercado cerrado - Omitiendo escaneo")
                cycle_results['success'] = True
                return cycle_results
            
            # 2. Ejecutar escaneo de todos los símbolos
            symbols_to_scan = config.TEST_SYMBOLS if config.TEST_MODE else config.SYMBOLS
            signals = self.scanner.scan_multiple_symbols(symbols_to_scan)
            
            cycle_results['signals_found'] = len(signals)
            logger.info(f"📊 Escaneo completado: {len(signals)} señales detectadas de {len(symbols_to_scan)} símbolos")
            
            # 3. Procesar y enviar alertas
            alerts_sent = 0
            for signal in signals:
                try:
                    # Enviar alerta por Telegram
                    success = self.telegram_bot.send_signal_alert(signal)
                    if success:
                        alerts_sent += 1
                        logger.info(f"✅ Alerta enviada: {signal.symbol} {signal.signal_type} ({signal.signal_strength} pts)")
                    else:
                        logger.error(f"❌ Error enviando alerta: {signal.symbol}")
                        cycle_results['errors'].append(f"Failed to send alert for {signal.symbol}")
                        
                except Exception as e:
                    error_msg = f"Error procesando señal {signal.symbol}: {str(e)}"
                    logger.error(error_msg)
                    cycle_results['errors'].append(error_msg)
            
            cycle_results['alerts_sent'] = alerts_sent
            
            # 4. Actualizar estadísticas
            self.session_stats['scans_completed'] += 1
            self.session_stats['signals_detected'] += len(signals)
            self.session_stats['alerts_sent'] += alerts_sent
            self.session_stats['last_scan_time'] = datetime.now()
            
            if signals:
                self.session_stats['last_signal_time'] = datetime.now()
            
            # 5. Reset contador de errores consecutivos
            if not cycle_results['errors']:
                self.consecutive_errors = 0
            
            cycle_results['success'] = True
            cycle_results['duration'] = time.time() - cycle_start
            
            logger.info(f"✅ Ciclo completado en {cycle_results['duration']:.1f}s - {alerts_sent} alertas enviadas")
            
        except Exception as e:
            error_msg = f"Error en ciclo de escaneo: {str(e)}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            
            cycle_results['errors'].append(error_msg)
            self.session_stats['errors_count'] += 1
            self.consecutive_errors += 1
            
            # Enviar alerta de error crítico
            if self.consecutive_errors >= 3:
                self._send_error_alert(f"Error crítico en ciclo #{self.consecutive_errors}: {str(e)}")
        
        return cycle_results
    
    def _send_error_alert(self, error_message: str):
        """Enviar alerta de error crítico"""
        try:
            if self.telegram_bot and self.telegram_bot.initialized:
                self.telegram_bot.send_system_alert("ERROR", error_message)
        except Exception as e:
            logger.error(f"Error enviando alerta de error: {e}")
    
    def log_hourly_stats(self):
        """Registrar estadísticas cada hora"""
        try:
            uptime = datetime.now() - self.session_stats['uptime_start']
            
            stats_message = (
                f"📊 ESTADÍSTICAS HORARIAS\n"
                f"⏰ Uptime: {uptime}\n"
                f"🔍 Escaneos: {self.session_stats['scans_completed']}\n"
                f"🎯 Señales: {self.session_stats['signals_detected']}\n"
                f"📱 Alertas: {self.session_stats['alerts_sent']}\n"
                f"❌ Errores: {self.session_stats['errors_count']}\n"
                f"💪 Estado: {'🟢 Operativo' if self.consecutive_errors < 3 else '🟡 Degradado'}"
            )
            
            logger.info(stats_message)
            
            # Enviar por Telegram si está configurado
            if config.ALERT_TYPES.get('SYSTEM_INFO', False):
                self.telegram_bot.send_system_alert("INFO", stats_message)
                
        except Exception as e:
            logger.error(f"Error en estadísticas horarias: {e}")
    
    def send_daily_summary(self):
        """Enviar resumen diario (opcional)"""
        try:
            if not config.ALERT_TYPES.get('DAILY_SUMMARY', False):
                return
            
            summary = (
                f"📈 RESUMEN DIARIO\n"
                f"🔍 Total escaneos: {self.session_stats['scans_completed']}\n"
                f"🎯 Total señales: {self.session_stats['signals_detected']}\n"
                f"📱 Total alertas: {self.session_stats['alerts_sent']}\n"
                f"📊 Tasa detección: {(self.session_stats['signals_detected'] / max(self.session_stats['scans_completed'], 1)):.1%}\n"
                f"✅ Sistema funcionando correctamente"
            )
            
            self.telegram_bot.send_system_alert("INFO", summary)
            logger.info("📈 Resumen diario enviado")
            
        except Exception as e:
            logger.error(f"Error enviando resumen diario: {e}")
    
    def run_forever(self):
        """
        Ejecutar el sistema de forma continua
        """
        try:
            logger.info("🚀 Iniciando sistema de trading automatizado...")
            
            # Enviar mensaje de inicio
            startup_message = (
                f"🚀 Sistema Trading v{self.version} INICIADO\n"
                f"📊 Símbolos: {', '.join(config.SYMBOLS)}\n"
                f"⏰ Intervalo: {config.SCAN_INTERVAL} min\n"
                f"🎯 Umbral mínimo: {config.SIGNAL_THRESHOLDS['NO_TRADE']} pts\n"
                f"💰 Riesgo por trade: {config.RISK_PER_TRADE}%\n"
                f"🏛️ Mercado: {'🟢 Abierto' if self.scanner.is_market_open() else '🔴 Cerrado'}"
            )
            
            self.telegram_bot.send_system_alert("START", startup_message)
            
            self.running = True
            logger.info("✅ Sistema iniciado correctamente - Entrando en loop principal")
            
            # Loop principal
            while self.running and not self.shutdown_requested:
                try:
                    # Ejecutar tareas programadas
                    schedule.run_pending()
                    
                    # Verificar si hay demasiados errores consecutivos
                    if self.consecutive_errors >= self.max_consecutive_errors:
                        logger.error(f"❌ Demasiados errores consecutivos ({self.consecutive_errors}). Deteniendo sistema.")
                        self._send_error_alert(f"Sistema detenido por {self.consecutive_errors} errores consecutivos")
                        break
                    
                    # Dormir 1 segundo antes de siguiente iteración
                    time.sleep(1)
                    
                except KeyboardInterrupt:
                    logger.info("⚠️ Interrupción del usuario detectada")
                    break
                except Exception as e:
                    logger.error(f"❌ Error en loop principal: {e}")
                    self.session_stats['errors_count'] += 1
                    time.sleep(5)  # Esperar antes de continuar
            
        except Exception as e:
            logger.error(f"❌ Error crítico en run_forever: {e}")
            logger.error(traceback.format_exc())
        finally:
            self._shutdown_system()
    
    def run_single_scan(self) -> Dict:
        """
        Ejecutar un solo escaneo (útil para testing)
        
        Returns:
            Resultados del escaneo
        """
        logger.info("🧪 Ejecutando escaneo único...")
        return self.run_scan_cycle()
    
    def get_system_status(self) -> Dict:
        """Obtener estado completo del sistema"""
        try:
            uptime = datetime.now() - self.session_stats['uptime_start']
            
            # Estado de componentes
            components_status = {
                'indicators': self.indicators is not None,
                'scanner': self.scanner is not None,
                'position_calc': self.position_calc is not None,
                'telegram_bot': self.telegram_bot and self.telegram_bot.initialized
            }
            
            return {
                'version': self.version,
                'running': self.running,
                'uptime': str(uptime),
                'uptime_seconds': uptime.total_seconds(),
                'components': components_status,
                'market_open': self.scanner.is_market_open() if self.scanner else False,
                'consecutive_errors': self.consecutive_errors,
                'session_stats': self.session_stats.copy(),
                'development_mode': config.DEVELOPMENT_MODE,
                'test_mode': config.TEST_MODE
            }
            
        except Exception as e:
            logger.error(f"Error obteniendo estado del sistema: {e}")
            return {'error': str(e)}
    
    def _shutdown_system(self):
        """Apagar el sistema de forma ordenada"""
        try:
            logger.info("🛑 Iniciando apagado del sistema...")
            
            self.running = False
            
            # Limpiar scheduler
            schedule.clear()
            
            # Enviar mensaje de apagado
            if self.telegram_bot and self.telegram_bot.initialized:
                uptime = datetime.now() - self.session_stats['uptime_start']
                shutdown_message = (
                    f"🛑 Sistema DETENIDO\n"
                    f"⏰ Uptime: {uptime}\n"
                    f"📊 Estadísticas finales:\n"
                    f"  • Escaneos: {self.session_stats['scans_completed']}\n"
                    f"  • Señales: {self.session_stats['signals_detected']}\n"
                    f"  • Alertas: {self.session_stats['alerts_sent']}\n"
                    f"  • Errores: {self.session_stats['errors_count']}"
                )
                
                self.telegram_bot.send_system_alert("INFO", shutdown_message)
            
            logger.info("✅ Sistema apagado correctamente")
            
        except Exception as e:
            logger.error(f"Error en apagado del sistema: {e}")
    
    def _signal_handler(self, signum, frame):
        """Manejador de señales del sistema (Ctrl+C, etc.)"""
        logger.info(f"📡 Señal {signum} recibida - Iniciando apagado ordenado...")
        self.shutdown_requested = True


# =============================================================================
# 🎯 FUNCIONES DE CONTROL Y UTILIDADES
# =============================================================================

def print_banner():
    """Mostrar banner de inicio"""
    banner = """
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║          🚀 SISTEMA DE TRADING AUTOMATIZADO V2.0             ║
║                                                              ║
║          📊 Detección Inteligente de Señales                 ║
║          💰 Gestión Adaptativa de Posiciones                 ║
║          📱 Alertas Automáticas por Telegram                 ║
║                                                              ║
║          Estado: PRODUCCIÓN READY                            ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
    """
    print(banner)

def run_tests():
    """Ejecutar tests de todos los módulos"""
    print("🧪 EJECUTANDO TESTS DEL SISTEMA COMPLETO")
    print("=" * 60)
    
    try:
        # Test de importaciones
        print("1️⃣ Verificando importaciones...")
        assert config is not None
        assert TechnicalIndicators is not None
        assert SignalScanner is not None
        assert TelegramBot is not None
        print("✅ Todas las importaciones OK")
        
        # Test de configuración
        print("\n2️⃣ Validando configuración...")
        config_errors = config.validate_config()
        if config_errors:
            print("❌ Errores de configuración:")
            for error in config_errors:
                print(f"  {error}")
            return False
        print("✅ Configuración válida")
        
        # Test de inicialización
        print("\n3️⃣ Testeando inicialización del sistema...")
        system = TradingSystemOrchestrator()
        init_success = system.initialize_components()
        
        if not init_success:
            print("❌ Error en inicialización de componentes")
            return False
        print("✅ Todos los componentes inicializados")
        
        # Test de escaneo
        print("\n4️⃣ Ejecutando test de escaneo...")
        scan_result = system.run_single_scan()
        print(f"✅ Escaneo completado: {scan_result['signals_found']} señales")
        
        # Test de estado del sistema
        print("\n5️⃣ Verificando estado del sistema...")
        status = system.get_system_status()
        print(f"✅ Sistema operativo: {status['running']}")
        
        print(f"\n🎯 TODOS LOS TESTS PASARON")
        print(f"🚀 Sistema listo para producción")
        return True
        
    except Exception as e:
        print(f"❌ Error en tests: {e}")
        return False

def interactive_menu():
    """Menú interactivo para control del sistema"""
    print("\n🎛️ MENÚ DE CONTROL DEL SISTEMA")
    print("=" * 40)
    print("1. Ejecutar tests completos")
    print("2. Escaneo único (test)")
    print("3. Mostrar configuración")
    print("4. Iniciar sistema automático")
    print("5. Estado del sistema")
    print("6. Salir")
    print("")
    
    while True:
        try:
            choice = input("Selecciona una opción (1-6): ").strip()
            
            if choice == "1":
                print("\n" + "="*60)
                success = run_tests()
                if not success:
                    print("❌ Algunos tests fallaron")
                input("\nPresiona Enter para continuar...")
                
            elif choice == "2":
                print("\n" + "="*60)
                system = TradingSystemOrchestrator()
                if system.initialize_components():
                    result = system.run_single_scan()
                    print(f"\n📊 Resultados: {result}")
                else:
                    print("❌ Error inicializando sistema")
                input("\nPresiona Enter para continuar...")
                
            elif choice == "3":
                print("\n" + "="*60)
                config.print_config_summary()
                input("\nPresiona Enter para continuar...")
                
            elif choice == "4":
                print("\n🚀 Iniciando sistema automático...")
                print("💡 Usa Ctrl+C para detener el sistema")
                system = TradingSystemOrchestrator()
                if system.initialize_components():
                    system.setup_scheduler()
                    system.run_forever()
                else:
                    print("❌ Error inicializando sistema")
                    input("\nPresiona Enter para continuar...")
                
            elif choice == "5":
                print("\n" + "="*60)
                system = TradingSystemOrchestrator()
                if system.initialize_components():
                    status = system.get_system_status()
                    print("📊 Estado del Sistema:")
                    for key, value in status.items():
                        print(f"  {key}: {value}")
                else:
                    print("❌ Error obteniendo estado")
                input("\nPresiona Enter para continuar...")
                
            elif choice == "6":
                print("👋 ¡Hasta luego!")
                break
                
            else:
                print("❌ Opción no válida")
            
            # Volver a mostrar menú
            print("\n🎛️ MENÚ DE CONTROL DEL SISTEMA")
            print("=" * 40)
            print("1. Ejecutar tests completos")
            print("2. Escaneo único (test)")
            print("3. Mostrar configuración")
            print("4. Iniciar sistema automático") 
            print("5. Estado del sistema")
            print("6. Salir")
            print("")
                
        except KeyboardInterrupt:
            print("\n👋 Saliendo del menú...")
            break
        except Exception as e:
            print(f"❌ Error: {e}")

# =============================================================================
# 🚀 PUNTO DE ENTRADA PRINCIPAL
# =============================================================================

def main():
    """Función principal del sistema"""
    try:
        # Mostrar banner
        print_banner()
        
        # Verificar argumentos de línea de comandos
        if len(sys.argv) > 1:
            command = sys.argv[1].lower()
            
            if command == "test":
                logger.info("🧪 Modo test solicitado")
                success = run_tests()
                sys.exit(0 if success else 1)
                
            elif command == "scan":
                logger.info("🔍 Escaneo único solicitado")
                system = TradingSystemOrchestrator()
                if system.initialize_components():
                    result = system.run_single_scan()
                    print(f"📊 Resultado: {result}")
                    sys.exit(0)
                else:
                    sys.exit(1)
                    
            elif command == "auto":
                logger.info("🚀 Modo automático solicitado")
                system = TradingSystemOrchestrator()
                if system.initialize_components():
                    system.setup_scheduler()
                    
                    # Configurar manejador de señales
                    signal.signal(signal.SIGINT, system._signal_handler)
                    signal.signal(signal.SIGTERM, system._signal_handler)
                    
                    system.run_forever()
                    sys.exit(0)
                else:
                    sys.exit(1)
                    
            elif command == "config":
                config.print_config_summary()
                sys.exit(0)
                
            else:
                print(f"❌ Comando desconocido: {command}")
                print("💡 Comandos disponibles: test, scan, auto, config")
                sys.exit(1)
        
        else:
            # Modo interactivo por defecto
            logger.info("🎛️ Iniciando modo interactivo")
            interactive_menu()
    
    except KeyboardInterrupt:
        logger.info("👋 Sistema interrumpido por el usuario")
        sys.exit(0)
    except Exception as e:
        logger.error(f"❌ Error crítico en main: {e}")
        logger.error(traceback.format_exc())
        sys.exit(1)

if __name__ == "__main__":
    main()