#!/usr/bin/env python3
"""
📊 POSITION DATA MODELS - Estructuras de Datos Mejoradas
=======================================================

Define las estructuras de datos para el nuevo sistema de tracking
de posiciones con entradas escalonadas y gestión granular de estado.

Reemplaza la estructura JSON simple por modelos robustos con validación.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, List, Optional, Any, Union
from decimal import Decimal
import json
from enum import Enum

# Manejo de imports para testing standalone y uso en módulo
try:
    from .states import (
        PositionStatus, EntryStatus, ExitStatus, ExecutionType, 
        SignalDirection, AlertPriority
    )
except ImportError:
    # Para testing standalone
    from states import (
        PositionStatus, EntryStatus, ExitStatus, ExecutionType, 
        SignalDirection, AlertPriority
    )


@dataclass
class ExecutionLevel:
    """Nivel de ejecución individual (entrada o salida)"""
    
    # Identificación
    level_id: int                    # 1, 2, 3, 4
    level_type: ExecutionType        # ENTRY, EXIT, STOP_LOSS, etc.
    
    # Precios y cantidades
    target_price: float              # Precio objetivo
    executed_price: Optional[float] = None   # Precio real de ejecución
    quantity: int = 0                # Cantidad de acciones
    percentage: float = 0.0          # % del total de la posición
    
    # Estado y timing
    status: Union[EntryStatus, ExitStatus] = EntryStatus.PENDING
    created_at: datetime = field(default_factory=datetime.now)
    executed_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    
    # Metadatos
    description: str = ""            # "Entrada 1 - Breakout confirmado"
    trigger_condition: str = ""      # "Precio <= 508.00"
    notes: str = ""                  # Notas adicionales
    
    def is_executed(self) -> bool:
        """Verificar si el nivel está ejecutado"""
        return self.status in [EntryStatus.FILLED, ExitStatus.FILLED]
    
    def is_pending(self) -> bool:
        """Verificar si el nivel está pendiente"""
        return self.status in [EntryStatus.PENDING, ExitStatus.PENDING]
    
    def get_executed_value(self) -> float:
        """Obtener valor ejecutado en dollars"""
        if self.executed_price and self.quantity:
            return self.executed_price * self.quantity
        return 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertir a diccionario serializable"""
        data = asdict(self)
        # Convertir enums y datetime a strings
        data['level_type'] = self.level_type.value
        data['status'] = self.status.value
        data['created_at'] = self.created_at.isoformat()
        if self.executed_at:
            data['executed_at'] = self.executed_at.isoformat()
        if self.cancelled_at:
            data['cancelled_at'] = self.cancelled_at.isoformat()
        return data


@dataclass
class PositionSummary:
    """Resumen calculado de la posición actual"""
    
    # Estado general
    total_shares: int = 0                    # Acciones totales ejecutadas
    average_entry_price: float = 0.0        # Precio promedio ponderado
    total_invested: float = 0.0              # Capital invertido real
    
    # Progreso de ejecución
    percent_filled: float = 0.0              # % de posición ejecutado
    levels_executed: int = 0                 # Niveles ejecutados
    levels_pending: int = 0                  # Niveles pendientes
    
    # Risk management
    current_risk_dollars: float = 0.0        # Riesgo actual en $
    max_risk_dollars: float = 0.0            # Riesgo máximo planeado
    stop_loss_price: float = 0.0             # Precio stop actual
    
    # Performance
    current_price: float = 0.0               # Precio actual del mercado
    unrealized_pnl: float = 0.0              # P&L no realizado ($)
    unrealized_pnl_pct: float = 0.0          # P&L no realizado (%)
    
    # Timing
    time_in_position: int = 0                # Minutos en posición
    last_update: datetime = field(default_factory=datetime.now)
    
    def update_from_executions(self, executions: List[ExecutionLevel]):
        """Actualizar resumen basado en ejecuciones"""
        entry_executions = [e for e in executions if e.level_type == ExecutionType.ENTRY and e.is_executed()]
        
        if entry_executions:
            # Calcular totales usando precio ponderado correcto
            total_value = 0.0
            total_shares = 0
            
            for e in entry_executions:
                if e.executed_price and e.quantity:
                    total_value += (e.executed_price * e.quantity)
                    total_shares += e.quantity
            
            self.total_shares = total_shares
            self.total_invested = total_value
            self.average_entry_price = total_value / total_shares if total_shares > 0 else 0.0
            
            # Calcular progreso
            all_entries = [e for e in executions if e.level_type == ExecutionType.ENTRY]
            self.levels_executed = len(entry_executions)
            self.levels_pending = len([e for e in all_entries if e.is_pending()])
            
            # Calcular % ejecutado (por shares, no por niveles) - CONSISTENTE con BD
            total_planned_shares = sum(e.quantity for e in all_entries)
            self.percent_filled = (total_shares / total_planned_shares * 100) if total_planned_shares > 0 else 0.0
        else:
            # Si no hay entradas ejecutadas, resetear valores
            self.total_shares = 0
            self.total_invested = 0.0
            self.average_entry_price = 0.0
            self.percent_filled = 0.0
            self.levels_executed = 0
            self.levels_pending = len([e for e in executions if e.level_type == ExecutionType.ENTRY and e.is_pending()])
        
        self.last_update = datetime.now()
    
    def calculate_pnl(self, current_market_price: float, direction: SignalDirection):
        """Calcular P&L actual"""
        if self.total_shares <= 0 or self.average_entry_price <= 0:
            return
        
        self.current_price = current_market_price
        
        if direction == SignalDirection.LONG:
            price_diff = current_market_price - self.average_entry_price
        else:  # SHORT
            price_diff = self.average_entry_price - current_market_price
        
        self.unrealized_pnl = price_diff * self.total_shares
        self.unrealized_pnl_pct = (price_diff / self.average_entry_price) * 100


