#!/usr/bin/env python3
"""
🧪 TEST POSITION TRACKER - Validación del Sistema Unificado V3.0
================================================================

Tests completos para el sistema de tracking unificado de posiciones:
- Registro y gestión de posiciones
- Coordinación entre componentes  
- Health monitoring y auto-recovery
- Background tasks y threading
- Snapshots y métricas
- Batch operations

Ejecutar desde raíz del proyecto:
python tests/test_position_tracker.py
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
from position_management.position_tracker import (
    PositionTracker, get_position_tracker, reset_position_tracker,
    TrackingStatus, HealthStatus, RecoveryAction, PositionSnapshot, SystemHealthReport
)
from position_management.states import PositionStatus, SignalDirection, EntryStatus
from position_management.data_models import EnhancedPosition, create_execution_level
from position_management.state_manager import reset_state_manager
from position_management.execution_tracker import reset_execution_tracker  
from position_management.persistence_manager import reset_persistence_manager

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


class TestPositionTracker(unittest.TestCase):
    """Test suite para PositionTracker"""
    
    @classmethod
    def setUpClass(cls):
        """Setup una vez para toda la clase"""
        print_test("🚀 INICIANDO TESTS - POSITION TRACKER V3.0")
        cls.start_time = time.time()
    
    def setUp(self):
        """Setup para cada test"""
        # Reset todos los singletons para test limpio
        reset_position_tracker()
        reset_state_manager() 
        reset_execution_tracker()
        reset_persistence_manager()
        
        # Mock de componentes para evitar dependencias reales
        with patch('position_management.position_tracker.get_state_manager') as mock_state_mgr, \
             patch('position_management.position_tracker.get_execution_tracker') as mock_exec_tracker, \
             patch('position_management.position_tracker.get_persistence_manager') as mock_persist_mgr:
            
            # Configurar mocks
            mock_state_mgr.return_value = Mock()
            mock_exec_tracker.return_value = Mock()
            mock_persist_mgr.return_value = Mock()
            
            # Configurar comportamiento de mocks
            mock_state_mgr.return_value.register_position.return_value = True
            mock_state_mgr.return_value.update_position.return_value = True
            mock_state_mgr.return_value.get_position.return_value = None
            mock_state_mgr.return_value.ACTIVE_TRACKING_STATES = {
                PositionStatus.ENTRY_PENDING, PositionStatus.PARTIALLY_FILLED
            }
            mock_state_mgr.return_value.FINAL_STATES = {
                PositionStatus.CLOSED, PositionStatus.STOPPED_OUT
            }
            
            mock_persist_mgr.return_value.save_position.return_value = True
            mock_persist_mgr.return_value.get_position.return_value = None
            
            mock_exec_tracker.return_value.get_execution_metrics.return_value = Mock(
                avg_execution_time_ms=250, avg_slippage=0.02, fill_rate=95.0
            )
            mock_exec_tracker.return_value.get_execution_summary.return_value = {
                'system_health': 'GOOD', 'success_rate_24h': 92.0
            }
            
            # Crear tracker con mocks
            self.tracker = PositionTracker()
            
            # Posición de prueba
            self.test_position = EnhancedPosition(
                symbol="TEST_TRACKER",
                direction=SignalDirection.LONG,
                position_id=f"TEST_TRACK_{uuid.uuid4().hex[:8]}"
            )
    
    def tearDown(self):
        """Cleanup después de cada test"""
        if hasattr(self, 'tracker'):
            self.tracker.shutdown()
    
    def test_01_initialization(self):
        """Test 1: Inicialización del tracker"""
        print_test("TEST 1: Inicialización del PositionTracker")
        
        self.assertEqual(self.tracker.status, TrackingStatus.ACTIVE)
        self.assertEqual(self.tracker.health_status, HealthStatus.HEALTHY)
        self.assertEqual(len(self.tracker._active_positions), 0)
        self.assertEqual(len(self.tracker._position_snapshots), 0)
        
        # Verificar componentes integrados
        self.assertIsNotNone(self.tracker.state_manager)
        self.assertIsNotNone(self.tracker.execution_tracker)
        self.assertIsNotNone(self.tracker.persistence_manager)
        
        # Verificar background threads (mockeados, no se ejecutan realmente)
        self.assertIsNotNone(self.tracker._monitoring_thread)
        self.assertIsNotNone(self.tracker._health_check_thread)
        self.assertIsNotNone(self.tracker._snapshot_update_thread)
        
        print_success("Inicialización correcta")
    
    def test_02_register_position(self):
        """Test 2: Registro de posición"""
        print_test("TEST 2: Registro de posición")
        
        # Registrar posición
        success = self.tracker.register_position(self.test_position)
        self.assertTrue(success)
        
        # Verificar que se registró
        self.assertIn(self.test_position.position_id, self.tracker._active_positions)
        self.assertIn(self.test_position.position_id, self.tracker._position_snapshots)
        
        # Verificar stats
        self.assertEqual(self.tracker._stats['positions_registered'], 1)
        
        # Verificar snapshot creado
        snapshot = self.tracker._position_snapshots[self.test_position.position_id]
        self.assertEqual(snapshot.position_id, self.test_position.position_id)
        self.assertEqual(snapshot.symbol, self.test_position.symbol)
        self.assertTrue(snapshot.is_healthy)
        
        print_success("Registro de posición funcionando")
    
    def test_03_get_position(self):
        """Test 3: Obtención de posición"""
        print_test("TEST 3: Obtención de posición")
        
        # Registrar posición primero
        self.tracker.register_position(self.test_position)
        
        # Obtener posición registrada
        retrieved = self.tracker.get_position(self.test_position.position_id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.position_id, self.test_position.position_id)
        self.assertEqual(retrieved.symbol, self.test_position.symbol)
        
        # Intentar obtener posición no existente
        non_existent = self.tracker.get_position("NON_EXISTENT_ID")
        self.assertIsNone(non_existent)
        
        print_success("Obtención de posición funcionando")
    
    def test_04_update_position(self):
        """Test 4: Actualización de posición"""
        print_test("TEST 4: Actualización de posición")
        
        # Registrar posición
        self.tracker.register_position(self.test_position)
        
        # Modificar posición
        self.test_position.status = PositionStatus.PARTIALLY_FILLED
        
        # Actualizar
        success = self.tracker.update_position(self.test_position)
        self.assertTrue(success)
        
        # Verificar actualización
        updated = self.tracker.get_position(self.test_position.position_id)
        self.assertEqual(updated.status, PositionStatus.PARTIALLY_FILLED)
        
        # Verificar snapshot actualizado
        snapshot = self.tracker._position_snapshots[self.test_position.position_id]
        self.assertEqual(snapshot.status, PositionStatus.PARTIALLY_FILLED)
        
        print_success("Actualización de posición funcionando")
    
    def test_05_remove_position(self):
        """Test 5: Remoción de posición"""
        print_test("TEST 5: Remoción de posición")
        
        # Registrar posición
        self.tracker.register_position(self.test_position)
        self.assertIn(self.test_position.position_id, self.tracker._active_positions)
        
        # Remover posición
        success = self.tracker.remove_position(self.test_position.position_id, "test_completion")
        self.assertTrue(success)
        
        # Verificar remoción
        self.assertNotIn(self.test_position.position_id, self.tracker._active_positions)
        
        # Snapshot debe permanecer para historial
        self.assertIn(self.test_position.position_id, self.tracker._position_snapshots)
        
        # Verificar stats
        self.assertEqual(self.tracker._stats['positions_completed'], 1)
        
        print_success("Remoción de posición funcionando")
    
    def test_06_position_validation(self):
        """Test 6: Validación de posiciones"""
        print_test("TEST 6: Validación de posiciones")
        
        # Posición válida
        valid_position = EnhancedPosition(
            symbol="VALID", 
            direction=SignalDirection.LONG, 
            position_id="VALID_001"
        )
        
        is_valid = self.tracker._validate_position(valid_position)
        self.assertTrue(is_valid)
        
        # Posición inválida - sin position_id
        invalid_position1 = EnhancedPosition(
            symbol="INVALID",
            direction=SignalDirection.LONG,
            position_id=""  # Vacío
        )
        
        is_invalid1 = self.tracker._validate_position(invalid_position1)
        self.assertFalse(is_invalid1)
        
        # Posición inválida - sin symbol
        invalid_position2 = EnhancedPosition(
            symbol="",  # Vacío
            direction=SignalDirection.LONG,
            position_id="INVALID_002"
        )
        
        is_invalid2 = self.tracker._validate_position(invalid_position2)
        self.assertFalse(is_invalid2)
        
        print_success("Validación de posiciones funcionando")
    
    def test_07_position_snapshots(self):
        """Test 7: Creación y gestión de snapshots"""
        print_test("TEST 7: Position snapshots")
        
        # Crear posición con niveles de entrada
        position_with_levels = EnhancedPosition(
            symbol="SNAPSHOT_TEST",
            direction=SignalDirection.LONG,
            position_id="SNAPSHOT_001"
        )
        
        # Añadir niveles de entrada
        entry1 = create_execution_level(1, "ENTRY", 100.0, 50, 40.0, "Test entry 1")
        entry2 = create_execution_level(2, "ENTRY", 99.0, 30, 30.0, "Test entry 2")
        entry1.status = EntryStatus.FILLED
        entry1.executed_price = 100.05
        
        position_with_levels.entries = [entry1, entry2]
        
        # Crear snapshot
        snapshot = self.tracker._create_position_snapshot(position_with_levels)
        
        # Verificar snapshot
        self.assertEqual(snapshot.position_id, position_with_levels.position_id)
        self.assertEqual(snapshot.symbol, position_with_levels.symbol)
        self.assertEqual(snapshot.total_entry_levels, 2)
        self.assertEqual(snapshot.executed_entries, 1)
        self.assertEqual(snapshot.pending_entries, 1)
        self.assertTrue(snapshot.is_healthy)
        
        print_success("Position snapshots funcionando")
    
    def test_08_inconsistency_detection(self):
        """Test 8: Detección de inconsistencias"""
        print_test("TEST 8: Detección de inconsistencias")
        
        # Crear posición con inconsistencia
        inconsistent_position = EnhancedPosition(
            symbol="INCONSISTENT",
            direction=SignalDirection.LONG,
            position_id="INCONSISTENT_001"
        )
        
        # Crear inconsistencia: status FULLY_ENTERED pero con entradas pendientes
        inconsistent_position.status = PositionStatus.FULLY_ENTERED
        entry1 = create_execution_level(1, "ENTRY", 100.0, 50, 50.0, "Entry 1")
        entry2 = create_execution_level(2, "ENTRY", 99.0, 50, 50.0, "Entry 2")
        entry1.status = EntryStatus.FILLED
        entry2.status = EntryStatus.PENDING  # Pendiente pero status dice FULLY_ENTERED
        
        inconsistent_position.entries = [entry1, entry2]
        
        # Detectar inconsistencias
        inconsistencies = self.tracker._detect_position_inconsistencies(inconsistent_position)
        
        # Verificar detección
        self.assertGreater(len(inconsistencies), 0)
        self.assertTrue(any("FULLY_ENTERED pero hay entradas pendientes" in inc for inc in inconsistencies))
        
        print_success("Detección de inconsistencias funcionando")
    
    def test_09_health_check_system(self):
        """Test 9: Sistema de health check"""
        print_test("TEST 9: Sistema de health check")
        
        # Realizar health check
        health_report = self.tracker.perform_health_check()
        
        # Verificar reporte
        self.assertIsInstance(health_report, SystemHealthReport)
        self.assertIn(health_report.overall_status, [status for status in HealthStatus])
        self.assertGreaterEqual(health_report.total_positions, 0)
        self.assertGreaterEqual(health_report.active_positions, 0)
        self.assertIsInstance(health_report.critical_issues, list)
        self.assertIsInstance(health_report.warnings, list)
        
        # Stats deben incrementar
        initial_checks = self.tracker._stats['health_checks_performed']
        self.tracker.perform_health_check()
        self.assertEqual(self.tracker._stats['health_checks_performed'], initial_checks + 1)
        
        print_success("Sistema de health check funcionando")
    
    def test_10_batch_operations(self):
        """Test 10: Operaciones en batch"""
        print_test("TEST 10: Operaciones en batch")
        
        # Crear múltiples posiciones
        positions = []
        for i in range(3):
            pos = EnhancedPosition(
                symbol=f"BATCH_{i}",
                direction=SignalDirection.LONG,
                position_id=f"BATCH_POS_{i:03d}"
            )
            positions.append(pos)
        
        # Batch register
        results = self.tracker.batch_register_positions(positions)
        
        # Verificar resultados
        self.assertEqual(len(results), 3)
        self.assertTrue(all(results.values()))  # Todos exitosos
        
        # Verificar que se registraron
        for pos in positions:
            self.assertIn(pos.position_id, self.tracker._active_positions)
        
        # Modificar posiciones para batch update
        for pos in positions:
            pos.status = PositionStatus.PARTIALLY_FILLED
        
        # Batch update
        update_results = self.tracker.batch_update_positions(positions)
        
        # Verificar updates
        self.assertEqual(len(update_results), 3)
        self.assertTrue(all(update_results.values()))
        
        print_success("Operaciones en batch funcionando")
    
    def test_11_query_operations(self):
        """Test 11: Operaciones de consulta"""
        print_test("TEST 11: Operaciones de consulta")
        
        # Registrar posiciones de prueba
        positions = [
            EnhancedPosition("AAPL", SignalDirection.LONG, "QUERY_001"),
            EnhancedPosition("AAPL", SignalDirection.SHORT, "QUERY_002"), 
            EnhancedPosition("GOOGL", SignalDirection.LONG, "QUERY_003")
        ]
        positions[0].status = PositionStatus.PARTIALLY_FILLED
        positions[1].status = PositionStatus.CLOSED
        positions[2].status = PositionStatus.PARTIALLY_FILLED
        
        for pos in positions:
            self.tracker.register_position(pos)
        
        # Test get_active_positions
        active = self.tracker.get_active_positions()
        self.assertEqual(len(active), 3)
        
        # Test get_positions_by_symbol
        aapl_positions = self.tracker.get_positions_by_symbol("AAPL")
        self.assertEqual(len(aapl_positions), 2)
        
        # Test get_positions_by_status
        partially_filled = self.tracker.get_positions_by_status(PositionStatus.PARTIALLY_FILLED)
        self.assertEqual(len(partially_filled), 2)
        
        # Test get_position_snapshots
        snapshots = self.tracker.get_position_snapshots()
        self.assertEqual(len(snapshots), 3)
        
        print_success("Operaciones de consulta funcionando")
    
    def test_12_system_metrics(self):
        """Test 12: Métricas del sistema"""
        print_test("TEST 12: Métricas del sistema")
        
        # Registrar posiciones
        for i in range(5):
            pos = EnhancedPosition(
                symbol=f"METRICS_{i}",
                direction=SignalDirection.LONG,
                position_id=f"METRICS_POS_{i:03d}"
            )
            self.tracker.register_position(pos)
        
        # Obtener métricas
        metrics = self.tracker.get_system_metrics()
        
        # Verificar métricas básicas
        self.assertEqual(metrics.total_positions, 5)
        self.assertGreaterEqual(metrics.avg_fill_time_ms, 0)
        self.assertGreaterEqual(metrics.fill_rate, 0)
        self.assertIsInstance(metrics.symbol_breakdown, dict)
        
        # Verificar breakdown por símbolo
        self.assertEqual(len(metrics.symbol_breakdown), 5)  # 5 símbolos únicos
        
        print_success("Métricas del sistema funcionando")
    
    def test_13_tracker_stats(self):
        """Test 13: Estadísticas del tracker"""
        print_test("TEST 13: Estadísticas del tracker")
        
        # Registrar algunas posiciones
        for i in range(2):
            pos = EnhancedPosition(
                symbol=f"STATS_{i}",
                direction=SignalDirection.LONG,
                position_id=f"STATS_POS_{i:03d}"
            )
            self.tracker.register_position(pos)
        
        # Obtener stats
        stats = self.tracker.get_tracker_stats()
        
        # Verificar stats básicas
        self.assertEqual(stats['active_positions_count'], 2)
        self.assertEqual(stats['positions_registered'], 2)
        self.assertEqual(stats['status'], TrackingStatus.ACTIVE.value)
        self.assertIn('uptime_seconds', stats)
        self.assertIn('background_threads_alive', stats)
        
        print_success("Estadísticas del tracker funcionando")
    
    def test_14_export_summary(self):
        """Test 14: Export de resumen completo"""
        print_test("TEST 14: Export de resumen")
        
        # Registrar posición
        self.tracker.register_position(self.test_position)
        
        # Exportar summary
        summary = self.tracker.export_positions_summary()
        
        # Verificar estructura del summary
        self.assertIn('timestamp', summary)
        self.assertIn('tracker_stats', summary)
        self.assertIn('system_health', summary)
        self.assertIn('active_positions', summary)
        self.assertIn('position_snapshots', summary)
        self.assertIn('system_metrics', summary)
        
        # Verificar contenido
        self.assertEqual(len(summary['active_positions']), 1)
        self.assertEqual(len(summary['position_snapshots']), 1)
        
        print_success("Export de resumen funcionando")
    
    def test_15_observers_and_callbacks(self):
        """Test 15: Sistema de observers"""
        print_test("TEST 15: Sistema de observers")
        
        # Callbacks de prueba
        position_changes = []
        health_reports = []
        
        def position_callback(pos_id, position):
            position_changes.append((pos_id, position.symbol))
        
        def health_callback(report):
            health_reports.append(report.overall_status)
        
        # Añadir observers
        self.tracker.add_position_observer(position_callback)
        self.tracker.add_health_observer(health_callback)
        
        # Registrar posición (debería disparar callback)
        self.tracker.register_position(self.test_position)
        
        # Realizar health check (debería disparar callback)
        self.tracker.perform_health_check()
        
        # Verificar callbacks
        self.assertEqual(len(position_changes), 1)
        self.assertEqual(position_changes[0][0], self.test_position.position_id)
        self.assertEqual(position_changes[0][1], self.test_position.symbol)
        
        self.assertEqual(len(health_reports), 1)
        self.assertIsInstance(health_reports[0], HealthStatus)
        
        print_success("Sistema de observers funcionando")
    
    def test_16_shutdown_and_cleanup(self):
        """Test 16: Shutdown y cleanup"""
        print_test("TEST 16: Shutdown y cleanup")
        
        # Registrar posiciones
        for i in range(3):
            pos = EnhancedPosition(
                symbol=f"SHUTDOWN_{i}",
                direction=SignalDirection.LONG,
                position_id=f"SHUTDOWN_POS_{i:03d}"
            )
            self.tracker.register_position(pos)
        
        # Verificar estado activo
        self.assertEqual(self.tracker.status, TrackingStatus.ACTIVE)
        self.assertEqual(len(self.tracker._active_positions), 3)
        
        # Shutdown
        self.tracker.shutdown()
        
        # Verificar shutdown
        self.assertEqual(self.tracker.status, TrackingStatus.STOPPED)
        self.assertTrue(self.tracker._shutdown)
        
        # Snapshots finales deben existir
        self.assertEqual(len(self.tracker._position_snapshots), 3)
        
        print_success("Shutdown y cleanup funcionando")
    
    @classmethod
    def tearDownClass(cls):
        """Cleanup final y reporte"""
        total_time = time.time() - cls.start_time
        print("\n" + "=" * 80)
        print_test("🏁 RESUMEN TESTS POSITION TRACKER")
        print_success(f"⚡ Completado en {total_time:.2f} segundos")
        
        if total_time > 30:
            print_warning(f"⚠️ Tests tardaron {total_time:.2f}s (esperado <30s)")
        else:
            print_success("✅ Performance de tests aceptable")


def run_integration_test():
    """Test de integración rápido con componentes reales"""
    print_test("INTEGRATION TEST: Position Tracker + Componentes")
    
    try:
        # Reset todos los singletons
        reset_position_tracker()
        reset_state_manager()
        reset_execution_tracker() 
        reset_persistence_manager()
        
        # Crear tracker con componentes reales (mocked)
        with patch('position_management.position_tracker.PositionQueries') as mock_queries:
            mock_queries.return_value = Mock()
            
            tracker = get_position_tracker()
            
            # Test básico
            test_pos = EnhancedPosition(
                symbol="INTEGRATION_TEST",
                direction=SignalDirection.LONG,
                position_id="INTEG_001"
            )
            
            success = tracker.register_position(test_pos)
            print_success(f"✅ Registro: {'OK' if success else 'FAILED'}")
            
            retrieved = tracker.get_position("INTEG_001")
            print_success(f"✅ Retrieval: {'OK' if retrieved else 'FAILED'}")
            
            health = tracker.perform_health_check()
            print_success(f"✅ Health check: {health.overall_status.value}")
            
            # Shutdown
            tracker.shutdown()
            print_success("✅ Integration test completado")
    
    except Exception as e:
        print_error(f"❌ Integration test falló: {e}")
    
    finally:
        # Cleanup
        reset_position_tracker()


def main():
    """Ejecutar todos los tests"""
    print_test("TESTING POSITION TRACKER V3.0")
    print("=" * 80)
    
    # Crear test suite
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestPositionTracker)
    
    # Ejecutar tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Integration test adicional
    print("\n" + "=" * 80)
    run_integration_test()
    
    # Resumen final
    print("\n" + "=" * 80)
    print_test("RESUMEN DE TESTS")
    
    if result.wasSuccessful():
        print_success(f"🎉 TODOS LOS TESTS PASARON ({result.testsRun} tests)")
        print_success("✅ Position Tracker funcionando correctamente")
        print_success("🚀 Phase 3 - Componente central completado")
        print_success("📋 Listo para continuar con signal_processor.py")
    else:
        print_error(f"❌ {len(result.failures)} tests fallaron")
        print_error(f"❌ {len(result.errors)} errores encontrados")
        print_warning("🔧 Revisar y corregir errores antes de continuar")
    
    return result.wasSuccessful()


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)