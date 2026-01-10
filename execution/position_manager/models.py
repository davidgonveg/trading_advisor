#!/usr/bin/env python3
"""
📊 POSITION MANAGER MODELS V4.0
================================

Dataclasses y Enums compartidos para el sistema de Position Management.

Estos modelos representan el estado completo de posiciones en seguimiento,
incluyendo niveles de entrada/salida y eventos de ejecución.
"""

from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
from typing import Optional, List, Dict, Any
import json


# =============================================================================
# 🎯 ENUMS - Estados y Tipos
# =============================================================================

class ExecutionStatus(Enum):
    """Estados posibles de un nivel de entrada/salida"""
    PENDING = "PENDING"           # Esperando ejecución
    FILLED = "FILLED"             # Ejecutado completamente
    PARTIALLY_FILLED = "PARTIALLY_FILLED"  # Parcialmente ejecutado
    CANCELLED = "CANCELLED"       # Cancelado por usuario/sistema
    SKIPPED = "SKIPPED"          # Saltado (precio pasó sin ejecutar)
    EXPIRED = "EXPIRED"          # Expiró sin ejecutarse


class PositionStatus(Enum):
    """Estados posibles de una posición completa"""
    PENDING = "PENDING"                    # Esperando primera entrada
    PARTIALLY_FILLED = "PARTIALLY_FILLED"  # Algunas entradas ejecutadas
    FULLY_ENTERED = "FULLY_ENTERED"        # Todas las entradas completas
    EXITING = "EXITING"                    # Empezando a salir
    CLOSED = "CLOSED"                      # Posición cerrada completamente
    STOPPED = "STOPPED"                    # Cerrada por stop loss


class ExecutionEventType(Enum):
    """Tipos de eventos de ejecución"""
    ENTRY_FILLED = "ENTRY_FILLED"
    EXIT_FILLED = "EXIT_FILLED"
    STOP_HIT = "STOP_HIT"
    TRAILING_STOP_HIT = "TRAILING_STOP_HIT"
    MANUAL_CLOSE = "MANUAL_CLOSE"
    LEVEL_SKIPPED = "LEVEL_SKIPPED"


# =============================================================================
# 📊 DATACLASSES - Estados de Niveles
# =============================================================================

@dataclass
class EntryLevelStatus:
    """
    Estado de un nivel de entrada específico
    
    Representa cada uno de los niveles de entrada escalonados
    (típicamente 3 niveles: 40%, 30%, 30%)
    """
    level_id: int                          # 1, 2, 3
    target_price: float                    # Precio objetivo
    percentage: float                      # % del capital total
    status: ExecutionStatus                # Estado actual
    
    # Información de ejecución (si aplica)
    filled_price: Optional[float] = None
    filled_timestamp: Optional[datetime] = None
    filled_percentage: float = 0.0         # % realmente ejecutado
    
    # Metadatos
    description: str = ""
    trigger_condition: str = ""            # Ej: "Precio <= 100.50"
    notes: str = ""
    
    def is_executed(self) -> bool:
        """Check si este nivel ya se ejecutó"""
        return self.status in [ExecutionStatus.FILLED, ExecutionStatus.PARTIALLY_FILLED]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertir a diccionario para persistencia"""
        return {
            'level_id': self.level_id,
            'target_price': self.target_price,
            'percentage': self.percentage,
            'status': self.status.value,
            'filled_price': self.filled_price,
            'filled_timestamp': self.filled_timestamp.isoformat() if self.filled_timestamp else None,
            'filled_percentage': self.filled_percentage,
            'description': self.description,
            'trigger_condition': self.trigger_condition,
            'notes': self.notes
        }


@dataclass
class ExitLevelStatus:
    """
    Estado de un nivel de salida específico
    
    Similar a EntryLevelStatus pero para take profits
    (típicamente 4 niveles: 25%, 25%, 25%, 25%)
    """
    level_id: int                          # 1, 2, 3, 4
    target_price: float                    # Precio objetivo
    percentage: float                      # % de la posición
    status: ExecutionStatus                # Estado actual
    
    # Información de ejecución (si aplica)
    filled_price: Optional[float] = None
    filled_timestamp: Optional[datetime] = None
    filled_percentage: float = 0.0
    
    # Metadatos
    risk_reward_ratio: Optional[float] = None  # R:R de este nivel
    description: str = ""
    trigger_condition: str = ""
    notes: str = ""
    
    def is_executed(self) -> bool:
        """Check si este nivel ya se ejecutó"""
        return self.status in [ExecutionStatus.FILLED, ExecutionStatus.PARTIALLY_FILLED]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertir a diccionario para persistencia"""
        return {
            'level_id': self.level_id,
            'target_price': self.target_price,
            'percentage': self.percentage,
            'status': self.status.value,
            'filled_price': self.filled_price,
            'filled_timestamp': self.filled_timestamp.isoformat() if self.filled_timestamp else None,
            'filled_percentage': self.filled_percentage,
            'risk_reward_ratio': self.risk_reward_ratio,
            'description': self.description,
            'trigger_condition': self.trigger_condition,
            'notes': self.notes
        }


