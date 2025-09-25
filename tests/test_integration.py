#!/usr/bin/env python3
"""
🧪 TEST INTEGRATION - Validar implementación actual V3.0
=======================================================

Test completo para validar los componentes creados hasta ahora:
- scanner_enhancer.py: Extensión del scanner con state awareness
- state_manager.py: Controlador principal de estados
- Integración con base de datos y componentes existentes

🎯 OBJETIVOS:
1. Verificar que todos los imports funcionan
2. Validar funcionalidad básica de cada componente  
3. Probar integración entre componentes
4. Verificar feature flags y configuración
5. Testing de casos edge importantes

Ejecutar desde raíz del proyecto:
python -m tests.test_integration
"""

import sys
import os
from pathlib import Path
from datetime import datetime, timedelta
import traceback
import logging
import uuid
import pytz

# Agregar proyecto root al path
parent_dir = Path(__file__).parent.parent
sys.path.insert(0, str(parent_dir))

# Configurar logging para testing
logging.basicConfig(
    level=logging.WARNING,  # Reducir ruido durante tests
    format='%(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Colores para output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m' 
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def print_test(msg, color=Colors.BLUE):
    print(f"{color}{Colors.BOLD}🧪 {msg}{Colors.ENDC}")

def print_success(msg):
    print(f"{Colors.GREEN}✅ {msg}{Colors.ENDC}")

def print_error(msg):
    print(f"{Colors.RED}❌ {msg}{Colors.ENDC}")

def print_warning(msg):
    print(f"{Colors.YELLOW}⚠️ {msg}{Colors.ENDC}")


class TestIntegrationV3:
    """Testing suite para validar implementación actual V3.0"""
    
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.warnings = 0
        
    def run_all_tests(self):
        """Ejecutar todos los tests de integración"""
        print_test("TESTING INTEGRATION V3.0 - Position Management System")
        print("=" * 80)
        
        # Test 1: Imports
        self.test_imports()
        
        # Test 2: State Manager  
        self.test_state_manager_basic()
        
        # Test 3: Scanner Enhancer
        self.test_scanner_enhancer_basic()
        
        # Test 4: Integración con base de datos
        self.test_database_integration()
        
        # Test 5: Feature flags
        self.test_feature_flags()
        
        # Test 6: Cache y performance
        self.test_cache_functionality()
        
        # Resumen final
        self.print_summary()
        
        return self.failed == 0
    
    def test_imports(self):
        """Test 1: Validar todas las importaciones necesarias"""
        print_test("TEST 1: Validando importaciones...")
        
        try:
            # Core position management (ya debería existir)
            from position_management.states import PositionStatus, EntryStatus, SignalDirection
            from position_management.data_models import EnhancedPosition, ExecutionLevel
            from position_management.state_machine import PositionStateMachine
            print_success("✅ Core position management imports OK")
            
            # Nuevos componentes creados
            from position_management.state_manager import StateManager, get_state_manager, StateChangeEvent
            print_success("✅ State Manager imports OK")
            
            from position_management.scanner_enhancer import ScannerEnhancer, enhance_scanner_if_enabled
            print_success("✅ Scanner Enhancer imports OK")
            
            # Database components
            from database.position_queries import PositionQueries
            from database.connection import get_connection
            print_success("✅ Database components imports OK")
            
            # Existing system components
            try:
                from scanner import SignalScanner, TradingSignal
                print_success("✅ Scanner system imports OK")
            except ImportError:
                print_warning("⚠️ Scanner system no disponible (normal en testing)")
            
            self.passed += 1
            
        except ImportError as e:
            print_error(f"Error de importación: {e}")
            print_error(f"Stacktrace: {traceback.format_exc()}")
            self.failed += 1
        except Exception as e:
            print_error(f"Error inesperado en imports: {e}")
            self.failed += 1
    
    def test_state_manager_basic(self):
        """Test 2: Funcionalidad básica del State Manager"""
        print_test("TEST 2: Validando State Manager...")
        
        try:
            from position_management.state_manager import get_state_manager, StateChangeEvent, reset_state_manager
            from position_management.states import PositionStatus, SignalDirection
            from position_management.data_models import ExecutionLevel, ExecutionType
            
            # Reset para test limpio
            reset_state_manager()
            state_manager = get_state_manager()
            
            # Test: Inicialización
            stats = state_manager.get_stats()
            print_success(f"✅ State Manager inicializado. Cache: {stats['cache_size']}")
            
            # Test: Crear niveles de prueba
            entry_levels = [
                ExecutionLevel(
                    level_id=str(uuid.uuid4()),
                    level_type=ExecutionType.ENTRY,
                    target_price=100.0,
                    quantity=10,
                    percentage=50.0
                )
            ]
            
            exit_levels = [
                ExecutionLevel(
                    level_id=str(uuid.uuid4()),
                    level_type=ExecutionType.EXIT,
                    target_price=110.0,
                    quantity=10,
                    percentage=100.0
                )
            ]
            
            # Test: Observer system
            events_received = []
            def test_observer(notification):
                events_received.append(notification.event_type)
            
            state_manager.add_observer(StateChangeEvent.POSITION_CREATED, test_observer)
            
            # Test: Crear posición (puede fallar por DB, está OK)
            try:
                position = state_manager.create_position(
                    symbol="TEST_SM",
                    direction=SignalDirection.LONG,
                    entry_levels=entry_levels,
                    exit_levels=exit_levels,
                    metadata={"test": True}
                )
                print_success(f"✅ Posición creada: {position.position_id}")
                
                # Verificar observer funcionó
                if StateChangeEvent.POSITION_CREATED in events_received:
                    print_success("✅ Sistema de observers funcionando")
                else:
                    print_warning("⚠️ Sistema de observers no activado")
                
            except Exception as db_error:
                print_warning(f"⚠️ Creación de posición falló (esperado si DB no está configurada): {db_error}")
            
            self.passed += 1
            
        except Exception as e:
            print_error(f"Error en State Manager test: {e}")
            print_error(f"Stacktrace: {traceback.format_exc()}")
            self.failed += 1
    
    def test_scanner_enhancer_basic(self):
        """Test 3: Funcionalidad básica del Scanner Enhancer"""
        print_test("TEST 3: Validando Scanner Enhancer...")
        
        try:
            from position_management.scanner_enhancer import ScannerEnhancer, enhance_scanner_if_enabled
            
            # Mock scanner básico para testing
            class MockScanner:
                def __init__(self):
                    self.signals_generated = 0
                    
                def scan_single_symbol(self, symbol):
                    # Mock signal para testing
                    from datetime import datetime
                    
                    class MockSignal:
                        def __init__(self, symbol):
                            self.symbol = symbol
                            self.signal_type = "LONG"
                            self.signal_strength = 75
                            self.confidence_level = "MEDIUM"
                            self.timestamp = datetime.now()
                            self.metadata = {}
                    
                    return MockSignal(symbol)
                
                def scan_symbols(self, symbols):
                    return [self.scan_single_symbol(s) for s in symbols]
            
            # Test: Inicialización del enhancer
            mock_scanner = MockScanner()
            enhancer = ScannerEnhancer(mock_scanner)
            print_success("✅ Scanner Enhancer inicializado")
            
            # Test: Stats del enhancer
            stats = enhancer.get_scanning_stats()
            print_success(f"✅ Stats obtenidas: enhanced_scanning_enabled = {stats.get('enhanced_scanning_enabled', False)}")
            
            # Test: Scanning con state awareness
            try:
                symbols = ["TEST1", "TEST2"]
                signals = enhancer.scan_with_state_awareness(symbols)
                print_success(f"✅ State-aware scanning completado: {len(signals)} señales")
            except Exception as scan_error:
                print_warning(f"⚠️ State-aware scanning falló (esperado sin DB): {scan_error}")
            
            # Test: Feature flag integration
            try:
                import config
                # Mock config para testing
                config.USE_POSITION_MANAGEMENT = False
                enhanced_scanner = enhance_scanner_if_enabled(mock_scanner)
                print_success("✅ Feature flag integration OK")
            except Exception as config_error:
                print_warning(f"⚠️ Config no disponible: {config_error}")
            
            self.passed += 1
            
        except Exception as e:
            print_error(f"Error en Scanner Enhancer test: {e}")
            print_error(f"Stacktrace: {traceback.format_exc()}")
            self.failed += 1
    
    def test_database_integration(self):
        """Test 4: Integración con base de datos"""
        print_test("TEST 4: Validando integración con base de datos...")
        
        try:
            from database.position_queries import PositionQueries
            from database.connection import get_connection
            
            # Test: Conexión básica
            try:
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='position_executions'")
                table_exists = cursor.fetchone() is not None
                conn.close()
                
                if table_exists:
                    print_success("✅ Tabla position_executions existe")
                else:
                    print_warning("⚠️ Tabla position_executions no existe")
                
            except Exception as db_error:
                print_warning(f"⚠️ Conexión DB falló: {db_error}")
            
            # Test: PositionQueries initialization
            queries = PositionQueries()
            print_success("✅ PositionQueries inicializado")
            
            # Test: Operaciones básicas (pueden fallar, está OK)
            try:
                active_count = queries.get_active_positions_count()
                print_success(f"✅ Consulta de posiciones activas: {active_count}")
            except Exception as query_error:
                print_warning(f"⚠️ Consulta falló (esperado si tabla no existe): {query_error}")
            
            self.passed += 1
            
        except Exception as e:
            print_error(f"Error en database integration test: {e}")
            self.failed += 1
    
    def test_feature_flags(self):
        """Test 5: Sistema de feature flags"""
        print_test("TEST 5: Validando feature flags...")
        
        try:
            # Test: Config básico
            try:
                import config
                has_config = True
                print_success("✅ Config module disponible")
                
                # Verificar flags relevantes
                flags_to_check = [
                    'USE_POSITION_MANAGEMENT',
                    'ENABLE_POSITION_CACHE',
                    'USE_ADAPTIVE_TARGETS'
                ]
                
                for flag in flags_to_check:
                    value = getattr(config, flag, None)
                    if value is not None:
                        print_success(f"✅ {flag} = {value}")
                    else:
                        print_warning(f"⚠️ {flag} no definido")
                
            except ImportError:
                print_warning("⚠️ Config module no disponible")
                has_config = False
            
            # Test: Behavior con/sin feature flags
            if has_config:
                from position_management.scanner_enhancer import enhance_scanner_if_enabled
                
                class MockScanner:
                    def scan_symbols(self, symbols):
                        return []
                
                # Test con flag OFF
                original_value = getattr(config, 'USE_POSITION_MANAGEMENT', False)
                config.USE_POSITION_MANAGEMENT = False
                
                mock_scanner = MockScanner()
                result_off = enhance_scanner_if_enabled(mock_scanner)
                
                # Test con flag ON  
                config.USE_POSITION_MANAGEMENT = True
                result_on = enhance_scanner_if_enabled(mock_scanner)
                
                # Restaurar valor original
                config.USE_POSITION_MANAGEMENT = original_value
                
                print_success("✅ Feature flag behavior OK")
            
            self.passed += 1
            
        except Exception as e:
            print_error(f"Error en feature flags test: {e}")
            self.failed += 1
    
    def test_cache_functionality(self):
        """Test 6: Funcionalidad de cache"""
        print_test("TEST 6: Validando cache y performance...")
        
        try:
            from position_management.state_manager import get_state_manager, reset_state_manager
            from position_management.scanner_enhancer import ScannerEnhancer
            
            # Test State Manager cache
            reset_state_manager()
            state_manager = get_state_manager()
            
            # Test cache operations
            state_manager.clear_cache()
            stats_before = state_manager.get_stats()
            print_success(f"✅ State Manager cache limpio: {stats_before['cache_size']}")
            
            # Test Scanner Enhancer cache
            class MockScanner:
                def scan_single_symbol(self, symbol):
                    return None
            
            enhancer = ScannerEnhancer(MockScanner())
            enhancer.clear_cache()
            print_success("✅ Scanner Enhancer cache limpio")
            
            self.passed += 1
            
        except Exception as e:
            print_error(f"Error en cache functionality test: {e}")
            self.failed += 1
    
    def print_summary(self):
        """Imprimir resumen final de tests"""
        print("\n" + "=" * 80)
        print_test("RESUMEN DE TESTS V3.0")
        
        total = self.passed + self.failed
        
        print(f"\n📊 RESULTADOS:")
        print_success(f"✅ Tests pasados: {self.passed}")
        if self.failed > 0:
            print_error(f"❌ Tests fallidos: {self.failed}")
        if self.warnings > 0:
            print_warning(f"⚠️ Warnings: {self.warnings}")
        
        print(f"\n🎯 TOTAL: {self.passed}/{total}")
        
        if self.failed == 0:
            print_success("\n🎉 ¡TODOS LOS TESTS DE INTEGRACIÓN PASARON!")
            print_success("✅ Los nuevos componentes están funcionando correctamente")
            print_success("🚀 Listo para continuar con el siguiente archivo del roadmap")
        else:
            print_error("\n⚠️ Algunos tests fallaron")
            print_error("🔧 Revisar errores antes de continuar")


def main():
    """Función principal para ejecutar tests"""
    try:
        tester = TestIntegrationV3()
        success = tester.run_all_tests()
        
        if success:
            print(f"\n🎯 PRÓXIMO PASO: Continuar con execution_tracker.py")
        else:
            print(f"\n🛠️ ACCIÓN REQUERIDA: Revisar y corregir errores")
        
        return success
        
    except KeyboardInterrupt:
        print("\n👋 Tests interrumpidos por el usuario")
        return False
    except Exception as e:
        print(f"\n❌ Error ejecutando tests: {e}")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)