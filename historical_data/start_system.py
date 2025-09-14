#!/usr/bin/env python3
"""
🚀 START HISTORICAL SYSTEM - INICIALIZADOR COMPLETO V3.0
=====================================================

Script principal para inicializar y ejecutar el sistema de datos históricos:

🎯 FUNCIONALIDADES:
- Quick setup y validación del sistema
- Test de conectividad de APIs
- Descarga inicial de datos históricos
- Validación de configuración
- Modo interactivo y automático

🚦 MODOS DE EJECUCIÓN:
- --setup: Configuración inicial completa
- --test: Solo testing del sistema
- --download: Solo descarga de datos
- --interactive: Modo interactivo con menú
- --auto: Modo automático completo
"""

import sys
import os
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import logging

# Setup de imports
def setup_imports():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    if current_dir not in sys.path:
        sys.path.insert(0, current_dir)
    parent_dir = os.path.dirname(current_dir)
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)

setup_imports()

# Imports del sistema
try:
    import config
    from api_manager import APIManager
    from data_downloader import DataDownloader
    from test_historical_system import HistoricalSystemTester
except ImportError as e:
    print(f"❌ Error importando módulos del sistema histórico: {e}")
    print("📝 Asegúrate de estar ejecutando desde el directorio historical_data/")
    sys.exit(1)

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class HistoricalSystemStarter:
    """
    Inicializador principal del sistema de datos históricos
    """
    
    def __init__(self):
        """Inicializar starter"""
        self.api_manager = None
        self.downloader = None
        self.tester = None
        
        print("🚀 Historical System Starter V3.0")
        print("=" * 50)
        
        # Validar configuración inicial
        self.validate_environment()
    
    def validate_environment(self):
        """Validar que el entorno esté configurado correctamente"""
        print("\n🔍 VALIDANDO ENTORNO...")
        
        # Verificar archivos de configuración
        required_files = [
            'config.py',
            'api_manager.py', 
            'data_downloader.py'
        ]
        
        missing_files = []
        for file in required_files:
            if not os.path.exists(file):
                missing_files.append(file)
        
        if missing_files:
            print(f"❌ Archivos faltantes: {missing_files}")
            print("📝 Asegúrate de que todos los archivos estén en historical_data/")
            sys.exit(1)
        
        # Verificar directorios
        required_dirs = [
            'logs',
            'raw_data', 
            'processed_data',
            'temp_data'
        ]
        
        for directory in required_dirs:
            if not os.path.exists(directory):
                os.makedirs(directory, exist_ok=True)
                print(f"📁 Creado directorio: {directory}")
        
        # Verificar archivo .env en directorio padre
        env_file = os.path.join('..', '.env')
        if not os.path.exists(env_file):
            print("⚠️ Archivo .env no encontrado en directorio padre")
            print("📝 Asegúrate de configurar las API keys")
        
        print("✅ Validación del entorno completada")
    
    def show_system_status(self):
        """Mostrar estado actual del sistema"""
        print("\n📊 ESTADO DEL SISTEMA")
        print("-" * 30)
        
        # APIs configuradas
        available_apis = config.get_available_apis()
        print(f"🔑 APIs disponibles: {len(available_apis)}")
        for api in available_apis:
            print(f"   ✅ {api}")
        
        unavailable_apis = [api for api in config.API_PRIORITY if api not in available_apis]
        if unavailable_apis:
            print(f"⚠️ APIs no configuradas: {unavailable_apis}")
        
        # Archivos de datos existentes
        raw_data_dir = 'raw_data'
        if os.path.exists(raw_data_dir):
            csv_files = [f for f in os.listdir(raw_data_dir) if f.endswith('.csv')]
            print(f"📁 Archivos de datos: {len(csv_files)} CSV files")
        else:
            print("📁 No hay datos históricos descargados")
        
        # Configuración actual
        print(f"📅 Período configurado: {config.HISTORICAL_START_DATE} a hoy")
        print(f"📈 Símbolos: {len(config.SYMBOLS)} configurados")
        print(f"⏱️ Timeframes: {config.TIMEFRAMES}")
    
    def setup_system(self):
        """Configuración inicial completa del sistema"""
        print("\n⚙️ CONFIGURACIÓN INICIAL DEL SISTEMA")
        print("-" * 40)
        
        # Paso 1: Verificar APIs
        print("1️⃣ Verificando conectividad de APIs...")
        
        self.api_manager = APIManager()
        available_apis = self.api_manager.get_available_apis()
        
        if not available_apis:
            print("❌ No hay APIs disponibles")
            print("📝 Configura al menos una API en el archivo .env")
            return False
        
        # Test de conectividad rápido
        print("🔍 Testing conectividad...")
        success, data, source = self.api_manager.get_data('AAPL', interval='1d', period='5d')
        
        if success:
            print(f"✅ Conectividad OK - usando {source}")
        else:
            print(f"❌ Error de conectividad: {source}")
            return False
        
        # Paso 2: Inicializar downloader
        print("\n2️⃣ Inicializando downloader...")
        
        self.downloader = DataDownloader(self.api_manager)
        print("✅ Downloader inicializado")
        
        # Paso 3: Verificar configuración
        print("\n3️⃣ Verificando configuración...")
        
        config_errors = config.validate_config()
        if config_errors:
            print("❌ Errores de configuración:")
            for error in config_errors:
                print(f"   {error}")
            return False
        
        print("✅ Configuración válida")
        
        print("\n🎉 Sistema configurado correctamente")
        return True
    
    def run_tests(self, quick: bool = False):
        """Ejecutar tests del sistema"""
        print(f"\n🧪 EJECUTANDO TESTS {'(QUICK MODE)' if quick else '(FULL SUITE)'}")
        print("-" * 50)
        
        self.tester = HistoricalSystemTester()
        
        if quick:
            # Solo tests críticos
            self.tester.test_api_manager()
        else:
            # Suite completa
            self.tester.run_all_tests()
        
        return True
    
    def download_initial_data(self, symbols: List[str] = None, 
                            timeframes: List[str] = None,
                            months_back: int = 3):
        """Descarga inicial de datos históricos"""
        print(f"\n📥 DESCARGA INICIAL DE DATOS ({months_back} meses)")
        print("-" * 40)
        
        # Defaults
        symbols = symbols or config.SYMBOLS[:10]  # Primeros 10 símbolos
        timeframes = timeframes or ['1d', '1h']   # Solo timeframes principales
        
        # Calcular fechas
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=months_back * 30)).strftime('%Y-%m-%d')
        
        print(f"📋 Descargando:")
        print(f"   Símbolos: {len(symbols)} ({', '.join(symbols[:5])}{'...' if len(symbols) > 5 else ''})")
        print(f"   Timeframes: {timeframes}")
        print(f"   Período: {start_date} a {end_date}")
        
        # Confirmar con usuario en modo interactivo
        if '--interactive' in sys.argv:
            response = input(f"\n¿Proceder con la descarga? (s/n): ").lower()
            if response != 's' and response != 'y':
                print("⏹️ Descarga cancelada")
                return False
        
        # Ejecutar descarga
        if not self.downloader:
            self.downloader = DataDownloader(self.api_manager)
        
        start_time = time.time()
        
        stats = self.downloader.download_batch(
            symbols=symbols,
            timeframes=timeframes,
            start_date=start_date,
            end_date=end_date,
            max_workers=config.PARALLEL_CONFIG.get('max_workers', 2)
        )
        
        elapsed_time = time.time() - start_time
        
        # Mostrar resultados
        print(f"\n📊 RESULTADOS DE DESCARGA:")
        print(f"   Estado: {stats.get('status', 'unknown')}")
        print(f"   Tareas completadas: {stats.get('completed_tasks', 0)}")
        print(f"   Tareas fallidas: {stats.get('failed_tasks', 0)}")
        print(f"   Puntos descargados: {stats.get('data_points_downloaded', 0):,}")
        print(f"   Tiempo total: {elapsed_time:.1f}s")
        
        if stats.get('status') == 'completed':
            success_rate = stats.get('success_rate', 0)
            print(f"   Tasa de éxito: {success_rate:.1f}%")
            
            if success_rate >= 80:
                print("✅ Descarga exitosa")
                return True
            else:
                print("⚠️ Descarga parcial - revisar errores")
                return False
        else:
            print("❌ Descarga falló")
            return False
    
    def interactive_menu(self):
        """Menú interactivo para el usuario"""
        print("\n🎯 MODO INTERACTIVO")
        print("=" * 30)
        
        while True:
            print(f"\n📋 OPCIONES DISPONIBLES:")
            print("   1. 🔍 Ver estado del sistema")
            print("   2. ⚙️ Setup inicial completo")
            print("   3. 🧪 Ejecutar tests (rápidos)")
            print("   4. 🧪 Ejecutar tests (completos)")
            print("   5. 📥 Descarga inicial (3 meses)")
            print("   6. 📥 Descarga personalizada")
            print("   7. 📊 Ver estadísticas de API")
            print("   8. 🧹 Limpiar archivos temporales")
            print("   0. ❌ Salir")
            
            try:
                choice = input("\n🎯 Selecciona una opción (0-8): ").strip()
                
                if choice == '0':
                    print("👋 ¡Hasta luego!")
                    break
                
                elif choice == '1':
                    self.show_system_status()
                
                elif choice == '2':
                    self.setup_system()
                
                elif choice == '3':
                    self.run_tests(quick=True)
                
                elif choice == '4':
                    self.run_tests(quick=False)
                
                elif choice == '5':
                    self.download_initial_data()
                
                elif choice == '6':
                    self.custom_download_menu()
                
                elif choice == '7':
                    self.show_api_stats()
                
                elif choice == '8':
                    self.cleanup_temp_files()
                
                else:
                    print("❌ Opción inválida")
            
            except KeyboardInterrupt:
                print("\n👋 Interrumpido por usuario")
                break
            except Exception as e:
                print(f"❌ Error: {e}")
    
    def custom_download_menu(self):
        """Menú para descarga personalizada"""
        print(f"\n📥 DESCARGA PERSONALIZADA")
        print("-" * 30)
        
        # Seleccionar símbolos
        print(f"📈 Símbolos disponibles: {', '.join(config.SYMBOLS[:10])}...")
        symbols_input = input("Ingresa símbolos separados por coma (Enter para default): ").strip()
        
        if symbols_input:
            symbols = [s.strip().upper() for s in symbols_input.split(',')]
        else:
            symbols = config.SYMBOLS[:5]  # Default primeros 5
        
        # Seleccionar timeframes
        print(f"⏱️ Timeframes disponibles: {', '.join(config.TIMEFRAMES)}")
        timeframes_input = input("Ingresa timeframes separados por coma (Enter para 1d,1h): ").strip()
        
        if timeframes_input:
            timeframes = [t.strip() for t in timeframes_input.split(',')]
        else:
            timeframes = ['1d', '1h']
        
        # Seleccionar período
        months_input = input("Meses hacia atrás (Enter para 3): ").strip()
        try:
            months_back = int(months_input) if months_input else 3
        except:
            months_back = 3
        
        # Ejecutar descarga
        self.download_initial_data(symbols, timeframes, months_back)
    
    def show_api_stats(self):
        """Mostrar estadísticas de uso de APIs"""
        print(f"\n📊 ESTADÍSTICAS DE API")
        print("-" * 30)
        
        if not self.api_manager:
            self.api_manager = APIManager()
        
        summary = self.api_manager.get_daily_summary()
        
        for api_name, stats in summary.items():
            print(f"\n🔑 {api_name}:")
            print(f"   Requests: {stats['requests_made']}")
            print(f"   Éxito: {stats['success_rate']:.1f}%")
            print(f"   Tiempo promedio: {stats['avg_response_time']:.2f}s")
            print(f"   Estado: {stats['status']}")
            print(f"   Disponible: {'✅' if stats['can_make_request'] else '❌'}")
    
    def cleanup_temp_files(self):
        """Limpiar archivos temporales"""
        print(f"\n🧹 LIMPIEZA DE ARCHIVOS TEMPORALES")
        print("-" * 40)
        
        temp_dirs = ['temp_data', 'logs']
        total_cleaned = 0
        
        for temp_dir in temp_dirs:
            if os.path.exists(temp_dir):
                files = os.listdir(temp_dir)
                temp_files = [f for f in files if f.endswith('.tmp') or f.endswith('.temp')]
                
                for temp_file in temp_files:
                    try:
                        os.remove(os.path.join(temp_dir, temp_file))
                        total_cleaned += 1
                    except:
                        pass
        
        print(f"✅ Limpieza completada: {total_cleaned} archivos eliminados")
    
    def auto_mode(self):
        """Modo automático completo"""
        print(f"\n🤖 MODO AUTOMÁTICO - SETUP COMPLETO")
        print("=" * 40)
        
        steps = [
            ("⚙️ Setup del sistema", self.setup_system),
            ("🧪 Tests básicos", lambda: self.run_tests(quick=True)),
            ("📥 Descarga inicial", self.download_initial_data)
        ]
        
        for step_name, step_func in steps:
            print(f"\n{step_name}...")
            try:
                success = step_func()
                if success:
                    print(f"✅ {step_name} completado")
                else:
                    print(f"❌ {step_name} falló")
                    break
            except Exception as e:
                print(f"💥 Error en {step_name}: {e}")
                break
        else:
            print(f"\n🎉 SETUP AUTOMÁTICO COMPLETADO")
            self.show_system_status()

