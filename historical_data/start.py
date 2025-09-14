#!/usr/bin/env python3
"""
🚀 START.PY - SISTEMA MASTER DE TRADING AUTOMATIZADO V3.0
========================================================

Punto de entrada principal que orquesta todo el ecosistema de trading:

📊 COMPONENTES INTEGRADOS:
- Scanner de señales en tiempo real
- Telegram bot para alertas
- Exit manager para gestión de posiciones  
- Backtesting engine con validación de datos
- Descarga y población de datos históricos
- Sistema de base de datos completo

🎯 MODOS DE OPERACIÓN:
1. AUTO    - Trading automático en vivo
2. SCAN    - Escaneo único de mercado
3. BACKTEST - Backtesting de estrategias
4. DATA    - Gestión de datos históricos
5. STATUS  - Estado del sistema
6. SETUP   - Configuración inicial

FILOSOFÍA: "Un comando para gobernarlos a todos"
"""

import os
import sys
import argparse
import logging
import time
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import signal
from pathlib import Path

# Configurar paths
SCRIPT_DIR = Path(__file__).parent.absolute()
sys.path.insert(0, str(SCRIPT_DIR))

# Configurar logging básico
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

class TradingSystemMaster:
    """Sistema maestro que coordina todos los componentes"""
    
    def __init__(self):
        self.components_status = {}
        self.system_health = {}
        self.shutdown_requested = False
        
        # Registrar signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        logger.info("🚀 Trading System Master inicializado")
    
    def _signal_handler(self, signum, frame):
        """Manejo graceful de señales de sistema"""
        logger.info(f"📡 Señal {signum} recibida, iniciando shutdown...")
        self.shutdown_requested = True
    
    def check_system_requirements(self) -> Dict[str, Any]:
        """Verificar que todos los componentes estén disponibles"""
        requirements = {
            'python_version': sys.version_info >= (3, 8),
            'config_available': False,
            'database_available': False,
            'scanner_available': False,
            'telegram_available': False,
            'backtest_available': False,
            'historical_data_available': False,
            'env_file_exists': False
        }
        
        try:
            # Check config
            import config
            requirements['config_available'] = True
            logger.debug("✅ Config module loaded")
        except ImportError:
            logger.error("❌ config.py not found")
        
        try:
            # Check database
            from database.connection import get_connection
            conn = get_connection()
            if conn:
                conn.close()
                requirements['database_available'] = True
                logger.debug("✅ Database connection OK")
        except Exception as e:
            logger.error(f"❌ Database error: {e}")
        
        try:
            # Check scanner
            from scanner import SignalScanner
            requirements['scanner_available'] = True
            logger.debug("✅ Scanner module OK")
        except ImportError:
            logger.error("❌ scanner.py not found")
        
        try:
            # Check telegram
            from telegram_bot import TelegramBot
            requirements['telegram_available'] = True
            logger.debug("✅ Telegram bot OK")
        except ImportError:
            logger.error("❌ telegram_bot.py not found")
        
        try:
            # Check backtest engine
            if (SCRIPT_DIR / 'historical_data' / 'backtest_engine.py').exists():
                requirements['backtest_available'] = True
                logger.debug("✅ Backtest engine OK")
        except Exception:
            logger.error("❌ Backtest engine not found")
        
        try:
            # Check historical data tools
            historical_dir = SCRIPT_DIR / 'historical_data'
            if (historical_dir / 'downloader.py').exists() and (historical_dir / 'populate_db.py').exists():
                requirements['historical_data_available'] = True
                logger.debug("✅ Historical data tools OK")
        except Exception:
            logger.error("❌ Historical data tools not found")
        
        # Check .env file
        env_file = SCRIPT_DIR / '.env'
        requirements['env_file_exists'] = env_file.exists()
        if not requirements['env_file_exists']:
            logger.warning("⚠️ .env file not found - Telegram features may not work")
        
        return requirements
    
    def print_system_status(self):
        """Imprimir estado completo del sistema"""
        print("=" * 70)
        print("🔍 SISTEMA DE TRADING AUTOMATIZADO - STATUS REPORT")
        print("=" * 70)
        
        # System info
        print(f"🐍 Python Version: {sys.version.split()[0]}")
        print(f"📁 Working Directory: {SCRIPT_DIR}")
        print(f"⏰ Current Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()
        
        # Check requirements
        requirements = self.check_system_requirements()
        
        print("🔧 COMPONENTES DEL SISTEMA:")
        component_status = {
            'config_available': '⚙️ Configuration',
            'database_available': '🗄️ Database System', 
            'scanner_available': '🔍 Signal Scanner',
            'telegram_available': '📱 Telegram Bot',
            'backtest_available': '📊 Backtest Engine',
            'historical_data_available': '📈 Historical Data Tools',
            'env_file_exists': '🔐 Environment File'
        }
        
        for key, name in component_status.items():
            status = "✅ OK" if requirements[key] else "❌ ERROR"
            print(f"   {name}: {status}")
        
        # Overall health
        total_components = len(requirements) - 1  # Exclude python_version
        working_components = sum([1 for k, v in requirements.items() if k != 'python_version' and v])
        health_pct = (working_components / total_components) * 100
        
        print(f"\n🏥 SALUD DEL SISTEMA: {health_pct:.1f}%")
        
        if health_pct >= 90:
            print("   ✅ Sistema completamente operacional")
        elif health_pct >= 70:
            print("   ⚡ Sistema mayormente funcional - algunos componentes no disponibles")
        elif health_pct >= 50:
            print("   ⚠️ Sistema parcialmente funcional - revisar componentes faltantes")
        else:
            print("   ❌ Sistema con problemas críticos - requiere configuración")
        
        # Recommendations
        print(f"\n💡 RECOMENDACIONES:")
        if not requirements['env_file_exists']:
            print("   • Crear archivo .env con TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID")
        if not requirements['database_available']:
            print("   • Verificar permisos de base de datos y estructura de tablas")
        if not requirements['backtest_available']:
            print("   • Instalar módulos de backtesting para análisis histórico")
        if health_pct == 100:
            print("   • ¡Sistema listo para operación en vivo!")
    
    def run_live_trading(self, symbols: Optional[List[str]] = None, 
                        test_mode: bool = False) -> bool:
        """Ejecutar trading en vivo"""
        try:
            print("🚀 INICIANDO TRADING EN VIVO")
            print("=" * 50)
            
            # Verificar componentes críticos
            requirements = self.check_system_requirements()
            critical_components = ['config_available', 'scanner_available', 'telegram_available']
            
            for component in critical_components:
                if not requirements[component]:
                    logger.error(f"❌ Componente crítico no disponible: {component}")
                    return False
            
            # Import modules
            import config
            from scanner import SignalScanner
            from telegram_bot import TelegramBot
            
            # Initialize components
            scanner = SignalScanner()
            telegram = TelegramBot()
            
            # Test telegram connection
            if not telegram.initialized:
                logger.error("❌ Telegram bot no inicializado correctamente")
                return False
            
            # Send startup message
            startup_msg = f"""
🚀 <b>SISTEMA DE TRADING INICIADO</b>

📊 <b>Configuración:</b>
• Símbolos: {symbols if symbols else config.SYMBOLS[:5]}
• Timeframe: {getattr(config, 'TIMEFRAME', '15m')}
• Modo: {'🧪 TEST' if test_mode else '🔴 LIVE'}

⏰ <b>Hora inicio:</b> {datetime.now().strftime('%H:%M:%S')}
🎯 <b>Estado:</b> Buscando señales de alta calidad...

<i>Presiona Ctrl+C para detener</i>
"""
            
            telegram.send_message(startup_msg.strip())
            logger.info("📱 Mensaje de inicio enviado por Telegram")
            
            # Main trading loop
            scan_count = 0
            signals_found = 0
            
            try:
                while not self.shutdown_requested:
                    scan_count += 1
                    logger.info(f"🔍 Escaneo #{scan_count}")
                    
                    # Scan for signals
                    symbols_to_scan = symbols if symbols else config.SYMBOLS
                    signals = scanner.scan_multiple_symbols(symbols_to_scan)
                    
                    if signals:
                        signals_found += len(signals)
                        logger.info(f"📊 {len(signals)} señales detectadas")
                        
                        # Send signals via telegram
                        for signal in signals:
                            try:
                                alert_msg = telegram.format_signal_alert(signal)
                                success = telegram.send_message(alert_msg)
                                
                                if success:
                                    logger.info(f"📱 Alerta enviada: {signal.symbol} {signal.signal_type}")
                                else:
                                    logger.error(f"❌ Error enviando alerta: {signal.symbol}")
                                
                                # Delay between messages
                                time.sleep(2)
                                
                            except Exception as e:
                                logger.error(f"❌ Error procesando señal {signal.symbol}: {e}")
                    else:
                        logger.info("📊 No se detectaron señales")
                    
                    # Wait for next scan
                    scan_interval = getattr(config, 'SCAN_INTERVAL', 15) * 60  # Convert to seconds
                    
                    logger.info(f"⏳ Esperando {scan_interval//60} minutos para próximo escaneo...")
                    
                    # Sleep with interruption check
                    sleep_time = 0
                    while sleep_time < scan_interval and not self.shutdown_requested:
                        time.sleep(10)  # Check every 10 seconds
                        sleep_time += 10
                        
                        # Show progress every minute
                        if sleep_time % 60 == 0:
                            remaining = (scan_interval - sleep_time) // 60
                            if remaining > 0:
                                logger.info(f"⏳ {remaining} minutos restantes...")
                    
            except KeyboardInterrupt:
                logger.info("🛑 Interrumpido por usuario")
            
            # Send shutdown message
            shutdown_msg = f"""
🛑 <b>SISTEMA DE TRADING DETENIDO</b>

📊 <b>Estadísticas de sesión:</b>
• Escaneos realizados: {scan_count}
• Señales detectadas: {signals_found}
• Duración: {datetime.now().strftime('%H:%M:%S')}

💤 <b>Estado:</b> Sistema en pausa
            """
            
            telegram.send_message(shutdown_msg.strip())
            
            print(f"\n📊 ESTADÍSTICAS FINALES:")
            print(f"   Escaneos: {scan_count}")
            print(f"   Señales: {signals_found}")
            print(f"   Tasa detección: {(signals_found/scan_count*100):.1f}%" if scan_count > 0 else "   Tasa detección: 0%")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error en trading en vivo: {e}")
            return False
    
    def run_single_scan(self, symbols: Optional[List[str]] = None) -> bool:
        """Ejecutar escaneo único"""
        try:
            print("🔍 ESCANEO ÚNICO DE MERCADO")
            print("=" * 40)
            
            # Import scanner
            from scanner import SignalScanner
            import config
            
            scanner = SignalScanner()
            symbols_to_scan = symbols if symbols else config.SYMBOLS[:5]
            
            logger.info(f"📊 Escaneando {len(symbols_to_scan)} símbolos...")
            print(f"🎯 Símbolos: {', '.join(symbols_to_scan)}")
            
            # Perform scan
            start_time = time.time()
            signals = scanner.scan_multiple_symbols(symbols_to_scan)
            scan_time = time.time() - start_time
            
            print(f"⏱️ Tiempo de escaneo: {scan_time:.2f}s")
            print()
            
            if signals:
                print(f"📊 {len(signals)} SEÑALES DETECTADAS:")
                print("-" * 50)
                
                for i, signal in enumerate(signals, 1):
                    print(f"{i}. {signal.symbol} - {signal.signal_type}")
                    print(f"   💪 Fuerza: {signal.signal_strength}/100 ({signal.confidence_level})")
                    print(f"   💰 Precio: ${signal.current_price:.2f}")
                    
                    if hasattr(signal, 'risk_reward_ratio'):
                        print(f"   📊 R:R: 1:{signal.risk_reward_ratio:.1f}")
                    
                    if hasattr(signal, 'position_plan') and signal.position_plan:
                        print(f"   🎯 Estrategia: {signal.position_plan.strategy_type}")
                    
                    print()
                
                # Ask to send via telegram
                try:
                    send_telegram = input("📱 ¿Enviar señales por Telegram? (y/n): ").lower().strip()
                    
                    if send_telegram == 'y':
                        from telegram_bot import TelegramBot
                        telegram = TelegramBot()
                        
                        if telegram.initialized:
                            sent_count = 0
                            for signal in signals:
                                try:
                                    alert_msg = telegram.format_signal_alert(signal)
                                    success = telegram.send_message(alert_msg)
                                    if success:
                                        sent_count += 1
                                    time.sleep(2)  # Delay between messages
                                except Exception as e:
                                    logger.error(f"Error enviando {signal.symbol}: {e}")
                            
                            print(f"📱 {sent_count}/{len(signals)} alertas enviadas por Telegram")
                        else:
                            print("❌ Telegram bot no disponible")
                            
                except (KeyboardInterrupt, EOFError):
                    print("\n👋 Cancelado por usuario")
                    
            else:
                print("📊 No se detectaron señales en este momento")
                print("💡 Esto puede ser normal - el sistema es selectivo")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error en escaneo único: {e}")
            return False
    
    def run_backtest(self, symbols: Optional[List[str]] = None, 
                    start_date: Optional[str] = None, end_date: Optional[str] = None,
                    validation_only: bool = False) -> bool:
        """Ejecutar backtesting"""
        try:
            print("📊 SISTEMA DE BACKTESTING")
            print("=" * 40)
            
            # Check if backtest engine is available
            backtest_path = SCRIPT_DIR / 'historical_data' / 'backtest_engine.py'
            if not backtest_path.exists():
                print("❌ Backtest engine no encontrado")
                print("💡 Instalar: Copiar backtest_engine.py a historical_data/")
                return False
            
            # Change to historical_data directory
            original_cwd = os.getcwd()
            os.chdir(SCRIPT_DIR / 'historical_data')
            
            try:
                # Import backtest engine
                sys.path.insert(0, str(SCRIPT_DIR / 'historical_data'))
                from backtest_engine import ValidatedBacktestEngine
                from datetime import datetime
                
                # Setup parameters
                symbols_to_test = symbols if symbols else ['AAPL', 'MSFT', 'GOOGL']
                
                # Parse dates
                start_dt = None
                end_dt = None
                
                if start_date:
                    start_dt = datetime.strptime(start_date, '%Y-%m-%d')
                if end_date:
                    end_dt = datetime.strptime(end_date, '%Y-%m-%d')
                
                print(f"🎯 Símbolos: {symbols_to_test}")
                print(f"📅 Período: {start_date or 'Auto'} a {end_date or 'Auto'}")
                print(f"🔍 Modo: {'Solo validación' if validation_only else 'Backtest completo'}")
                print()
                
                # Create engine
                engine = ValidatedBacktestEngine(strict_mode=True)
                
                if validation_only:
                    # Only data validation
                    logger.info("🔍 Ejecutando solo validación de datos...")
                    
                    validation_reports = engine.validate_all_data(
                        symbols_to_test,
                        start_dt or datetime.now() - timedelta(days=90),
                        end_dt or datetime.now()
                    )
                    
                    engine.print_validation_summary()
                    
                else:
                    # Full backtest
                    logger.info("🚀 Ejecutando backtest completo...")
                    
                    metrics = engine.run_backtest(
                        symbols=symbols_to_test,
                        start_date=start_dt,
                        end_date=end_dt
                    )
                    
                    # Print results
                    engine.print_validation_summary()
                    print()
                    engine.print_summary(metrics)
                
                return True
                
            finally:
                # Restore working directory
                os.chdir(original_cwd)
            
        except Exception as e:
            logger.error(f"❌ Error en backtesting: {e}")
            return False
    
    def manage_historical_data(self, action: str = "status") -> bool:
        """Gestionar datos históricos"""
        try:
            print("📈 GESTIÓN DE DATOS HISTÓRICOS")
            print("=" * 40)
            
            historical_dir = SCRIPT_DIR / 'historical_data'
            
            if action == "status":
                # Show data status
                downloader_exists = (historical_dir / 'downloader.py').exists()
                populator_exists = (historical_dir / 'populate_db.py').exists()
                
                print(f"📁 Directorio: {historical_dir}")
                print(f"📥 Descargador: {'✅' if downloader_exists else '❌'}")
                print(f"💾 Poblador: {'✅' if populator_exists else '❌'}")
                
                # Check for existing data files
                if historical_dir.exists():
                    csv_files = list(historical_dir.glob('**/*.csv'))
                    print(f"📊 Archivos CSV: {len(csv_files)}")
                    
                    if csv_files:
                        # Show sample of files
                        print("📋 Archivos recientes:")
                        for csv_file in sorted(csv_files, key=lambda x: x.stat().st_mtime, reverse=True)[:5]:
                            size_kb = csv_file.stat().st_size / 1024
                            print(f"   • {csv_file.name} ({size_kb:.1f} KB)")
                
                # Check database
                try:
                    from database.connection import get_connection
                    conn = get_connection()
                    if conn:
                        cursor = conn.cursor()
                        cursor.execute("SELECT COUNT(*) FROM indicators_data")
                        row_count = cursor.fetchone()[0]
                        conn.close()
                        print(f"🗄️ Registros en BD: {row_count:,}")
                except Exception as e:
                    print(f"🗄️ Base de datos: ❌ ({e})")
                
            elif action == "download":
                # Download historical data
                if not (historical_dir / 'downloader.py').exists():
                    print("❌ downloader.py no encontrado")
                    return False
                
                print("📥 Iniciando descarga de datos históricos...")
                print("💡 Esto puede tomar varios minutos...")
                
                # Change directory and run downloader
                original_cwd = os.getcwd()
                os.chdir(historical_dir)
                
                try:
                    import subprocess
                    result = subprocess.run([sys.executable, 'downloader.py', '--test'], 
                                          capture_output=True, text=True)
                    
                    if result.returncode == 0:
                        print("✅ Descarga completada exitosamente")
                        print("📊 Output:", result.stdout[-500:])  # Last 500 chars
                    else:
                        print("❌ Error en descarga")
                        print("📋 Error:", result.stderr[-500:])
                        
                finally:
                    os.chdir(original_cwd)
            
            elif action == "populate":
                # Populate database
                if not (historical_dir / 'populate_db.py').exists():
                    print("❌ populate_db.py no encontrado")
                    return False
                
                print("💾 Iniciando población de base de datos...")
                print("💡 Calculando indicadores técnicos...")
                
                # Change directory and run populator
                original_cwd = os.getcwd()
                os.chdir(historical_dir)
                
                try:
                    import subprocess
                    result = subprocess.run([sys.executable, 'populate_db.py', '--test'], 
                                          capture_output=True, text=True)
                    
                    if result.returncode == 0:
                        print("✅ Población completada exitosamente")
                        print("📊 Output:", result.stdout[-500:])
                    else:
                        print("❌ Error en población")
                        print("📋 Error:", result.stderr[-500:])
                        
                finally:
                    os.chdir(original_cwd)
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error gestionando datos históricos: {e}")
            return False
    
    def setup_system(self) -> bool:
        """Configuración inicial del sistema"""
        try:
            print("⚙️ CONFIGURACIÓN INICIAL DEL SISTEMA")
            print("=" * 50)
            
            # Check current status
            requirements = self.check_system_requirements()
            
            setup_needed = []
            if not requirements['env_file_exists']:
                setup_needed.append("env_file")
            if not requirements['database_available']:
                setup_needed.append("database")
            
            if not setup_needed:
                print("✅ Sistema ya configurado correctamente")
                return True
            
            print("🔧 Componentes que necesitan configuración:")
            for item in setup_needed:
                print(f"   • {item}")
            print()
            
            # Setup .env file
            if "env_file" in setup_needed:
                print("🔐 CONFIGURACIÓN DE TELEGRAM")
                print("-" * 30)
                
                env_path = SCRIPT_DIR / '.env'
                
                # Check if user wants to set up telegram
                try:
                    setup_telegram = input("¿Configurar Telegram Bot? (y/n): ").lower().strip()
                    
                    if setup_telegram == 'y':
                        print("\n📋 Necesitas crear un bot en Telegram:")
                        print("1. Abre Telegram y busca @BotFather")
                        print("2. Envía /newbot y sigue las instrucciones")
                        print("3. Copia el token que te dé BotFather")
                        print()
                        
                        bot_token = input("🤖 Pega aquí tu Bot Token: ").strip()
                        
                        print("\n📱 Necesitas tu Chat ID:")
                        print("1. Envía un mensaje a tu bot")
                        print("2. Ve a: https://api.telegram.org/bot<TOKEN>/getUpdates")
                        print("3. Busca el 'id' en el JSON")
                        print()
                        
                        chat_id = input("💬 Pega aquí tu Chat ID: ").strip()
                        
                        if bot_token and chat_id:
                            # Create .env file
                            env_content = f"""# Telegram Configuration
TELEGRAM_BOT_TOKEN={bot_token}
TELEGRAM_CHAT_ID={chat_id}

# Optional: Additional settings
LOG_LEVEL=INFO
"""
                            
                            with open(env_path, 'w') as f:
                                f.write(env_content)
                            
                            print("✅ Archivo .env creado exitosamente")
                        else:
                            print("❌ Token o Chat ID vacío - .env no creado")
                    
                except (KeyboardInterrupt, EOFError):
                    print("\n❌ Configuración de Telegram cancelada")
            
            # Setup database
            if "database" in setup_needed:
                print("\n🗄️ CONFIGURACIÓN DE BASE DE DATOS")
                print("-" * 30)
                
                try:
                    # Try to create database tables
                    from database.connection import get_connection
                    
                    # This should create the database if it doesn't exist
                    conn = get_connection()
                    if conn:
                        conn.close()
                        print("✅ Base de datos configurada correctamente")
                    else:
                        print("❌ Error configurando base de datos")
                        
                except Exception as e:
                    print(f"❌ Error configurando base de datos: {e}")
                    print("💡 Verifica que database/connection.py esté disponible")
            
            print("\n🎉 CONFIGURACIÓN COMPLETADA")
            print("💡 Ejecuta 'python start.py status' para verificar el estado")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error en configuración: {e}")
            return False

def main():
    """Función principal con interfaz CLI"""
    parser = argparse.ArgumentParser(
        description="🚀 Sistema Master de Trading Automatizado V3.0",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos de uso:
  python start.py status                    # Estado del sistema
  python start.py setup                     # Configuración inicial
  python start.py auto                      # Trading automático
  python start.py scan --symbols AAPL MSFT # Escaneo único
  python start.py backtest --validation     # Solo validar datos
  python start.py data download             # Descargar datos históricos
        """
    )
    
    # Subcommands
    subparsers = parser.add_subparsers(dest='command', help='Comandos disponibles')
    
    # Status command
    status_parser = subparsers.add_parser('status', help='Mostrar estado del sistema')
    
    # Setup command  
    setup_parser = subparsers.add_parser('setup', help='Configuración inicial')
    
    # Auto trading command
    auto_parser = subparsers.add_parser('auto', help='Trading automático')
    auto_parser.add_argument('--symbols', nargs='+', help='Símbolos específicos')
    auto_parser.add_argument('--test', action='store_true', help='Modo test')
    
    # Scan command
    scan_parser = subparsers.add_parser('scan', help='Escaneo único')
    scan_parser.add_argument('--symbols', nargs='+', help='Símbolos específicos')
    
    # Backtest command
    backtest_parser = subparsers.add_parser('backtest', help='Backtesting')
    backtest_parser.add_argument('--symbols', nargs='+', help='Símbolos a testear')
    backtest_parser.add_argument('--start-date', help='Fecha inicio (YYYY-MM-DD)')
    backtest_parser.add_argument('--end-date', help='Fecha fin (YYYY-MM-DD)')
    backtest_parser.add_argument('--validation', action='store_true', help='Solo validar datos')
    
    # Data management command
    data_parser = subparsers.add_parser('data', help='Gestión de datos históricos')
    data_parser.add_argument('action', choices=['status', 'download', 'populate'], 
                            help='Acción a realizar')
    
    args = parser.parse_args()
    
    # Create system master
    system = TradingSystemMaster()
    
    try:
        # Handle commands
        if args.command == 'status' or not args.command:
            # Default to status if no command given
            system.print_system_status()
            return 0
            
        elif args.command == 'setup':
            success = system.setup_system()
            return 0 if success else 1
            
        elif args.command == 'auto':
            print("🤖 Iniciando trading automático...")
            success = system.run_live_trading(
                symbols=args.symbols,
                test_mode=args.test
            )
            return 0 if success else 1
            
        elif args.command == 'scan':
            success = system.run_single_scan(symbols=args.symbols)
            return 0 if success else 1
            
        elif args.command == 'backtest':
            success = system.run_backtest(
                symbols=args.symbols,
                start_date=args.start_date,
                end_date=args.end_date,
                validation_only=args.validation
            )
            return 0 if success else 1
            
        elif args.command == 'data':
            success = system.manage_historical_data(action=args.action)
            return 0 if success else 1
            
        else:
            parser.print_help()
            return 1
            
    except KeyboardInterrupt:
        print("\n👋 Proceso cancelado por usuario")
        return 0
    except Exception as e:
        logger.error(f"❌ Error ejecutando comando '{args.command}': {e}")
        return 1

def interactive_mode():
    """Modo interactivo con menú"""
    system = TradingSystemMaster()
    
    while True:
        print("\n" + "=" * 60)
        print("🚀 SISTEMA DE TRADING AUTOMATIZADO V3.0")
        print("=" * 60)
        print("Selecciona una opción:")
        print("1. 📊 Estado del sistema")
        print("2. ⚙️ Configuración inicial")
        print("3. 🤖 Trading automático")
        print("4. 🔍 Escaneo único")
        print("5. 📈 Backtesting")
        print("6. 💾 Gestión de datos")
        print("7. 🆘 Ayuda")
        print("0. 👋 Salir")
        print()
        
        try:
            choice = input("Elige una opción (0-7): ").strip()
            
            if choice == '0':
                print("👋 ¡Hasta luego!")
                break
                
            elif choice == '1':
                system.print_system_status()
                input("\n📱 Presiona Enter para continuar...")
                
            elif choice == '2':
                system.setup_system()
                input("\n📱 Presiona Enter para continuar...")
                
            elif choice == '3':
                print("\n🤖 TRADING AUTOMÁTICO")
                print("-" * 30)
                symbols_input = input("Símbolos (separados por espacio, Enter para default): ").strip()
                symbols = symbols_input.split() if symbols_input else None
                test_mode = input("¿Modo test? (y/n): ").lower().strip() == 'y'
                
                print("\n🚨 ¡ATENCIÓN! Iniciando trading automático...")
                print("Presiona Ctrl+C para detener en cualquier momento")
                input("Presiona Enter para continuar o Ctrl+C para cancelar...")
                
                system.run_live_trading(symbols=symbols, test_mode=test_mode)
                
            elif choice == '4':
                print("\n🔍 ESCANEO ÚNICO")
                print("-" * 20)
                symbols_input = input("Símbolos (separados por espacio, Enter para default): ").strip()
                symbols = symbols_input.split() if symbols_input else None
                
                system.run_single_scan(symbols=symbols)
                input("\n📱 Presiona Enter para continuar...")
                
            elif choice == '5':
                print("\n📈 BACKTESTING")
                print("-" * 20)
                
                # Submenu for backtest
                print("¿Qué deseas hacer?")
                print("1. Solo validar datos")
                print("2. Backtest completo")
                
                backtest_choice = input("Elige (1-2): ").strip()
                
                symbols_input = input("Símbolos (Enter para default): ").strip()
                symbols = symbols_input.split() if symbols_input else None
                
                start_date = input("Fecha inicio (YYYY-MM-DD, Enter para auto): ").strip() or None
                end_date = input("Fecha fin (YYYY-MM-DD, Enter para auto): ").strip() or None
                
                validation_only = backtest_choice == '1'
                
                system.run_backtest(
                    symbols=symbols,
                    start_date=start_date,
                    end_date=end_date,
                    validation_only=validation_only
                )
                input("\n📱 Presiona Enter para continuar...")
                
            elif choice == '6':
                print("\n💾 GESTIÓN DE DATOS")
                print("-" * 20)
                print("1. Ver estado de datos")
                print("2. Descargar datos históricos")
                print("3. Poblar base de datos")
                
                data_choice = input("Elige (1-3): ").strip()
                
                action_map = {'1': 'status', '2': 'download', '3': 'populate'}
                action = action_map.get(data_choice, 'status')
                
                system.manage_historical_data(action=action)
                input("\n📱 Presiona Enter para continuar...")
                
            elif choice == '7':
                print_help()
                input("\n📱 Presiona Enter para continuar...")
                
            else:
                print("❌ Opción no válida")
                
        except (KeyboardInterrupt, EOFError):
            print("\n👋 Saliendo...")
            break
        except Exception as e:
            logger.error(f"❌ Error en modo interactivo: {e}")

def print_help():
    """Mostrar ayuda detallada"""
    print("\n📋 AYUDA DEL SISTEMA DE TRADING")
    print("=" * 50)
    
    print("\n🎯 COMANDOS PRINCIPALES:")
    print("• python start.py status      - Estado del sistema")
    print("• python start.py setup       - Configuración inicial")  
    print("• python start.py auto        - Trading automático")
    print("• python start.py scan        - Escaneo único")
    print("• python start.py backtest    - Análisis histórico")
    print("• python start.py data <cmd>  - Gestión de datos")
    
    print("\n🔧 CONFIGURACIÓN INICIAL:")
    print("1. Ejecutar: python start.py setup")
    print("2. Crear bot en @BotFather (Telegram)")
    print("3. Obtener Chat ID de tu usuario")
    print("4. Descargar datos: python start.py data download")
    print("5. Poblar BD: python start.py data populate")
    
    print("\n📊 FLUJO DE TRABAJO TÍPICO:")
    print("1. Setup inicial (solo una vez)")
    print("2. Descargar/poblar datos históricos")
    print("3. Validar datos: python start.py backtest --validation")
    print("4. Test único: python start.py scan")
    print("5. Trading en vivo: python start.py auto")
    
    print("\n⚠️ CONSIDERACIONES IMPORTANTES:")
    print("• Revisa siempre las señales antes de operar")
    print("• Usa modo test antes de trading real")
    print("• Mantén datos históricos actualizados")
    print("• Monitorea logs para errores")
    
    print("\n🆘 SOLUCIÓN DE PROBLEMAS:")
    print("• Error de database: Verificar permisos y estructura")
    print("• Error de Telegram: Revisar .env y tokens")
    print("• Sin señales: Normal, el sistema es selectivo")
    print("• Error de datos: Ejecutar data download + populate")

if __name__ == "__main__":
    print("🚀 SISTEMA DE TRADING AUTOMATIZADO V3.0")
    print("=" * 50)
    
    # If no arguments provided, run interactive mode
    if len(sys.argv) == 1:
        interactive_mode()
    else:
        exit_code = main()
        sys.exit(exit_code)