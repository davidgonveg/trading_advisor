#!/usr/bin/env python3
"""
📊 TRADE MANAGER - Gestión de Trades con Entradas/Salidas Escalonadas
====================================================================

Gestiona el ciclo de vida completo de un trade:
- Entradas escalonadas (3 niveles)
- Salidas parciales (4 TPs)
- Stop loss
- Exit manager (salidas anticipadas)
- Tracking de P&L realizado y no realizado
"""

import logging
import pandas as pd
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import sys
from pathlib import Path

# Añadir path del proyecto
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from scanner import TradingSignal
from position_calculator import PositionPlan
from exit_manager import ExitUrgency

logger = logging.getLogger(__name__)


class TradeStatus(Enum):
    """Estados posibles de un trade"""
    PENDING = "PENDING"                 # Esperando entrada
    PARTIAL = "PARTIAL"                 # Parcialmente ejecutado
    ACTIVE = "ACTIVE"                   # Totalmente ejecutado
    CLOSING = "CLOSING"                 # Cerrando parcialmente
    CLOSED_WIN = "CLOSED_WIN"          # Cerrado con ganancia
    CLOSED_LOSS = "CLOSED_LOSS"        # Cerrado con pérdida
    CLOSED_EXIT_MANAGER = "CLOSED_EXIT_MANAGER"  # Cerrado por exit manager


class ExitReason(Enum):
    """Razones de cierre de trade"""
    NONE = "NONE"
    STOP_LOSS = "STOP_LOSS"
    TAKE_PROFIT_1 = "TAKE_PROFIT_1"
    TAKE_PROFIT_2 = "TAKE_PROFIT_2"
    TAKE_PROFIT_3 = "TAKE_PROFIT_3"
    TAKE_PROFIT_4 = "TAKE_PROFIT_4"
    EXIT_MANAGER = "EXIT_MANAGER"
    MANUAL = "MANUAL"
    END_OF_BACKTEST = "END_OF_BACKTEST"


@dataclass
class TradeExecution:
    """Registro de una ejecución (entrada o salida)"""
    timestamp: datetime
    action: str  # 'BUY', 'SELL', 'BUY_COVER', 'SELL_SHORT'
    price: float
    quantity: int
    commission: float
    total_cost: float  # Incluye comisión
    note: str = ""