def main():
    """Función principal CLI"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Historical System Starter V3.0')
    parser.add_argument('--setup', action='store_true',
                       help='Ejecutar configuración inicial')
    parser.add_argument('--test', action='store_true',
                       help='Ejecutar tests del sistema')
    parser.add_argument('--test-quick', action='store_true',
                       help='Ejecutar tests rápidos')
    parser.add_argument('--download', action='store_true',
                       help='Ejecutar descarga inicial')
    parser.add_argument('--interactive', action='store_true',
                       help='Modo interactivo con menú')
    parser.add_argument('--auto', action='store_true',
                       help='Modo automático completo')
    parser.add_argument('--status', action='store_true',
                       help='Mostrar estado del sistema')
    
    args = parser.parse_args()
    
    starter = HistoricalSystemStarter()
    
    # Ejecutar según argumentos
    if args.status:
        starter.show_system_status()
    elif args.setup:
        starter.setup_system()
    elif args.test:
        starter.run_tests(quick=False)
    elif args.test_quick:
        starter.run_tests(quick=True)
    elif args.download:
        starter.download_initial_data()
    elif args.interactive:
        starter.interactive_menu()
    elif args.auto:
        starter.auto_mode()
    else:
        # Default: mostrar ayuda y opciones
        print("\n🎯 OPCIONES RÁPIDAS:")
        print("   python start_system.py --status      # Ver estado")
        print("   python start_system.py --auto        # Setup completo")
        print("   python start_system.py --interactive # Menú interactivo")
        print("   python start_system.py --help        # Ver todas las opciones")
        
        response = input(f"\n¿Ejecutar modo interactivo? (s/n): ").lower()
        if response == 's' or response == 'y':
            starter.interactive_menu()

if __name__ == "__main__":
    main()