@dataclass  
class StateTransition:
    """Registro de transición de estado"""
    
    from_state: PositionStatus
    to_state: PositionStatus
    timestamp: datetime = field(default_factory=datetime.now)
    trigger: str = ""                # "partial_fill_level_1", "exit_signal_generated"
    metadata: Dict[str, Any] = field(default_factory=dict)
    notes: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertir a diccionario"""
        return {
            'from_state': self.from_state.value,
            'to_state': self.to_state.value,
            'timestamp': self.timestamp.isoformat(),
            'trigger': self.trigger,
            'metadata': self.metadata,
            'notes': self.notes
        }


@dataclass
class EnhancedPosition:
    """Posición mejorada con tracking completo de estado"""
    
    # Identificación básica
    symbol: str
    direction: SignalDirection
    position_id: str = ""                    # UUID único
    
    # Estado y timing
    status: PositionStatus = PositionStatus.SIGNAL_GENERATED
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    # Señal original (datos básicos para referencia)
    signal_strength: int = 0
    confidence_level: str = ""
    entry_quality: str = ""
    strategy_type: str = ""
    
    # Niveles de ejecución
    entries: List[ExecutionLevel] = field(default_factory=list)
    exits: List[ExecutionLevel] = field(default_factory=list)
    stop_loss: Optional[ExecutionLevel] = None
    
    # Resumen calculado
    summary: PositionSummary = field(default_factory=PositionSummary)
    
    # Historial y tracking
    state_history: List[StateTransition] = field(default_factory=list)
    alerts_sent: int = 0
    deterioration_count: int = 0
    exit_alerts_sent: int = 0
    
    # Metadatos adicionales
    notes: str = ""
    tags: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        """Post-inicialización"""
        if not self.position_id:
            # Generar ID único basado en symbol + timestamp
            timestamp_str = self.created_at.strftime("%Y%m%d_%H%M%S")
            self.position_id = f"{self.symbol}_{timestamp_str}"
    
    def add_state_transition(self, to_state: PositionStatus, trigger: str = "", notes: str = ""):
        """Agregar transición de estado"""
        transition = StateTransition(
            from_state=self.status,
            to_state=to_state,
            trigger=trigger,
            notes=notes
        )
        
        self.state_history.append(transition)
        self.status = to_state
        self.updated_at = datetime.now()
    
    def update_summary(self):
        """Actualizar resumen calculado"""
        self.summary.update_from_executions(self.entries + self.exits)
        self.updated_at = datetime.now()
    
    def get_executed_entries(self) -> List[ExecutionLevel]:
        """Obtener entradas ejecutadas"""
        return [e for e in self.entries if e.is_executed()]
    
    def get_pending_entries(self) -> List[ExecutionLevel]:
        """Obtener entradas pendientes"""
        return [e for e in self.entries if e.is_pending()]
    
    def get_executed_exits(self) -> List[ExecutionLevel]:
        """Obtener salidas ejecutadas"""
        return [e for e in self.exits if e.is_executed()]
    
    def get_pending_exits(self) -> List[ExecutionLevel]:
        """Obtener salidas pendientes"""
        return [e for e in self.exits if e.is_pending()]
    
    def is_fully_entered(self) -> bool:
        """Verificar si todas las entradas están ejecutadas"""
        return len(self.get_pending_entries()) == 0 and len(self.get_executed_entries()) > 0
    
    def is_partially_filled(self) -> bool:
        """Verificar si hay entradas parciales"""
        return len(self.get_executed_entries()) > 0 and len(self.get_pending_entries()) > 0
    
    def calculate_current_pnl(self, current_market_price: float):
        """Calcular P&L actual"""
        self.summary.calculate_pnl(current_market_price, self.direction)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertir a diccionario serializable"""
        return {
            # Básicos
            'symbol': self.symbol,
            'direction': self.direction.value,
            'position_id': self.position_id,
            'status': self.status.value,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            
            # Señal
            'signal_strength': self.signal_strength,
            'confidence_level': self.confidence_level,
            'entry_quality': self.entry_quality,
            'strategy_type': self.strategy_type,
            
            # Ejecuciones
            'entries': [e.to_dict() for e in self.entries],
            'exits': [e.to_dict() for e in self.exits],
            'stop_loss': self.stop_loss.to_dict() if self.stop_loss else None,
            
            # Resumen
            'summary': asdict(self.summary),
            
            # Historial
            'state_history': [t.to_dict() for t in self.state_history],
            'alerts_sent': self.alerts_sent,
            'deterioration_count': self.deterioration_count,
            'exit_alerts_sent': self.exit_alerts_sent,
            
            # Metadatos
            'notes': self.notes,
            'tags': self.tags
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'EnhancedPosition':
        """Crear desde diccionario"""
        # Crear instancia básica
        position = cls(
            symbol=data['symbol'],
            direction=SignalDirection(data['direction']),
            position_id=data.get('position_id', ''),
            status=PositionStatus(data.get('status', 'SIGNAL_GENERATED'))
        )
        
        # Actualizar campos básicos
        if 'created_at' in data:
            position.created_at = datetime.fromisoformat(data['created_at'])
        if 'updated_at' in data:
            position.updated_at = datetime.fromisoformat(data['updated_at'])
            
        # Campos de señal
        position.signal_strength = data.get('signal_strength', 0)
        position.confidence_level = data.get('confidence_level', '')
        position.entry_quality = data.get('entry_quality', '')
        position.strategy_type = data.get('strategy_type', '')
        
        # TODO: Deserializar entries, exits, etc. (implementar según necesidad)
        # Por ahora solo los básicos para compatibilidad
        
        return position


def create_execution_level(level_id: int, 
                         level_type: ExecutionType,
                         target_price: float,
                         quantity: int,
                         percentage: float,
                         description: str = "") -> ExecutionLevel:
    """Factory function para crear niveles de ejecución"""
    
    status = EntryStatus.PENDING if level_type == ExecutionType.ENTRY else ExitStatus.PENDING
    
    return ExecutionLevel(
        level_id=level_id,
        level_type=level_type,
        target_price=target_price,
        quantity=quantity,
        percentage=percentage,
        description=description,
        status=status
    )


if __name__ == "__main__":
    # Demo básico
    print("📊 POSITION DATA MODELS - Demo")
    print("=" * 40)
    
    # Crear posición de ejemplo
    position = EnhancedPosition(
        symbol="AAPL",
        direction=SignalDirection.LONG,
        signal_strength=85,
        confidence_level="HIGH"
    )
    
    # Agregar niveles de entrada
    entry1 = create_execution_level(1, ExecutionType.ENTRY, 150.0, 100, 40.0, "Entrada 1 - Breakout")
    entry2 = create_execution_level(2, ExecutionType.ENTRY, 149.0, 75, 30.0, "Entrada 2 - Pullback") 
    entry3 = create_execution_level(3, ExecutionType.ENTRY, 148.0, 75, 30.0, "Entrada 3 - Support")
    
    position.entries = [entry1, entry2, entry3]
    
    # Simular ejecución del primer nivel
    entry1.status = EntryStatus.FILLED
    entry1.executed_price = 150.05
    entry1.executed_at = datetime.now()
    
    # Actualizar resumen
    position.update_summary()
    position.add_state_transition(PositionStatus.PARTIALLY_FILLED, "entry_level_1_filled")
    
    print(f"✅ Posición creada: {position.symbol} {position.direction.value}")
    print(f"📈 Estado: {position.status.value}")
    print(f"📊 Progreso: {position.summary.percent_filled:.1f}% ejecutado")
    print(f"💰 Acciones: {position.summary.total_shares}")
    print(f"💵 Precio promedio: ${position.summary.average_entry_price:.2f}")
    print(f"🔄 Transiciones: {len(position.state_history)}")
    
    # Mostrar niveles
    print(f"\n📋 Niveles de entrada:")
    for entry in position.entries:
        status_icon = "✅" if entry.is_executed() else "⏳"
        print(f"  {status_icon} Nivel {entry.level_id}: ${entry.target_price:.2f} ({entry.percentage}%)")