#!/usr/bin/env python3
"""
🧪 TEST BÁSICO DE INTEGRACIÓN - Verificar que los 3 componentes funcionan juntos
==============================================================================

Prueba la integración entre:
- states.py (sistema de estados)
- data_models.py (estructuras de datos)  
- state_machine.py (lógica de transiciones)
"""

import sys
import os
from pathlib import Path

# Agregar el directorio padre al path para imports
parent_dir = Path(__file__).parent.parent
sys.path.insert(0, str(parent_dir))

from position_management.states import PositionStatus, SignalDirection, ExecutionType, EntryStatus
from position_management.data_models import EnhancedPosition, create_execution_level
from position_management.state_machine import PositionStateMachine, TransitionContext


def test_complete_lifecycle():
    """Test del ciclo completo de una posición"""
    print("🧪 TEST INTEGRACIÓN - Ciclo Completo")
    print("=" * 50)
    
    # 1. Crear componentes
    state_machine = PositionStateMachine()
    
    # 2. Crear posición
    position = EnhancedPosition(
        symbol="SPY",
        direction=SignalDirection.LONG,
        signal_strength=85,
        confidence_level="HIGH"
    )
    
    print(f"📊 Estado inicial: {position.status.value}")
    
    # 3. Agregar niveles de entrada
    entry1 = create_execution_level(1, ExecutionType.ENTRY, 450.0, 100, 40.0, "Breakout entry")
    entry2 = create_execution_level(2, ExecutionType.ENTRY, 449.0, 75, 30.0, "Pullback entry")
    entry3 = create_execution_level(3, ExecutionType.ENTRY, 448.0, 75, 30.0, "Support entry")
    
    position.entries = [entry1, entry2, entry3]
    
    print(f"📋 Niveles de entrada configurados: {len(position.entries)}")
    
    # 4. Transición a ENTRY_PENDING
    context = TransitionContext(trigger="signal_confirmed")
    result = state_machine.transition_to(position, PositionStatus.ENTRY_PENDING, context)
    print(f"✅ Transición 1: {result.value} -> {position.status.value}")
    
    # 5. Simular ejecución del primer nivel
    entry1.status = EntryStatus.FILLED
    entry1.executed_price = 450.05
    position.update_summary()
    
    print(f"💰 Primer nivel ejecutado: {entry1.quantity} shares a ${entry1.executed_price:.2f}")
    
    # 6. Transición automática
    recommended = state_machine.auto_evaluate_state(position)
    if recommended:
        context2 = TransitionContext(trigger="entry_execution", notes="Primer nivel ejecutado")
        result2 = state_machine.transition_to(position, recommended, context2)
        print(f"✅ Transición 2: {result2.value} -> {position.status.value}")
    else:
        print("🤖 Auto-evaluación: Estado actual es correcto")
    
    # 7. Simular ejecución del segundo nivel
    entry2.status = EntryStatus.FILLED
    entry2.executed_price = 449.10
    position.update_summary()
    
    print(f"💰 Segundo nivel ejecutado: {entry2.quantity} shares a ${entry2.executed_price:.2f}")
    
    # 8. Nueva evaluación automática
    recommended2 = state_machine.auto_evaluate_state(position)
    if recommended2:
        context3 = TransitionContext(trigger="additional_entry", notes="Segundo nivel ejecutado")
        result3 = state_machine.transition_to(position, recommended2, context3)
        print(f"✅ Transición 3: {result3.value} -> {position.status.value}")
    
    # 9. Mostrar resumen final
    print(f"\n📊 RESUMEN FINAL:")
    print(f"   Symbol: {position.symbol}")
    print(f"   Dirección: {position.direction.value}")
    print(f"   Estado: {position.status.value}")
    print(f"   Progreso: {position.summary.percent_filled:.1f}%")
    print(f"   Acciones totales: {position.summary.total_shares}")
    print(f"   Precio promedio: ${position.summary.average_entry_price:.2f}")
    print(f"   Inversión total: ${position.summary.total_invested:.2f}")
    print(f"   Historial: {len(position.state_history)} transiciones")
    
    # 10. Detalles de niveles
    print(f"\n📋 ESTADO DE NIVELES:")
    for i, entry in enumerate(position.entries, 1):
        status_icon = "✅" if entry.is_executed() else "⏳"
        price_info = f"${entry.executed_price:.2f}" if entry.executed_price else f"${entry.target_price:.2f} (target)"
        print(f"   {status_icon} Nivel {i}: {entry.quantity} shares @ {price_info}")
    
    # 11. Estadísticas del state machine
    stats = state_machine.get_statistics()
    print(f"\n🔄 STATE MACHINE STATS:")
    print(f"   Transiciones totales: {stats['total_transitions']}")
    print(f"   Transiciones fallidas: {stats['failed_transitions']}")
    print(f"   Tasa de éxito: {stats['success_rate']:.1f}%")
    print(f"   Auto-transiciones: {stats['auto_transitions']}")
    
    return True