@dataclass
class Trade:
    """
    Representa un trade completo con entradas/salidas escalonadas.
    """
    # Identificación
    trade_id: int
    symbol: str
    direction: str  # 'LONG' or 'SHORT'

    # Señal y plan originales
    signal: TradingSignal
    position_plan: PositionPlan

    # Timestamps
    signal_time: datetime
    first_entry_time: Optional[datetime] = None
    last_exit_time: Optional[datetime] = None

    # Estado actual
    status: TradeStatus = TradeStatus.PENDING

    # Entradas (tracking)
    entry_1_executed: bool = False
    entry_1_price: Optional[float] = None
    entry_1_quantity: int = 0
    entry_1_time: Optional[datetime] = None

    entry_2_executed: bool = False
    entry_2_price: Optional[float] = None
    entry_2_quantity: int = 0
    entry_2_time: Optional[datetime] = None

    entry_3_executed: bool = False
    entry_3_price: Optional[float] = None
    entry_3_quantity: int = 0
    entry_3_time: Optional[datetime] = None

    # Posición actual
    current_position: int = 0  # Acciones actualmente en posición
    avg_entry_price: float = 0.0

    # Salidas (tracking)
    tp1_executed: bool = False
    tp1_price: Optional[float] = None
    tp1_quantity: int = 0
    tp1_pnl: float = 0.0

    tp2_executed: bool = False
    tp2_price: Optional[float] = None
    tp2_quantity: int = 0
    tp2_pnl: float = 0.0

    tp3_executed: bool = False
    tp3_price: Optional[float] = None
    tp3_quantity: int = 0
    tp3_pnl: float = 0.0

    tp4_executed: bool = False
    tp4_price: Optional[float] = None
    tp4_quantity: int = 0
    tp4_pnl: float = 0.0

    # Stop loss
    stop_loss_hit: bool = False
    stop_loss_price: Optional[float] = None
    stop_loss_pnl: float = 0.0

    # Exit manager
    exit_manager_triggered: bool = False
    exit_manager_urgency: Optional[ExitUrgency] = None
    exit_manager_score: float = 0.0
    exit_manager_reason: str = ""

    # P&L
    realized_pnl: float = 0.0  # P&L de posiciones cerradas
    unrealized_pnl: float = 0.0  # P&L de posiciones abiertas
    total_pnl: float = 0.0  # realized + unrealized

    # Comisiones y slippage
    total_commissions: float = 0.0
    total_slippage: float = 0.0

    # Métricas de movimiento
    max_favorable_excursion: float = 0.0  # Mejor precio alcanzado
    max_adverse_excursion: float = 0.0    # Peor precio alcanzado
    bars_held: int = 0

    # Exit reason
    exit_reason: ExitReason = ExitReason.NONE

    # Ejecuciones
    executions: List[TradeExecution] = field(default_factory=list)

    def add_execution(self, execution: TradeExecution):
        """Añadir ejecución al historial"""
        self.executions.append(execution)
        self.total_commissions += execution.commission

    def update_unrealized_pnl(self, current_price: float):
        """Actualizar P&L no realizado basado en precio actual"""
        if self.current_position == 0:
            self.unrealized_pnl = 0.0
        else:
            if self.direction == "LONG":
                self.unrealized_pnl = (current_price - self.avg_entry_price) * self.current_position
            else:  # SHORT
                self.unrealized_pnl = (self.avg_entry_price - current_price) * self.current_position

            # Restar comisiones estimadas para cierre
            estimated_close_commission = self.current_position * 0.005
            self.unrealized_pnl -= estimated_close_commission

        self.total_pnl = self.realized_pnl + self.unrealized_pnl

    def update_excursions(self, current_price: float):
        """Actualizar máximas excursiones favorables y adversas"""
        if self.avg_entry_price == 0:
            return

        if self.direction == "LONG":
            # Para LONG: favorable = price up, adverse = price down
            move_pct = ((current_price - self.avg_entry_price) / self.avg_entry_price) * 100
            if move_pct > self.max_favorable_excursion:
                self.max_favorable_excursion = move_pct
            if move_pct < self.max_adverse_excursion:
                self.max_adverse_excursion = move_pct
        else:  # SHORT
            # Para SHORT: favorable = price down, adverse = price up
            move_pct = ((self.avg_entry_price - current_price) / self.avg_entry_price) * 100
            if move_pct > self.max_favorable_excursion:
                self.max_favorable_excursion = move_pct
            if move_pct < self.max_adverse_excursion:
                self.max_adverse_excursion = move_pct

    def to_dict(self) -> Dict:
        """Convertir trade a diccionario para análisis"""
        return {
            'trade_id': self.trade_id,
            'symbol': self.symbol,
            'direction': self.direction,
            'signal_time': self.signal_time.isoformat(),
            'first_entry_time': self.first_entry_time.isoformat() if self.first_entry_time else None,
            'last_exit_time': self.last_exit_time.isoformat() if self.last_exit_time else None,
            'status': self.status.value,
            'signal_strength': self.signal.signal_strength,
            'entry_quality': self.signal.entry_quality,

            # Entradas
            'entry_1_executed': self.entry_1_executed,
            'entry_1_price': self.entry_1_price,
            'entry_1_quantity': self.entry_1_quantity,
            'entry_2_executed': self.entry_2_executed,
            'entry_2_price': self.entry_2_price,
            'entry_2_quantity': self.entry_2_quantity,
            'entry_3_executed': self.entry_3_executed,
            'entry_3_price': self.entry_3_price,
            'entry_3_quantity': self.entry_3_quantity,
            'avg_entry_price': self.avg_entry_price,

            # Salidas
            'tp1_executed': self.tp1_executed,
            'tp1_pnl': self.tp1_pnl,
            'tp2_executed': self.tp2_executed,
            'tp2_pnl': self.tp2_pnl,
            'tp3_executed': self.tp3_executed,
            'tp3_pnl': self.tp3_pnl,
            'tp4_executed': self.tp4_executed,
            'tp4_pnl': self.tp4_pnl,
            'stop_loss_hit': self.stop_loss_hit,
            'stop_loss_pnl': self.stop_loss_pnl,

            # Exit manager
            'exit_manager_triggered': self.exit_manager_triggered,
            'exit_manager_reason': self.exit_manager_reason,

            # P&L
            'realized_pnl': self.realized_pnl,
            'unrealized_pnl': self.unrealized_pnl,
            'total_pnl': self.total_pnl,
            'total_commissions': self.total_commissions,

            # Métricas
            'max_favorable_excursion': self.max_favorable_excursion,
            'max_adverse_excursion': self.max_adverse_excursion,
            'bars_held': self.bars_held,
            'exit_reason': self.exit_reason.value,
        }


