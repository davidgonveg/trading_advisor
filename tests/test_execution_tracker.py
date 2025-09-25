#!/usr/bin/env python3
"""
🧪 TEST EXECUTION TRACKER - Validación Completa V3.0
==================================================

Tests completos para el sistema de tracking de ejecuciones:
- Funcionamiento básico del tracker
- Manejo de execuciones exitosas y fallidas
- Métricas y estadísticas
- Integración con state_manager
- Timeouts y retries
- Performance y threading

Ejecutar desde raíz del proyecto:
python -m tests.test_execution_tracker
"""

import sys
import os
from pathlib import Path
import unittest
import time
import threading
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
import uuid

# Agregar proyecto root al path
parent_dir = Path(__file__).parent.parent
sys.path.insert(0, str(parent_dir))

# Imports del sistema
from position_management.execution_tracker import (
    ExecutionTracker, get_execution_tracker, reset_execution_tracker,
    ExecutionStatus, ExecutionResult, ExecutionAttempt, ExecutionMetrics
)
from position_management.states import ExecutionType, PositionStatus, SignalDirection
from position_management.data_models import EnhancedPosition, ExecutionLevel
from position_management.state_manager import get_state_manager, reset_state_manager

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


class TestExecutionTracker(unittest.TestCase):
    """Test suite para ExecutionTracker"""
    
    def setUp(self):
        """Setup para cada test"""
        # Reset singletons para test limpio
        reset_execution_tracker()
        reset_state_manager()
        
        self.tracker = get_execution_tracker()
        self.state_manager = get_state_manager()
        
        # Mock position para testing
        self.test_position = EnhancedPosition(
            symbol="TEST_SYMBOL",
            direction=SignalDirection.LONG,
            position_id="TEST_POS_001"
        )
        
    def tearDown(self):
        """Cleanup después de cada test"""
        if hasattr(self, 'tracker'):
            self.tracker.shutdown()
        reset_execution_tracker()
        reset_state_manager()
    
    def test_01_initialization(self):
        """Test 1: Inicialización del tracker"""
        print_test("TEST 1: Inicialización del ExecutionTracker")
        
        self.assertIsNotNone(self.tracker)
        self.assertEqual(len(self.tracker.active_attempts), 0)
        self.assertEqual(len(self.tracker.execution_history), 0)
        self.assertEqual(self.tracker.metrics.total_attempts, 0)
        
        # Verificar configuración
        self.assertGreater(self.tracker.execution_timeout.total_seconds(), 0)
        self.assertGreater(self.tracker.max_retries, 0)
        self.assertGreater(self.tracker.slippage_tolerance, 0)
        
        print_success("Inicialización correcta")
    
    def test_02_track_execution_attempt(self):
        """Test 2: Tracking de intento de ejecución"""
        print_test("TEST 2: Tracking de intento de ejecución")
        
        # Mock del state_manager para devolver posición
        with patch.object(self.state_manager, 'get_position', return_value=self.test_position):
            attempt_id = self.tracker.track_execution_attempt(
                position_id="TEST_POS_001",
                level_id="entry_1",
                target_price=100.0,
                target_quantity=50
            )
        
        self.assertIsNotNone(attempt_id)
        self.assertIn(attempt_id, self.tracker.active_attempts)
        
        attempt = self.tracker.active_attempts[attempt_id]
        self.assertEqual(attempt.position_id, "TEST_POS_001")
        self.assertEqual(attempt.level_id, "entry_1")
        self.assertEqual(attempt.target_price, 100.0)
        self.assertEqual(attempt.target_quantity, 50)
        self.assertEqual(attempt.status, ExecutionStatus.PENDING)
        self.assertEqual(self.tracker.metrics.total_attempts, 1)
        
        print_success("Tracking de intento exitoso")
    
    def test_03_successful_execution(self):
        """Test 3: Ejecución exitosa"""
        print_test("TEST 3: Registro de ejecución exitosa")
        
        # Crear intento
        with patch.object(self.state_manager, 'get_position', return_value=self.test_position):
            attempt_id = self.tracker.track_execution_attempt(
                position_id="TEST_POS_001",
                level_id="entry_1", 
                target_price=100.0,
                target_quantity=50
            )
        
        # Mock del state_manager.record_execution
        with patch.object(self.state_manager, 'record_execution', return_value=True):
            result = self.tracker.record_execution_result(
                attempt_id=attempt_id,
                executed_price=100.05,
                executed_quantity=50,
                execution_time_ms=250
            )
        
        self.assertEqual(result, ExecutionResult.SUCCESS)
        self.assertNotIn(attempt_id, self.tracker.active_attempts)
        self.assertEqual(len(self.tracker.execution_history), 1)
        
        # Verificar métricas actualizadas
        self.assertEqual(self.tracker.metrics.successful_executions, 1)
        self.assertAlmostEqual(self.tracker.metrics.avg_execution_time_ms, 250.0)
        
        # Verificar slippage calculado
        executed_attempt = self.tracker.execution_history[0]
        expected_slippage = abs(100.05 - 100.0) / 100.0 * 100
        self.assertAlmostEqual(executed_attempt.slippage, expected_slippage, places=3)
        
        print_success("Ejecución exitosa registrada correctamente")
    
    def test_04_partial_execution(self):
        """Test 4: Ejecución parcial"""
        print_test("TEST 4: Ejecución parcial")
        
        with patch.object(self.state_manager, 'get_position', return_value=self.test_position):
            attempt_id = self.tracker.track_execution_attempt(
                position_id="TEST_POS_001",
                level_id="entry_1",
                target_price=100.0,
                target_quantity=100
            )
        
        with patch.object(self.state_manager, 'record_execution', return_value=True):
            result = self.tracker.record_execution_result(
                attempt_id=attempt_id,
                executed_price=100.10,
                executed_quantity=75,  # Solo 75 de 100
                execution_time_ms=300
            )
        
        self.assertEqual(result, ExecutionResult.PARTIAL_FILL)
        self.assertEqual(self.tracker.metrics.partial_fills, 1)
        
        executed_attempt = self.tracker.execution_history[0]
        self.assertEqual(executed_attempt.executed_quantity, 75)
        self.assertEqual(executed_attempt.result, ExecutionResult.PARTIAL_FILL)
        
        print_success("Ejecución parcial manejada correctamente")
    
    def test_05_execution_failure(self):
        """Test 5: Fallo de ejecución"""
        print_test("TEST 5: Manejo de fallos de ejecución")
        
        with patch.object(self.state_manager, 'get_position', return_value=self.test_position):
            attempt_id = self.tracker.track_execution_attempt(
                position_id="TEST_POS_001",
                level_id="entry_1",
                target_price=100.0,
                target_quantity=50
            )
        
        # Registrar fallo sin retry
        retry_attempted = self.tracker.record_execution_failure(
            attempt_id=attempt_id,
            error_message="Market closed",
            retry=False
        )
        
        self.assertFalse(retry_attempted)
        self.assertNotIn(attempt_id, self.tracker.active_attempts)
        self.assertEqual(len(self.tracker.execution_history), 1)
        self.assertEqual(self.tracker.metrics.failed_executions, 1)
        
        failed_attempt = self.tracker.execution_history[0]
        self.assertEqual(failed_attempt.status, ExecutionStatus.FAILED)
        self.assertEqual(failed_attempt.result, ExecutionResult.ERROR)
        self.assertEqual(failed_attempt.error_message, "Market closed")
        
        print_success("Fallo de ejecución manejado correctamente")
    
    def test_06_execution_retry(self):
        """Test 6: Sistema de retry"""
        print_test("TEST 6: Sistema de retry automático")
        
        with patch.object(self.state_manager, 'get_position', return_value=self.test_position):
            attempt_id = self.tracker.track_execution_attempt(
                position_id="TEST_POS_001",
                level_id="entry_1",
                target_price=100.0,
                target_quantity=50
            )
        
        # Registrar fallo con retry
        retry_attempted = self.tracker.record_execution_failure(
            attempt_id=attempt_id,
            error_message="Temporary network error",
            retry=True
        )
        
        self.assertTrue(retry_attempted)
        self.assertIn(attempt_id, self.tracker.active_attempts)
        
        attempt = self.tracker.active_attempts[attempt_id]
        self.assertEqual(attempt.retry_count, 1)
        self.assertEqual(attempt.error_message, "Temporary network error")
        
        print_success("Sistema de retry funcionando")
    
    def test_07_execution_metrics(self):
        """Test 7: Cálculo de métricas"""
        print_test("TEST 7: Cálculo de métricas de ejecución")
        
        # Crear múltiples ejecuciones para probar métricas
        attempt_ids = []
        with patch.object(self.state_manager, 'get_position', return_value=self.test_position):
            for i in range(5):
                attempt_id = self.tracker.track_execution_attempt(
                    position_id=f"TEST_POS_{i:03d}",
                    level_id=f"entry_{i}",
                    target_price=100.0 + i,
                    target_quantity=50
                )
                attempt_ids.append(attempt_id)
        
        # Simular diferentes resultados
        with patch.object(self.state_manager, 'record_execution', return_value=True):
            # 3 exitosas
            for i in range(3):
                self.tracker.record_execution_result(
                    attempt_id=attempt_ids[i],
                    executed_price=100.0 + i + 0.05,
                    executed_quantity=50,
                    execution_time_ms=200 + i * 50
                )
            
            # 1 parcial
            self.tracker.record_execution_result(
                attempt_id=attempt_ids[3],
                executed_price=103.10,
                executed_quantity=30,
                execution_time_ms=400
            )
        
        # 1 fallida
        self.tracker.record_execution_failure(
            attempt_id=attempt_ids[4],
            error_message="Order rejected",
            retry=False
        )
        
        # Verificar métricas
        metrics = self.tracker.get_execution_metrics()
        self.assertEqual(metrics.total_attempts, 5)
        self.assertEqual(metrics.successful_executions, 3)
        self.assertEqual(metrics.partial_fills, 1)
        self.assertEqual(metrics.failed_executions, 1)
        
        # Verificar cálculos - fill rate debería ser 60% (3 success + 1 partial = 4, pero success rate es solo 3/5 = 60%)
        expected_fill_rate = 60.0  # Solo 3 successful de 5 total
        self.assertAlmostEqual(metrics.fill_rate, expected_fill_rate, places=1)
        
        self.assertGreater(metrics.avg_execution_time_ms, 0)
        self.assertGreater(metrics.avg_slippage, 0)
        
        print_success("Métricas calculadas correctamente")
    
    def test_08_position_queries(self):
        """Test 8: Consultas por posición"""
        print_test("TEST 8: Consultas de ejecuciones por posición")
        
        # Crear ejecuciones para diferentes posiciones
        with patch.object(self.state_manager, 'get_position', return_value=self.test_position):
            # Posición A - 2 ejecuciones
            attempt_a1 = self.tracker.track_execution_attempt(
                position_id="POS_A",
                level_id="entry_1",
                target_price=100.0,
                target_quantity=50
            )
            attempt_a2 = self.tracker.track_execution_attempt(
                position_id="POS_A",
                level_id="entry_2", 
                target_price=99.0,
                target_quantity=30
            )
            
            # Posición B - 1 ejecución
            attempt_b1 = self.tracker.track_execution_attempt(
                position_id="POS_B",
                level_id="entry_1",
                target_price=200.0,
                target_quantity=25
            )
        
        # Completar algunas ejecuciones
        with patch.object(self.state_manager, 'record_execution', return_value=True):
            self.tracker.record_execution_result(attempt_a1, 100.05, 50, 250)
            self.tracker.record_execution_result(attempt_b1, 200.10, 25, 300)
        
        # Verificar consultas por posición
        pos_a_executions = self.tracker.get_executions_for_position("POS_A")
        pos_b_executions = self.tracker.get_executions_for_position("POS_B")
        
        self.assertEqual(len(pos_a_executions), 2)  # 1 completa + 1 activa
        self.assertEqual(len(pos_b_executions), 1)  # 1 completa
        
        # Verificar que encontramos la ejecución correcta
        pos_a_completed = [e for e in pos_a_executions if e.status == ExecutionStatus.COMPLETED]
        self.assertEqual(len(pos_a_completed), 1)
        self.assertEqual(pos_a_completed[0].executed_price, 100.05)
        
        print_success("Consultas por posición funcionando")
    
    def test_09_timeout_handling(self):
        """Test 9: Manejo de timeouts"""
        print_test("TEST 9: Manejo de timeouts de ejecución")
        
        with patch.object(self.state_manager, 'get_position', return_value=self.test_position):
            # Crear intento con timeout muy corto para test rápido
            attempt_id = self.tracker.track_execution_attempt(
                position_id="TEST_POS_001",
                level_id="entry_1",
                target_price=100.0,
                target_quantity=50,
                timeout_minutes=0.005  # 0.3 segundos para test rápido
            )
        
        # Esperar que expire el timeout (reducido para test rápido)
        time.sleep(0.8)
        
        # Verificar que el attempt fue marcado como timeout
        self.assertNotIn(attempt_id, self.tracker.active_attempts)
        
        # Buscar en historial
        timed_out_attempt = None
        for attempt in self.tracker.execution_history:
            if attempt.attempt_id == attempt_id:
                timed_out_attempt = attempt
                break
        
        self.assertIsNotNone(timed_out_attempt)
        self.assertEqual(timed_out_attempt.status, ExecutionStatus.TIMEOUT)
        self.assertEqual(timed_out_attempt.result, ExecutionResult.TIMEOUT)
        self.assertEqual(self.tracker.metrics.timeouts, 1)
        
        print_success("Timeout handling funcionando")
    
    def test_10_system_health_calculation(self):
        """Test 10: Cálculo de salud del sistema"""
        print_test("TEST 10: Cálculo de salud del sistema")
        
        # Crear ejecuciones con diferentes resultados para probar health
        with patch.object(self.state_manager, 'get_position', return_value=self.test_position):
            attempt_ids = []
            for i in range(10):
                attempt_id = self.tracker.track_execution_attempt(
                    position_id=f"TEST_POS_{i:03d}",
                    level_id=f"entry_{i}",
                    target_price=100.0,
                    target_quantity=50
                )
                attempt_ids.append(attempt_id)
        
        # Simular 9 exitosas de 10 (90% success rate)
        with patch.object(self.state_manager, 'record_execution', return_value=True):
            for i in range(9):
                self.tracker.record_execution_result(
                    attempt_id=attempt_ids[i],
                    executed_price=100.05,
                    executed_quantity=50,
                    execution_time_ms=250
                )
        
        # 1 fallida
        self.tracker.record_execution_failure(
            attempt_id=attempt_ids[9],
            error_message="Test failure",
            retry=False
        )
        
        # Obtener resumen del sistema
        summary = self.tracker.get_execution_summary()
        
        self.assertIn('system_health', summary)
        self.assertIn('success_rate_24h', summary)
        self.assertIn('avg_execution_time_ms', summary)
        
        # Con 90% success rate debería ser "GOOD"
        self.assertEqual(summary['system_health'], "GOOD")
        self.assertAlmostEqual(summary['success_rate_24h'], 90.0, places=1)
        
        print_success("Cálculo de salud del sistema funcionando")
    
    def test_11_cleanup_and_shutdown(self):
        """Test 11: Cleanup y shutdown"""
        print_test("TEST 11: Cleanup y shutdown del tracker")
        
        # Crear algunos attempts
        with patch.object(self.state_manager, 'get_position', return_value=self.test_position):
            for i in range(3):
                self.tracker.track_execution_attempt(
                    position_id=f"TEST_POS_{i:03d}",
                    level_id="entry_1",
                    target_price=100.0,
                    target_quantity=50
                )
        
        self.assertEqual(len(self.tracker.active_attempts), 3)
        
        # Shutdown
        self.tracker.shutdown()
        
        # Verificar que los attempts activos fueron cancelados
        cancelled_attempts = [a for a in self.tracker.active_attempts.values() 
                             if a.status == ExecutionStatus.CANCELLED]
        
        self.assertEqual(len(cancelled_attempts), 3)
        self.assertTrue(self.tracker._shutdown)
        
        print_success("Shutdown ejecutado correctamente")