@dataclass
class StopLevelStatus:
    """
    Estado del stop loss
    
    Puede ser fijo o trailing
    """
    target_price: float                    # Precio del stop
    status: ExecutionStatus                # Estado actual
    stop_type: str = "FIXED"               # 'FIXED' o 'TRAILING'
    
    # Información de ejecución (si aplica)
    filled_price: Optional[float] = None
    filled_timestamp: Optional[datetime] = None
    
    # Para trailing stops
    trailing_offset: Optional[float] = None  # Distancia del precio actual
    highest_price: Optional[float] = None    # Precio más alto alcanzado (LONG)
    lowest_price: Optional[float] = None     # Precio más bajo alcanzado (SHORT)
    
    # Metadatos
    description: str = ""
    trigger_condition: str = ""
    notes: str = ""
    
    def is_hit(self) -> bool:
        """Check si el stop fue tocado"""
        return self.status == ExecutionStatus.FILLED
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertir a diccionario para persistencia"""
        return {
            'target_price': self.target_price,
            'status': self.status.value,
            'stop_type': self.stop_type,
            'filled_price': self.filled_price,
            'filled_timestamp': self.filled_timestamp.isoformat() if self.filled_timestamp else None,
            'trailing_offset': self.trailing_offset,
            'highest_price': self.highest_price,
            'lowest_price': self.lowest_price,
            'description': self.description,
            'trigger_condition': self.trigger_condition,
            'notes': self.notes
        }


# =============================================================================
# 🎯 DATACLASSES - Posición Completa
# =============================================================================

@dataclass
class TrackedPosition:
    """
    Posición completa bajo seguimiento activo
    
    Esta es la clase principal que representa una posición desde
    que se envía la señal hasta que se cierra completamente.
    """
    # Identificación
    position_id: str                       # UUID único
    symbol: str
    direction: str                         # 'LONG' o 'SHORT'
    
    # Información original de la señal
    signal_timestamp: datetime
    signal_strength: int                   # 0-100
    original_plan: Any                     # PositionPlan del position_calculator
    
    # Estado de ejecución - Niveles
    entry_levels: List[EntryLevelStatus] = field(default_factory=list)
    exit_levels: List[ExitLevelStatus] = field(default_factory=list)
    stop_loss: Optional[StopLevelStatus] = None
    
    # Métricas en tiempo real
    total_filled_percentage: float = 0.0   # % ya ejecutado
    average_entry_price: float = 0.0       # Precio medio de entrada
    current_price: float = 0.0             # Último precio conocido
    unrealized_pnl: float = 0.0            # P&L no realizado (%)
    unrealized_pnl_usd: float = 0.0        # P&L no realizado ($)
    
    # Timing
    last_price_check: Optional[datetime] = None
    last_signal_sent: Optional[datetime] = None
    position_opened_at: Optional[datetime] = None  # Primera entrada ejecutada
    position_closed_at: Optional[datetime] = None
    
    # Control de actualizaciones
    update_count: int = 0                  # Cuántas veces se ha actualizado
    telegram_messages_sent: int = 0        # Mensajes enviados al usuario
    
    # Estado general
    status: PositionStatus = PositionStatus.PENDING
    
    # Metadatos adicionales
    metadata: Dict[str, Any] = field(default_factory=dict)
    notes: str = ""
    
    def get_entries_executed_count(self) -> int:
        """Contar cuántos niveles de entrada se ejecutaron"""
        return sum(1 for e in self.entry_levels if e.is_executed())
    
    def get_exits_executed_count(self) -> int:
        """Contar cuántos niveles de salida se ejecutaron"""
        return sum(1 for e in self.exit_levels if e.is_executed())
    
    def is_fully_entered(self) -> bool:
        """Check si todas las entradas se ejecutaron"""
        return all(e.is_executed() for e in self.entry_levels)
    
    def is_fully_exited(self) -> bool:
        """Check si todas las salidas se ejecutaron"""
        return all(e.is_executed() for e in self.exit_levels)
    
    def calculate_average_entry(self) -> float:
        """Calcular precio medio de entrada ponderado"""
        total_invested = 0.0
        total_shares = 0.0
        
        for entry in self.entry_levels:
            if entry.is_executed() and entry.filled_price:
                # Peso = porcentaje ejecutado
                weight = entry.filled_percentage / 100.0
                total_invested += entry.filled_price * weight
                total_shares += weight
        
        if total_shares > 0:
            return total_invested / total_shares
        return 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertir a diccionario para persistencia"""
        return {
            'position_id': self.position_id,
            'symbol': self.symbol,
            'direction': self.direction,
            'signal_timestamp': self.signal_timestamp.isoformat(),
            'signal_strength': self.signal_strength,
            'entry_levels': [e.to_dict() for e in self.entry_levels],
            'exit_levels': [e.to_dict() for e in self.exit_levels],
            'stop_loss': self.stop_loss.to_dict() if self.stop_loss else None,
            'total_filled_percentage': self.total_filled_percentage,
            'average_entry_price': self.average_entry_price,
            'current_price': self.current_price,
            'unrealized_pnl': self.unrealized_pnl,
            'unrealized_pnl_usd': self.unrealized_pnl_usd,
            'last_price_check': self.last_price_check.isoformat() if self.last_price_check else None,
            'last_signal_sent': self.last_signal_sent.isoformat() if self.last_signal_sent else None,
            'position_opened_at': self.position_opened_at.isoformat() if self.position_opened_at else None,
            'position_closed_at': self.position_closed_at.isoformat() if self.position_closed_at else None,
            'update_count': self.update_count,
            'telegram_messages_sent': self.telegram_messages_sent,
            'status': self.status.value,
            'metadata': self.metadata,
            'notes': self.notes
        }
    
    def to_json(self) -> str:
        """Convertir a JSON string"""
        return json.dumps(self.to_dict(), indent=2)