class TradeManager:
    """
    Gestor de trades que maneja el ciclo de vida completo.
    """

    def __init__(self, commission_per_share: float = 0.005):
        """
        Inicializar trade manager.

        Args:
            commission_per_share: Comisión por acción ($)
        """
        self.commission_per_share = commission_per_share
        self.trades: List[Trade] = []
        self.active_trades: Dict[str, Trade] = {}  # symbol -> trade
        self.trade_counter = 0

        logger.info(f"📊 TradeManager inicializado (commission=${commission_per_share}/share)")

    def create_trade(self, signal: TradingSignal, position_plan: PositionPlan) -> Trade:
        """
        Crear un nuevo trade.

        Args:
            signal: Señal de trading
            position_plan: Plan de posición calculado

        Returns:
            Trade object
        """
        self.trade_counter += 1

        trade = Trade(
            trade_id=self.trade_counter,
            symbol=signal.symbol,
            direction=signal.signal_type,
            signal=signal,
            position_plan=position_plan,
            signal_time=signal.timestamp,
        )

        self.trades.append(trade)
        self.active_trades[signal.symbol] = trade

        logger.info(
            f"📊 Trade #{trade.trade_id} creado: {signal.symbol} {signal.signal_type} "
            f"({signal.signal_strength} pts)"
        )

        return trade

    def execute_entry(
        self,
        trade: Trade,
        entry_level: int,
        price: float,
        timestamp: datetime,
        slippage: float = 0.0
    ) -> bool:
        """
        Ejecutar una entrada escalonada.

        Args:
            trade: Trade object
            entry_level: Nivel de entrada (1, 2, o 3)
            price: Precio de ejecución
            timestamp: Timestamp de ejecución
            slippage: Slippage aplicado

        Returns:
            True si se ejecutó, False si no
        """
        try:
            # Determinar cantidad según nivel
            if entry_level == 1:
                if trade.entry_1_executed:
                    return False
                quantity = trade.position_plan.entry_1_quantity
                trade.entry_1_executed = True
                trade.entry_1_price = price
                trade.entry_1_quantity = quantity
                trade.entry_1_time = timestamp
                if not trade.first_entry_time:
                    trade.first_entry_time = timestamp
            elif entry_level == 2:
                if trade.entry_2_executed:
                    return False
                quantity = trade.position_plan.entry_2_quantity
                trade.entry_2_executed = True
                trade.entry_2_price = price
                trade.entry_2_quantity = quantity
                trade.entry_2_time = timestamp
            elif entry_level == 3:
                if trade.entry_3_executed:
                    return False
                quantity = trade.position_plan.entry_3_quantity
                trade.entry_3_executed = True
                trade_3_price = price
                trade.entry_3_quantity = quantity
                trade.entry_3_time = timestamp
            else:
                return False

            # Calcular comisión
            commission = quantity * self.commission_per_share
            total_cost = (price * quantity) + commission

            # Añadir ejecución
            action = "BUY" if trade.direction == "LONG" else "SELL_SHORT"
            execution = TradeExecution(
                timestamp=timestamp,
                action=action,
                price=price,
                quantity=quantity,
                commission=commission,
                total_cost=total_cost,
                note=f"Entry level {entry_level}"
            )
            trade.add_execution(execution)

            # Actualizar posición
            trade.current_position += quantity

            # Recalcular precio promedio de entrada
            total_shares_before = trade.current_position - quantity
            total_cost_before = total_shares_before * trade.avg_entry_price
            new_cost = quantity * price
            trade.avg_entry_price = (total_cost_before + new_cost) / trade.current_position

            # Actualizar estado
            if trade.current_position == trade.position_plan.total_position_size:
                trade.status = TradeStatus.ACTIVE
            else:
                trade.status = TradeStatus.PARTIAL

            # Añadir slippage
            trade.total_slippage += slippage * quantity

            logger.debug(
                f"✅ Entry {entry_level} ejecutada: {trade.symbol} @ ${price:.2f} x {quantity} "
                f"(avg=${trade.avg_entry_price:.2f})"
            )

            return True

        except Exception as e:
            logger.error(f"❌ Error ejecutando entry: {e}")
            return False

    def execute_exit(
        self,
        trade: Trade,
        exit_type: str,
        price: float,
        timestamp: datetime,
        reason: ExitReason,
        slippage: float = 0.0
    ) -> Tuple[bool, float]:
        """
        Ejecutar una salida (TP o SL).

        Args:
            trade: Trade object
            exit_type: 'TP1', 'TP2', 'TP3', 'TP4', 'SL', 'EXIT_MANAGER'
            price: Precio de ejecución
            timestamp: Timestamp
            reason: Razón de salida
            slippage: Slippage aplicado

        Returns:
            Tupla (success, pnl)
        """
        try:
            if trade.current_position == 0:
                return False, 0.0

            # Determinar cantidad a cerrar
            if exit_type == "TP1":
                if trade.tp1_executed:
                    return False, 0.0
                quantity = int(trade.position_plan.total_position_size * 0.25)
                trade.tp1_executed = True
                trade.tp1_price = price
                trade.tp1_quantity = quantity
            elif exit_type == "TP2":
                if trade.tp2_executed:
                    return False, 0.0
                quantity = int(trade.position_plan.total_position_size * 0.25)
                trade.tp2_executed = True
                trade.tp2_price = price
                trade.tp2_quantity = quantity
            elif exit_type == "TP3":
                if trade.tp3_executed:
                    return False, 0.0
                quantity = int(trade.position_plan.total_position_size * 0.25)
                trade.tp3_executed = True
                trade.tp3_price = price
                trade.tp3_quantity = quantity
            elif exit_type == "TP4":
                if trade.tp4_executed:
                    return False, 0.0
                quantity = trade.current_position  # Cerrar todo lo restante
                trade.tp4_executed = True
                trade.tp4_price = price
                trade.tp4_quantity = quantity
            elif exit_type in ["SL", "EXIT_MANAGER"]:
                quantity = trade.current_position  # Cerrar toda la posición
                if exit_type == "SL":
                    trade.stop_loss_hit = True
                    trade.stop_loss_price = price
                else:
                    trade.exit_manager_triggered = True
            else:
                return False, 0.0

            # Asegurar que no cerramos más de lo que tenemos
            quantity = min(quantity, trade.current_position)

            # Calcular P&L
            if trade.direction == "LONG":
                pnl = (price - trade.avg_entry_price) * quantity
            else:  # SHORT
                pnl = (trade.avg_entry_price - price) * quantity

            # Calcular comisión
            commission = quantity * self.commission_per_share
            pnl -= commission  # Restar comisión del P&L

            # Añadir ejecución
            action = "SELL" if trade.direction == "LONG" else "BUY_COVER"
            execution = TradeExecution(
                timestamp=timestamp,
                action=action,
                price=price,
                quantity=quantity,
                commission=commission,
                total_cost=(price * quantity) - commission,
                note=f"{exit_type} exit"
            )
            trade.add_execution(execution)

            # Actualizar posición
            trade.current_position -= quantity

            # Actualizar P&L
            trade.realized_pnl += pnl
            if exit_type == "TP1":
                trade.tp1_pnl = pnl
            elif exit_type == "TP2":
                trade.tp2_pnl = pnl
            elif exit_type == "TP3":
                trade.tp3_pnl = pnl
            elif exit_type == "TP4":
                trade.tp4_pnl = pnl
            elif exit_type == "SL":
                trade.stop_loss_pnl = pnl

            # Añadir slippage
            trade.total_slippage += slippage * quantity

            # Actualizar estado
            if trade.current_position == 0:
                trade.last_exit_time = timestamp
                trade.exit_reason = reason
                if trade.total_pnl > 0:
                    trade.status = TradeStatus.CLOSED_WIN
                else:
                    if exit_type == "EXIT_MANAGER":
                        trade.status = TradeStatus.CLOSED_EXIT_MANAGER
                    else:
                        trade.status = TradeStatus.CLOSED_LOSS

                # Remover de active trades
                if trade.symbol in self.active_trades:
                    del self.active_trades[trade.symbol]

                logger.info(
                    f"🏁 Trade #{trade.trade_id} cerrado: {trade.symbol} "
                    f"P&L=${trade.total_pnl:.2f} ({reason.value})"
                )
            else:
                trade.status = TradeStatus.CLOSING
                logger.debug(
                    f"✅ {exit_type} ejecutado: {trade.symbol} @ ${price:.2f} x {quantity} "
                    f"P&L=${pnl:.2f} (quedan {trade.current_position} shares)"
                )

            return True, pnl

        except Exception as e:
            logger.error(f"❌ Error ejecutando exit: {e}")
            return False, 0.0

    def update_all_trades(self, current_prices: Dict[str, float], timestamp: datetime):
        """
        Actualizar todos los trades activos con precios actuales.

        Args:
            current_prices: Dict {symbol: current_price}
            timestamp: Timestamp actual
        """
        for symbol, trade in list(self.active_trades.items()):
            if symbol in current_prices:
                current_price = current_prices[symbol]
                trade.update_unrealized_pnl(current_price)
                trade.update_excursions(current_price)
                trade.bars_held += 1

    def get_active_trades(self) -> List[Trade]:
        """Obtener lista de trades activos"""
        return list(self.active_trades.values())

    def get_closed_trades(self) -> List[Trade]:
        """Obtener lista de trades cerrados"""
        return [t for t in self.trades if t.status in [
            TradeStatus.CLOSED_WIN,
            TradeStatus.CLOSED_LOSS,
            TradeStatus.CLOSED_EXIT_MANAGER
        ]]

    def get_trade_by_symbol(self, symbol: str) -> Optional[Trade]:
        """Obtener trade activo de un símbolo"""
        return self.active_trades.get(symbol)

    def has_active_trade(self, symbol: str) -> bool:
        """Verificar si hay trade activo para un símbolo"""
        return symbol in self.active_trades


if __name__ == "__main__":
    # Test del trade manager
    logging.basicConfig(level=logging.INFO)

    print("📊 TRADE MANAGER - TEST")
    print("=" * 70)

    # Test básico
    print("✅ TradeManager creado correctamente")