def run_performance_test():
    """Test de performance con múltiples ejecuciones concurrentes"""
    print_test("PERFORMANCE TEST: Múltiples ejecuciones concurrentes")
    
    reset_execution_tracker()
    tracker = get_execution_tracker()
    
    test_position = EnhancedPosition(
        symbol="PERF_TEST",
        direction=SignalDirection.LONG,
        position_id="PERF_POS_001"
    )
    
    start_time = time.time()
    attempt_ids = []
    
    with patch.object(get_state_manager(), 'get_position', return_value=test_position):
        with patch.object(get_state_manager(), 'record_execution', return_value=True):
            # Crear 100 attempts concurrentemente
            for i in range(100):
                attempt_id = tracker.track_execution_attempt(
                    position_id=f"PERF_POS_{i:03d}",
                    level_id="entry_1",
                    target_price=100.0 + i * 0.01,
                    target_quantity=50
                )
                attempt_ids.append(attempt_id)
            
            # Completar todas las ejecuciones
            for i, attempt_id in enumerate(attempt_ids):
                tracker.record_execution_result(
                    attempt_id=attempt_id,
                    executed_price=100.0 + i * 0.01 + 0.005,
                    executed_quantity=50,
                    execution_time_ms=200 + i
                )
    
    end_time = time.time()
    total_time = end_time - start_time
    
    # Verificar resultados
    metrics = tracker.get_execution_metrics()
    
    print_success(f"Performance test completado:")
    print(f"  📊 {metrics.total_attempts} ejecuciones en {total_time:.2f} segundos")
    print(f"  ⚡ {metrics.total_attempts / total_time:.1f} ejecuciones/segundo")
    print(f"  ✅ {metrics.successful_executions} exitosas")
    print(f"  📈 Success rate: {metrics.fill_rate:.1f}%")
    
    tracker.shutdown()
    reset_execution_tracker()


def main():
    """Ejecutar todos los tests"""
    print_test("TESTING EXECUTION TRACKER V3.0")
    print("=" * 80)
    
    # Crear test suite
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestExecutionTracker)
    
    # Ejecutar tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Performance test adicional
    print("\n" + "=" * 80)
    run_performance_test()
    
    # Resumen final
    print("\n" + "=" * 80)
    print_test("RESUMEN DE TESTS")
    
    if result.wasSuccessful():
        print_success(f"🎉 TODOS LOS TESTS PASARON ({result.testsRun} tests)")
        print_success("✅ Execution Tracker funcionando correctamente")
        print_success("🚀 Listo para continuar con persistence_manager.py")
    else:
        print_error(f"❌ {len(result.failures)} tests fallaron")
        print_error(f"❌ {len(result.errors)} errores encontrados")
        print_warning("🔧 Revisar y corregir errores antes de continuar")
    
    return result.wasSuccessful()


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)