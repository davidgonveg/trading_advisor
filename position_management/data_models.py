#!/usr/bin/env python3
"""
📊 POSITION DATA MODELS - Estructuras de Datos Corregidas V3.0
==============================================================

FIXES APLICADOS:
✅ PositionSummary.current_position_size (era total_shares)
✅ PositionSummary.total_pnl calculado correctamente
✅ EnhancedPosition.entry_levels / exit_levels (eran entries/exits)
✅ Métodos get_executed_entries/exits para compatibilidad
✅ Compatibilidad con position_tracker y tests
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
    """
    Resumen calculado de la posición actual - ESTRUCTURA CORREGIDA V3.0
    """
    
    # ✅ FIX: Estado general con nombres correctos
    current_position_size: float = 0.0          # ✅ Renombrado desde total_shares
    total_shares: int = 0                       # Mantener para compatibilidad
    average_entry_price: float = 0.0           # Precio promedio ponderado
    total_invested: float = 0.0                 # Capital invertido real
    
    # Progreso de ejecución
    percent_filled: float = 0.0                 # % de posición ejecutado
    levels_executed: int = 0                    # Niveles ejecutados
    levels_pending: int = 0                     # Niveles pendientes
    
    # ✅ FIX: P&L calculados correctamente
    realized_pnl: float = 0.0                  # P&L de posiciones cerradas
    unrealized_pnl: float = 0.0                # P&L de posición abierta
    total_pnl: float = 0.0                     # ✅ AÑADIDO: Total P&L
    unrealized_pnl_pct: float = 0.0            # % P&L no realizado
    
    # Precios de referencia
    current_price: float = 0.0                 # Precio actual del mercado
    stop_loss_price: float = 0.0               # Precio de stop loss
    
    # Timing
    first_entry_time: Optional[datetime] = None
    last_update: datetime = field(default_factory=datetime.now)
    
    def update_from_executions(self, execution_levels: List[ExecutionLevel]):
        """
        ✅ FIX: Actualizar resumen desde niveles de ejecución
        """
        executed_levels = [level for level in execution_levels if level.is_executed()]
        
        if not executed_levels:
            return
        
        # Calcular posición total
        total_quantity = sum(level.quantity for level in executed_levels)
        total_value = sum(level.get_executed_value() for level in executed_levels)
        
        # ✅ FIX: Actualizar ambos campos
        self.current_position_size = float(total_quantity)
        self.total_shares = int(total_quantity)
        
        # Precio promedio ponderado
        if total_quantity > 0:
            self.average_entry_price = total_value / total_quantity
            self.total_invested = total_value
        
        # Progreso de ejecución
        total_levels = len(execution_levels)
        self.levels_executed = len(executed_levels)
        self.levels_pending = total_levels - len(executed_levels)
        
        if total_levels > 0:
            self.percent_filled = (len(executed_levels) / total_levels) * 100
        
        # Timing
        executed_times = [level.executed_at for level in executed_levels if level.executed_at]
        if executed_times:
            self.first_entry_time = min(executed_times)
        
        self.last_update = datetime.now()
    
    def calculate_pnl(self, current_market_price: float, direction: SignalDirection):
        """✅ FIX: Calcular P&L actual"""
        if self.current_position_size <= 0 or self.average_entry_price <= 0:
            self.total_pnl = self.realized_pnl  # Solo P&L realizado
            return
        
        self.current_price = current_market_price
        
        if direction == SignalDirection.LONG:
            price_diff = current_market_price - self.average_entry_price
        else:  # SHORT
            price_diff = self.average_entry_price - current_market_price
        
        self.unrealized_pnl = price_diff * self.current_position_size
        if self.average_entry_price > 0:
            self.unrealized_pnl_pct = (price_diff / self.average_entry_price) * 100
        
        # ✅ FIX: Total P&L = realizado + no realizado
        self.total_pnl = self.realized_pnl + self.unrealized_pnl


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
    """
    ✅ FIX: Posición mejorada con estructura corregida V3.0
    """
    
    # Identificación básica
    symbol: str
    direction: SignalDirection
    position_id: str = ""                    # UUID único
    
    # Estado y timing
    status: PositionStatus = PositionStatus.SIGNAL_GENERATED
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    # Señal original (datos básicos para referencia)
    signal_strength: float = 0               # ✅ FIX: float en lugar de int
    confidence_level: str = ""
    entry_quality: str = ""
    strategy_type: str = ""
    
    # ✅ FIX: Niveles de ejecución con nombres correctos
    entry_levels: List[ExecutionLevel] = field(default_factory=list)  # ✅ Renombrado
    exit_levels: List[ExecutionLevel] = field(default_factory=list)   # ✅ Renombrado
    stop_loss: Optional[ExecutionLevel] = None
    
    # ✅ FIX: Mantener aliases para compatibilidad
    @property
    def entries(self) -> List[ExecutionLevel]:
        """Alias para compatibilidad"""
        return self.entry_levels
    
    @entries.setter
    def entries(self, value: List[ExecutionLevel]):
        """Setter para compatibilidad"""
        self.entry_levels = value
    
    @property
    def exits(self) -> List[ExecutionLevel]:
        """Alias para compatibilidad"""
        return self.exit_levels
    
    @exits.setter
    def exits(self, value: List[ExecutionLevel]):
        """Setter para compatibilidad"""
        self.exit_levels = value
    
    # Resumen calculado
    summary: PositionSummary = field(default_factory=PositionSummary)
    
    # Historial y tracking
    state_history: List[StateTransition] = field(default_factory=list)
    alerts_sent: int = 0
    deterioration_count: int = 0
    exit_alerts_sent: int = 0
    
    # ✅ FIX: Metadatos opcionales para compatibilidad
    metadata: Optional[Dict[str, Any]] = None
    notes: str = ""
    tags: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        """Post-inicialización"""
        if not self.position_id:
            # Generar ID único basado en symbol + timestamp
            timestamp_str = self.created_at.strftime("%Y%m%d_%H%M%S")
            self.position_id = f"{self.symbol}_{timestamp_str}"
        
        # Inicializar metadata si no existe
        if self.metadata is None:
            self.metadata = {}
    
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
        # ✅ FIX: Usar todos los niveles
        all_levels = self.entry_levels + self.exit_levels
        self.summary.update_from_executions(all_levels)
        self.updated_at = datetime.now()
    
    # ✅ FIX: Métodos de compatibilidad con nombres correctos
    def get_executed_entries(self) -> List[ExecutionLevel]:
        """Obtener entradas ejecutadas"""
        return [e for e in self.entry_levels if e.is_executed()]
    
    def get_pending_entries(self) -> List[ExecutionLevel]:
        """Obtener entradas pendientes"""
        return [e for e in self.entry_levels if e.is_pending()]
    
    def get_executed_exits(self) -> List[ExecutionLevel]:
        """Obtener salidas ejecutadas"""
        return [e for e in self.exit_levels if e.is_executed()]
    
    def get_pending_exits(self) -> List[ExecutionLevel]:
        """Obtener salidas pendientes"""
        return [e for e in self.exit_levels if e.is_pending()]
    
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
            
            # ✅ FIX: Usar nombres correctos
            'entry_levels': [e.to_dict() for e in self.entry_levels],
            'exit_levels': [e.to_dict() for e in self.exit_levels],
            'stop_loss': self.stop_loss.to_dict() if self.stop_loss else None,
            
            # Resumen
            'summary': asdict(self.summary),
            
            # Historial
            'state_history': [t.to_dict() for t in self.state_history],
            'alerts_sent': self.alerts_sent,
            'deterioration_count': self.deterioration_count,
            'exit_alerts_sent': self.exit_alerts_sent,
            
            # Metadatos
            'metadata': self.metadata,
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
        
        # Metadatos
        position.metadata = data.get('metadata', {})
        position.notes = data.get('notes', '')
        position.tags = data.get('tags', [])
        
        # TODO: Deserializar entry_levels, exit_levels, etc. si es necesario
        
        return position


# ==============================================
# FACTORY FUNCTIONS - HELPERS PARA CREAR OBJETOS
# ==============================================

def create_execution_level(level_number: int, level_type: Union[str, ExecutionType], 
                          target_price: float, quantity: int, 
                          percentage: float, description: str = "") -> ExecutionLevel:
    """
    ✅ FIX: Factory function para crear ExecutionLevel
    """
    # Convertir string a enum si es necesario
    if isinstance(level_type, str):
        if level_type.upper() == "ENTRY":
            level_type = ExecutionType.ENTRY
        elif level_type.upper() == "EXIT":
            level_type = ExecutionType.EXIT
        elif level_type.upper() == "STOP_LOSS":
            level_type = ExecutionType.STOP_LOSS
        else:
            level_type = ExecutionType.ENTRY  # Default
    
    return ExecutionLevel(
        level_id=level_number,
        level_type=level_type,
        target_price=target_price,
        quantity=quantity,
        percentage=percentage,
        description=description or f"{level_type.value.title()} level {level_number}"
    )


def create_enhanced_position(symbol: str, direction: Union[str, SignalDirection], 
                           signal_strength: float = 0, 
                           confidence_level: str = "MEDIUM") -> EnhancedPosition:
    """
    ✅ FIX: Factory function para crear EnhancedPosition
    """
    # Convertir string a enum si es necesario
    if isinstance(direction, str):
        direction = SignalDirection.LONG if direction.upper() == "LONG" else SignalDirection.SHORT
    
    return EnhancedPosition(
        symbol=symbol,
        direction=direction,
        signal_strength=signal_strength,
        confidence_level=confidence_level
    )


# ==============================================
# TESTING Y VALIDACIÓN
# ==============================================

def validate_position_data(position: EnhancedPosition) -> List[str]:
    """Validar datos de posición y devolver errores encontrados"""
    errors = []
    
    # Validaciones básicas
    if not position.symbol:
        errors.append("Symbol is required")
    
    if not position.position_id:
        errors.append("Position ID is required")
    
    if position.signal_strength < 0 or position.signal_strength > 100:
        errors.append("Signal strength must be between 0 and 100")
    
    # Validar niveles de ejecución
    if not position.entry_levels:
        errors.append("At least one entry level is required")
    
    # Validar consistencia de estado vs niveles
    executed_entries = len(position.get_executed_entries())
    pending_entries = len(position.get_pending_entries())
    
    if position.status == PositionStatus.FULLY_ENTERED and pending_entries > 0:
        errors.append("Status is FULLY_ENTERED but there are pending entries")
    
    if position.status == PositionStatus.ENTRY_PENDING and executed_entries > 0:
        errors.append("Status is ENTRY_PENDING but there are executed entries")
    
    return errors


# ==============================================
# DEMO Y TESTING
# ==============================================

if __name__ == "__main__":
    print("📊 DATA MODELS V3.0 - Demo y Validación")
    print("=" * 60)
    
    # Crear posición de ejemplo
    position = create_enhanced_position("DEMO", "LONG", 85, "HIGH")
    print(f"✅ Posición creada: {position.symbol} {position.direction.value}")
    
    # Añadir niveles de entrada
    entry1 = create_execution_level(1, "ENTRY", 100.0, 50, 40.0, "Breakout entry")
    entry2 = create_execution_level(2, "ENTRY", 99.0, 30, 30.0, "Pullback entry")
    entry3 = create_execution_level(3, "ENTRY", 98.0, 30, 30.0, "Support entry")
    
    position.entry_levels = [entry1, entry2, entry3]
    print(f"✅ {len(position.entry_levels)} niveles de entrada añadidos")
    
    # Simular ejecución parcial
    entry1.status = EntryStatus.FILLED
    entry1.executed_price = 100.05
    entry1.executed_at = datetime.now()
    
    # Actualizar resumen
    position.update_summary()
    print(f"✅ Summary actualizado:")
    print(f"   Current position size: {position.summary.current_position_size}")
    print(f"   Average entry price: ${position.summary.average_entry_price:.2f}")
    print(f"   Percent filled: {position.summary.percent_filled:.1f}%")
    print(f"   Total P&L: ${position.summary.total_pnl:.2f}")
    
    # Validar datos
    errors = validate_position_data(position)
    if errors:
        print(f"⚠️ Errores de validación: {errors}")
    else:
        print("✅ Validación exitosa - datos consistentes")
    
    # Test serialización
    try:
        position_dict = position.to_dict()
        print(f"✅ Serialización exitosa - {len(position_dict)} campos")
    except Exception as e:
        print(f"❌ Error en serialización: {e}")
    
    print("\n🏁 Demo completado")