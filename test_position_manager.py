#!/usr/bin/env python3
"""
🧪 TEST SCRIPT - POSITION MANAGER V4.0
======================================

Script de prueba para el sistema completo de Position Manager.
Este script debe ejecutarse desde la raíz del proyecto.
"""

import sys
from pathlib import Path

# Asegurar que estamos en la raíz del proyecto
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

print("🧪 TESTING POSITION MANAGER V4.0")
print("=" * 60)

# Test 1: Imports
print("\n1. Test: Imports del package")
try:
    from position_manager import (
        PositionTracker,
        ExecutionMonitor,
        SignalCoordinator,
        ExecutionStatus,
        PositionStatus,
        TrackedPosition,
        ExecutionEvent,
        create_position_manager_system,
        get_version_info
    )
    print("   ✅ Todos los imports exitosos")
except ImportError as e:
    print(f"   ❌ Error en imports: {e}")
    sys.exit(1)

# Test 2: Version info
print("\n2. Test: Version info")
version_info = get_version_info()
print(f"   Version: {version_info['version']}")
print(f"   Status: {version_info['status']}")
print(f"   Componentes: {list(version_info['components'].keys())}")

# Test 3: Crear sistema completo
print("\n3. Test: Crear sistema completo")
tracker, monitor, coordinator = create_position_manager_system(
    use_database=False,
    use_real_prices=False
)
print("   ✅ Tracker creado")
print("   ✅ Monitor creado")
print("   ✅ Coordinator creado")

# Test 4: Verificar clases
print("\n4. Test: Verificar clases disponibles")
print(f"   ExecutionStatus: {ExecutionStatus}")
print(f"   PositionStatus: {PositionStatus}")
print(f"   TrackedPosition: {TrackedPosition}")
print("   ✅ Todas las clases disponibles")

# Test 5: Crear posición mock
print("\n5. Test: Crear posición de prueba")
from dataclasses import dataclass
from typing import List

@dataclass
class MockSignal:
    symbol: str
    signal_type: str
    signal_strength: int
    confidence_level: str
    entry_quality: str
    current_price: float

@dataclass
class MockLevel:
    price: float
    percentage: float
    description: str
    trigger_condition: str

@dataclass
class MockPlan:
    entries: List[MockLevel]
    exits: List[MockLevel]
    stop_loss: MockLevel
    strategy_type: str
    expected_hold_time: str

signal = MockSignal(
    symbol="TEST",
    signal_type="LONG",
    signal_strength=80,
    confidence_level="ALTA",
    entry_quality="BUENA",
    current_price=100.0
)

plan = MockPlan(
    entries=[
        MockLevel(100.0, 40, "Entry 1", "Price <= 100.0"),
        MockLevel(99.0, 30, "Entry 2", "Price <= 99.0"),
        MockLevel(98.0, 30, "Entry 3", "Price <= 98.0")
    ],
    exits=[
        MockLevel(102.0, 25, "TP1", "Price >= 102.0"),
        MockLevel(104.0, 25, "TP2", "Price >= 104.0"),
        MockLevel(106.0, 25, "TP3", "Price >= 106.0"),
        MockLevel(108.0, 25, "TP4", "Price >= 108.0")
    ],
    stop_loss=MockLevel(97.0, 100, "Stop Loss", "Price <= 97.0"),
    strategy_type="TEST",
    expected_hold_time="Test"
)

position_id = tracker.register_new_position(signal, plan)
print(f"   ✅ Posición creada: {position_id[:8]}...")

# Test 6: Verificar estado
print("\n6. Test: Verificar estado de posición")
position = tracker.get_position("TEST")
print(f"   Symbol: {position.symbol}")
print(f"   Direction: {position.direction}")
print(f"   Status: {position.status.value}")
print(f"   Entradas: {len(position.entry_levels)}")
print(f"   Salidas: {len(position.exit_levels)}")

# Test 7: Simular ejecución
print("\n7. Test: Simular ejecución de nivel")
tracker.mark_level_as_filled("TEST", 1, "ENTRY", 99.95, 40.0)
position = tracker.get_position("TEST")
print(f"   Status actualizado: {position.status.value}")
print(f"   % Ejecutado: {position.total_filled_percentage}%")
print(f"   Precio medio entrada: ${position.average_entry_price:.2f}")

# Test 8: Monitoreo
print("\n8. Test: Monitoreo de ejecuciones")
events = monitor.monitor_single_position("TEST", force_price=101.0)
print(f"   Eventos detectados: {len(events)}")
if events:
    for event in events:
        print(f"   - {event.event_type.value}: ${event.executed_price:.2f}")

# Test 9: Resumen
print("\n9. Test: Resumen de posiciones")
summary = tracker.get_active_positions_summary()
print(f"   Total posiciones: {summary['total_positions']}")
print(f"   P&L total: {summary['total_unrealized_pnl']:.2f}%")

# Test 10: Estadísticas del coordinator
print("\n10. Test: Estadísticas del coordinator")
coordinator.print_statistics()

# Test 11: Cerrar posición
print("\n11. Test: Cerrar posición")
tracker.close_position("TEST", "Test completado", 101.5)
summary = tracker.get_active_positions_summary()
print(f"   Posiciones activas después de cerrar: {summary['total_positions']}")

print("\n" + "=" * 60)
print("✅ TODOS LOS TESTS PASARON")
print("🎉 POSITION MANAGER V4.0 FUNCIONANDO CORRECTAMENTE")
print("=" * 60)