# =============================================================================
# 📨 DATACLASSES - Eventos
# =============================================================================

@dataclass
class ExecutionEvent:
    """
    Evento de ejecución detectado
    
    Representa un cambio de estado en algún nivel (entrada, salida, stop)
    """
    # Identificación
    event_id: str                          # UUID único del evento
    position_id: str
    symbol: str
    
    # Tipo y detalles
    event_type: ExecutionEventType
    level_id: int                          # Qué nivel se ejecutó
    
    # Precios
    target_price: float                    # Precio objetivo original
    executed_price: float                  # Precio real de ejecución
    slippage: float = 0.0                  # Diferencia target vs executed
    
    # Cantidades
    percentage: float = 0.0                # % de la posición
    
    # Timing
    timestamp: datetime = field(default_factory=datetime.now)
    
    # Metadatos
    description: str = ""
    trigger_reason: str = ""               # Por qué se ejecutó
    notes: str = ""
    
    def calculate_slippage(self) -> float:
        """Calcular slippage en %"""
        if self.target_price == 0:
            return 0.0
        return ((self.executed_price - self.target_price) / self.target_price) * 100
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertir a diccionario para persistencia"""
        return {
            'event_id': self.event_id,
            'position_id': self.position_id,
            'symbol': self.symbol,
            'event_type': self.event_type.value,
            'level_id': self.level_id,
            'target_price': self.target_price,
            'executed_price': self.executed_price,
            'slippage': self.slippage,
            'percentage': self.percentage,
            'timestamp': self.timestamp.isoformat(),
            'description': self.description,
            'trigger_reason': self.trigger_reason,
            'notes': self.notes
        }


# =============================================================================
# 🛠️ FUNCIONES HELPER
# =============================================================================

def create_entry_levels_from_plan(plan: Any) -> List[EntryLevelStatus]:
    """
    Crear lista de EntryLevelStatus desde un PositionPlan
    
    Args:
        plan: PositionPlan del position_calculator
        
    Returns:
        Lista de EntryLevelStatus inicializados en PENDING
    """
    entry_levels = []
    
    for i, entry in enumerate(plan.entries, start=1):
        level = EntryLevelStatus(
            level_id=i,
            target_price=entry.price,
            percentage=entry.percentage,
            status=ExecutionStatus.PENDING,
            description=entry.description,
            trigger_condition=entry.trigger_condition
        )
        entry_levels.append(level)
    
    return entry_levels


def create_exit_levels_from_plan(plan: Any) -> List[ExitLevelStatus]:
    """
    Crear lista de ExitLevelStatus desde un PositionPlan
    
    Args:
        plan: PositionPlan del position_calculator
        
    Returns:
        Lista de ExitLevelStatus inicializados en PENDING
    """
    exit_levels = []
    
    for i, exit_level in enumerate(plan.exits, start=1):
        level = ExitLevelStatus(
            level_id=i,
            target_price=exit_level.price,
            percentage=exit_level.percentage,
            status=ExecutionStatus.PENDING,
            risk_reward_ratio=exit_level.risk_reward if hasattr(exit_level, 'risk_reward') else None,
            description=exit_level.description,
            trigger_condition=exit_level.trigger_condition
        )
        exit_levels.append(level)
    
    return exit_levels


def create_stop_level_from_plan(plan: Any) -> StopLevelStatus:
    """
    Crear StopLevelStatus desde un PositionPlan
    
    Args:
        plan: PositionPlan del position_calculator
        
    Returns:
        StopLevelStatus inicializado en PENDING
    """
    return StopLevelStatus(
        target_price=plan.stop_loss.price,
        status=ExecutionStatus.PENDING,
        stop_type="FIXED",  # Por ahora solo fixed, luego trailing
        description=plan.stop_loss.description,
        trigger_condition=plan.stop_loss.trigger_condition
    )


# =============================================================================
# 🧪 TESTING
# =============================================================================

if __name__ == "__main__":
    print("🧪 TESTING POSITION MANAGER MODELS V4.0")
    print("=" * 60)
    
    # Test 1: Crear niveles de entrada
    print("\n1. Test EntryLevelStatus:")
    entry = EntryLevelStatus(
        level_id=1,
        target_price=100.0,
        percentage=40.0,
        status=ExecutionStatus.PENDING,
        description="Primera entrada - 40%"
    )
    print(f"   Creado: Entry Level {entry.level_id} @ ${entry.target_price}")
    print(f"   Status: {entry.status.value}")
    print(f"   Ejecutado: {entry.is_executed()}")
    
    # Test 2: Ejecutar nivel
    print("\n2. Test ejecución de nivel:")
    entry.status = ExecutionStatus.FILLED
    entry.filled_price = 99.95
    entry.filled_timestamp = datetime.now()
    entry.filled_percentage = 40.0
    print(f"   Nivel ejecutado @ ${entry.filled_price}")
    print(f"   Ejecutado: {entry.is_executed()}")
    
    # Test 3: TrackedPosition completa
    print("\n3. Test TrackedPosition:")
    from uuid import uuid4
    
    position = TrackedPosition(
        position_id=str(uuid4()),
        symbol="AAPL",
        direction="LONG",
        signal_timestamp=datetime.now(),
        signal_strength=85,
        original_plan=None,  # Normalmente sería el PositionPlan real
        entry_levels=[entry],
        status=PositionStatus.PARTIALLY_FILLED
    )
    
    print(f"   Position ID: {position.position_id[:8]}...")
    print(f"   Symbol: {position.symbol}")
    print(f"   Direction: {position.direction}")
    print(f"   Status: {position.status.value}")
    print(f"   Entradas ejecutadas: {position.get_entries_executed_count()}")
    print(f"   Completamente entrado: {position.is_fully_entered()}")
    
    # Test 4: Serialización
    print("\n4. Test serialización:")
    position_dict = position.to_dict()
    print(f"   Keys en dict: {len(position_dict)}")
    print(f"   Serializado correctamente: ✅")
    
    # Test 5: ExecutionEvent
    print("\n5. Test ExecutionEvent:")
    event = ExecutionEvent(
        event_id=str(uuid4()),
        position_id=position.position_id,
        symbol="AAPL",
        event_type=ExecutionEventType.ENTRY_FILLED,
        level_id=1,
        target_price=100.0,
        executed_price=99.95,
        percentage=40.0,
        trigger_reason="Precio alcanzó nivel objetivo"
    )
    event.slippage = event.calculate_slippage()
    print(f"   Event: {event.event_type.value}")
    print(f"   Slippage: {event.slippage:.3f}%")
    
    print("\n✅ TODOS LOS TESTS PASARON")
    print("=" * 60)