def test_invalid_transitions():
    """Test de transiciones inválidas"""
    print("\n🧪 TEST TRANSICIONES INVÁLIDAS")
    print("=" * 40)
    
    state_machine = PositionStateMachine()
    position = EnhancedPosition(symbol="AAPL", direction=SignalDirection.SHORT)
    
    # Intentar transición inválida: SIGNAL_GENERATED -> CLOSED (sin entradas)
    context = TransitionContext(trigger="invalid_test")
    result = state_machine.transition_to(position, PositionStatus.CLOSED, context)
    
    print(f"❌ Transición inválida: {result.value}")
    print(f"📊 Estado se mantiene: {position.status.value}")
    
    return result.name == "INVALID_TRANSITION"


def test_state_validation():
    """Test de validación de estados"""
    print("\n🧪 TEST VALIDACIÓN DE ESTADOS")
    print("=" * 40)
    
    state_machine = PositionStateMachine()
    position = EnhancedPosition(symbol="TSLA", direction=SignalDirection.LONG)
    
    # Test: Verificar transición válida
    can_transition, reason = state_machine.can_transition(position, PositionStatus.ENTRY_PENDING)
    print(f"✅ Transición válida: {can_transition} - {reason}")
    
    # Test: Verificar transición inválida
    can_transition2, reason2 = state_machine.can_transition(position, PositionStatus.FULLY_ENTERED)
    print(f"❌ Transición inválida: {can_transition2} - {reason2}")
    
    return can_transition and not can_transition2


def run_all_tests():
    """Ejecutar todos los tests"""
    print("🚀 EJECUTANDO TODOS LOS TESTS DE INTEGRACIÓN")
    print("=" * 60)
    
    tests_passed = 0
    tests_total = 3
    
    try:
        # Test 1: Ciclo completo
        if test_complete_lifecycle():
            tests_passed += 1
            print("✅ Test 1 PASADO: Ciclo completo")
        else:
            print("❌ Test 1 FALLIDO: Ciclo completo")
    except Exception as e:
        print(f"💥 Test 1 ERROR: {e}")
    
    try:
        # Test 2: Transiciones inválidas
        if test_invalid_transitions():
            tests_passed += 1
            print("✅ Test 2 PASADO: Transiciones inválidas")
        else:
            print("❌ Test 2 FALLIDO: Transiciones inválidas")
    except Exception as e:
        print(f"💥 Test 2 ERROR: {e}")
    
    try:
        # Test 3: Validación de estados
        if test_state_validation():
            tests_passed += 1
            print("✅ Test 3 PASADO: Validación de estados")
        else:
            print("❌ Test 3 FALLIDO: Validación de estados")
    except Exception as e:
        print(f"💥 Test 3 ERROR: {e}")
    
    # Resultado final
    print(f"\n📊 RESULTADO FINAL: {tests_passed}/{tests_total} tests pasados")
    
    if tests_passed == tests_total:
        print("🎉 ¡TODOS LOS TESTS PASARON!")
        print("✅ La integración básica funciona correctamente")
        print("🚀 Listo para continuar con más componentes")
        return True
    else:
        print("⚠️ Algunos tests fallaron")
        print("🔧 Revisar problemas antes de continuar")
        return False


if __name__ == "__main__":
    success = run_all_tests()
    
    if success:
        print(f"\n🎯 PRÓXIMO PASO: Continuar con más archivos del roadmap")
    else:
        print(f"\n🛠️ ACCIÓN REQUERIDA: Revisar y corregir errores")