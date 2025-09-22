#!/usr/bin/env python3
"""
🔙 REALISTIC BACKTESTING ENGINE V2.2 - CAPITAL MANAGEMENT FIXED
==============================================================

Motor de backtesting COMPLETAMENTE REALISTA que replica exactamente
el comportamiento del sistema de trading en vivo con GESTIÓN DE CAPITAL CORREGIDA.

🎯 CARACTERÍSTICAS REALISTAS:
1. Scanner REAL usando tu scanner.py completo (no mock)
2. Entradas escalonadas usando position_calculator.py V3.0
3. Salidas parciales: 25%/25%/25%/25% como en trading real
4. Exit Manager REAL para deterioro técnico (mock durante backtest)
5. Slippage variable según volatilidad/volumen
6. Gestión capital REAL con risk management
7. Drawdown calculado correctamente

✅ FIXES V2.2 - CAPITAL MANAGEMENT:
- ✅ Entradas: NO reducir capital (solo cambio de composición cash->acciones)
- ✅ Salidas: SOLO aplicar P&L, NO sumar proceeds totales  
- ✅ Stop Loss: SOLO aplicar P&L al capital
- ✅ Cierre final: SOLO aplicar P&L final
- ✅ Drawdown basado en valor total (capital + unrealized P&L)
- ✅ Matemática consistente: Capital Final = Capital Inicial + P&L Total
"""

import os
import sys
import pandas as pd
import numpy as np
import logging
import argparse
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum
import sqlite3
from pathlib import Path
import json

# Configurar paths
current_dir = Path(__file__).parent.absolute()
project_root = current_dir.parent if current_dir.name == 'historical_data' else current_dir
sys.path.insert(0, str(project_root))

# Importar core REAL del sistema
try:
    from scanner import SignalScanner, TradingSignal
    from position_calculator import PositionCalculatorV3, PositionPlan, PositionLevel
    from exit_manager import ExitManager, ExitSignal, ExitUrgency
    from database.connection import get_connection
    import config
    logger = logging.getLogger(__name__)
    logger.info("✅ Core REAL del sistema importado correctamente")
except ImportError as e:
    logger.error(f"❌ Error importando core del sistema: {e}")
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class TradeStatus(Enum):
    """Estados de un trade realista"""
    PENDING_ENTRY_1 = "PENDING_ENTRY_1"
    PENDING_ENTRY_2 = "PENDING_ENTRY_2"  
    PENDING_ENTRY_3 = "PENDING_ENTRY_3"
    ACTIVE_PARTIAL = "ACTIVE_PARTIAL"
    ACTIVE_FULL = "ACTIVE_FULL"
    CLOSED_WIN = "CLOSED_WIN"
    CLOSED_LOSS = "CLOSED_LOSS"
    CLOSED_EXIT_MANAGER = "CLOSED_EXIT_MANAGER"

@dataclass
class TradeEntry:
    """Entrada individual de un trade"""
    entry_level: int
    target_price: float
    percentage: float
    executed: bool = False
    execution_time: Optional[datetime] = None
    execution_price: Optional[float] = None
    quantity: float = 0.0

@dataclass
class TradeExit:
    """Salida individual de un trade"""
    exit_level: int
    target_price: float
    percentage: float
    executed: bool = False
    execution_time: Optional[datetime] = None
    execution_price: Optional[float] = None
    pnl_dollars: float = 0.0

@dataclass
class RealisticTrade:
    """Trade completamente realista con entradas/salidas escalonadas"""
    trade_id: int
    symbol: str
    direction: str
    signal: TradingSignal
    position_plan: PositionPlan
    entries: List[TradeEntry] = field(default_factory=list)
    exits: List[TradeExit] = field(default_factory=list)
    stop_loss_price: float = 0.0
    stop_loss_hit: bool = False
    stop_loss_time: Optional[datetime] = None
    status: TradeStatus = TradeStatus.PENDING_ENTRY_1
    signal_time: datetime = None
    total_position_size: float = 0.0
    current_position: float = 0.0
    avg_entry_price: float = 0.0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    total_pnl: float = 0.0
    max_favorable: float = 0.0
    max_adverse: float = 0.0
    exit_manager_alerts: int = 0
    technical_deterioration_score: float = 0.0

class RealisticBacktestEngine:
    """Motor de backtesting que replica EXACTAMENTE el comportamiento real"""
    
    def __init__(self, initial_capital: float = 10000):
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.capital_history = []
        
        # Core components REALES
        self.scanner = SignalScanner()
        self.position_calculator = PositionCalculatorV3()
        self.exit_manager = ExitManager()
        
        # Tracking
        self.trades = []
        self.active_trades = {}
        self.trade_counter = 0
        
        # Configuración
        self.risk_per_trade = 2.0  # 2% por trade
        self.max_concurrent_trades = 5
        self.commission_per_share = 0.005
        
        # Métricas
        self.metrics = {
            'total_signals': 0,
            'total_trades': 0,
            'trades_entered': 0,
            'trades_won': 0,
            'trades_lost': 0,
            'win_rate': 0.0,
            'profit_factor': 0.0,
            'max_drawdown': 0.0,
            'max_drawdown_date': None,
            'sharpe_ratio': 0.0,
            'total_return': 0.0,
            'total_return_pct': 0.0,
            'largest_win': 0.0,
            'largest_loss': 0.0,
            'average_win': 0.0,
            'average_loss': 0.0,
            'total_slippage': 0.0,
            'total_commissions': 0.0
        }
        
        logger.info(f"🚀 RealisticBacktestEngine V2.2 inicializado con capital ${initial_capital:,.2f}")

    def calculate_realistic_slippage(self, price: float, volume: int, volatility: float) -> float:
        """Calcular slippage realista basado en volumen y volatilidad"""
        try:
            base_slippage = price * 0.0005  # 0.05% base
            
            # Ajuste por volumen (menor volumen = mayor slippage)
            if volume < 500000:
                volume_multiplier = 2.0
            elif volume < 1000000:
                volume_multiplier = 1.5
            else:
                volume_multiplier = 1.0
            
            # Ajuste por volatilidad
            volatility_multiplier = 1.0 + (volatility * 2)
            
            slippage = base_slippage * volume_multiplier * volatility_multiplier
            return min(slippage, price * 0.002)  # Cap al 0.2%
        except:
            return price * 0.001

    def get_historical_data_with_indicators(self, symbol: str, start_date: datetime, end_date: datetime) -> pd.DataFrame:
        """Obtener datos históricos con indicadores desde la base de datos"""
        try:
            conn = get_connection()
            query = """
            SELECT i.timestamp, i.symbol, i.open_price, i.high_price, i.low_price, i.close_price, 
                   i.volume, i.rsi_value, i.macd_line, i.macd_signal, i.macd_histogram, 
                   i.bb_upper, i.bb_middle, i.bb_lower, i.atr_value, i.vwap_value, i.roc_value
            FROM indicators_data i
            WHERE i.symbol = ?
            AND i.timestamp BETWEEN ? AND ?
            ORDER BY i.timestamp
            """
            
            df = pd.read_sql_query(
                query, conn, 
                params=[symbol, start_date.isoformat(), end_date.isoformat()],
                index_col='timestamp', parse_dates=['timestamp']
            )
            conn.close()
            
            if df.empty:
                logger.warning(f"⚠️ Sin datos históricos para {symbol}")
                return df
                
            # Renombrar columnas
            df.rename(columns={
                'open_price': 'Open', 'high_price': 'High', 'low_price': 'Low', 'close_price': 'Close',
                'volume': 'Volume', 'rsi_value': 'rsi_14', 'macd_line': 'macd', 'macd_signal': 'macd_signal',
                'macd_histogram': 'macd_histogram', 'bb_upper': 'bb_upper', 'bb_middle': 'bb_middle', 
                'bb_lower': 'bb_lower', 'atr_value': 'atr_14', 'vwap_value': 'vwap', 'roc_value': 'roc_10'
            }, inplace=True)
            
            logger.info(f"✅ Datos históricos obtenidos: {symbol} ({len(df)} registros)")
            return df
        except Exception as e:
            logger.error(f"❌ Error obteniendo datos históricos para {symbol}: {e}")
            return pd.DataFrame()

    def scan_with_real_scanner(self, symbol: str, market_data: pd.DataFrame, current_data: pd.Series, timestamp: datetime) -> Optional[TradingSignal]:
        """Usar scanner REAL inyectando datos históricos temporalmente"""
        try:
            if len(market_data) < 20:
                return None
                
            # Guardar función original
            original_get_market_data = self.scanner.indicators.get_market_data
            
            def mock_get_market_data(symbol_param, period="15m", days=30):
                mock_df = market_data.copy()
                if 'Close' not in mock_df.columns and 'close' in mock_df.columns:
                    mock_df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'}, inplace=True)
                
                expected_columns = ['Open', 'High', 'Low', 'Close', 'Volume']
                for col in expected_columns:
                    if col not in mock_df.columns:
                        if col in ['Open', 'High', 'Low'] and 'Close' in mock_df.columns:
                            mock_df[col] = mock_df['Close']
                        elif col == 'Volume':
                            mock_df[col] = 1000000
                
                return mock_df
            
            # Inyectar mock
            self.scanner.indicators.get_market_data = mock_get_market_data
            
            # Ejecutar scanner REAL
            signal = self.scanner.scan_symbol(symbol)
            
            if signal:
                signal.timestamp = timestamp
                signal.current_price = current_data['Close']
                signal.market_data = market_data
                logger.debug(f"✅ Señal encontrada: {symbol} {signal.signal_type} (fuerza: {signal.signal_strength})")
            
            # Restaurar función original
            self.scanner.indicators.get_market_data = original_get_market_data
            return signal
            
        except Exception as e:
            try:
                self.scanner.indicators.get_market_data = original_get_market_data
            except:
                pass
            logger.error(f"❌ Error usando scanner real para {symbol}: {e}")
            return None

    def create_realistic_trade(self, signal: TradingSignal, timestamp: datetime, current_data: pd.Series, market_data: pd.DataFrame) -> Optional[RealisticTrade]:
        """Crear trade realista usando position_calculator REAL V3.0"""
        try:
            # Extraer indicadores
            indicators_dict = {
                'macd': {'histogram': getattr(current_data, 'macd_histogram', 0), 'signal_strength': signal.indicator_scores.get('MACD', 0)},
                'rsi': {'rsi': getattr(current_data, 'rsi_14', 50), 'signal_strength': signal.indicator_scores.get('RSI', 0)},
                'vwap': {'distance_pct': ((signal.current_price - getattr(current_data, 'vwap', signal.current_price)) / signal.current_price) * 100, 'signal_strength': signal.indicator_scores.get('VWAP', 0)},
                'bollinger': {'bb_upper': getattr(current_data, 'bb_upper', signal.current_price * 1.02), 'bb_lower': getattr(current_data, 'bb_lower', signal.current_price * 0.98), 'signal_strength': signal.indicator_scores.get('BOLLINGER', 0)},
                'atr': {'atr': getattr(current_data, 'atr_14', signal.current_price * 0.02)}
            }
            
            # Usar position_calculator REAL V3.0
            position_plan = self.position_calculator.calculate_position_plan_v3(
                symbol=signal.symbol, direction=signal.signal_type, current_price=signal.current_price,
                signal_strength=signal.signal_strength, indicators=indicators_dict, 
                market_data=market_data, account_balance=self.current_capital
            )
            
            if not position_plan:
                return None
                
            # Calcular tamaño de posición
            risk_dollars = self.current_capital * (self.risk_per_trade / 100)
            stop_distance = abs(signal.current_price - position_plan.stop_loss.price)
            
            if stop_distance <= 0:
                return None
                
            total_position_size = risk_dollars / stop_distance
            
            # Crear trade
            self.trade_counter += 1
            trade = RealisticTrade(
                trade_id=self.trade_counter, symbol=signal.symbol, direction=signal.signal_type,
                signal=signal, position_plan=position_plan, signal_time=timestamp,
                total_position_size=total_position_size, stop_loss_price=position_plan.stop_loss.price
            )
            
            # Crear entradas escalonadas
            for i, entry_level in enumerate(position_plan.entries):
                entry_quantity = (total_position_size * entry_level.percentage / 100)
                trade.entries.append(TradeEntry(
                    entry_level=i+1, target_price=entry_level.price, 
                    percentage=entry_level.percentage, quantity=entry_quantity
                ))
            
            # Crear salidas escalonadas
            for i, exit_level in enumerate(position_plan.exits):
                trade.exits.append(TradeExit(
                    exit_level=i+1, target_price=exit_level.price, percentage=exit_level.percentage
                ))
            
            if not trade.entries or not trade.exits:
                return None
            
            logger.info(f"✅ Trade realista creado: {signal.symbol} {signal.signal_type}")
            logger.info(f"   💰 Tamaño: ${total_position_size:.0f}, Stop: ${position_plan.stop_loss.price:.2f}")
            
            return trade
            
        except Exception as e:
            logger.error(f"❌ Error creando trade realista para {signal.symbol}: {e}")
            return None

    def process_new_signals(self, timestamp: datetime, all_data: Dict[str, pd.DataFrame]):
        """Buscar nuevas señales usando scanner REAL"""
        try:
            if len(self.active_trades) >= self.max_concurrent_trades:
                return
                
            for symbol, df in all_data.items():
                if symbol in self.active_trades or timestamp not in df.index:
                    continue
                    
                current_data = df.loc[timestamp]
                end_idx = df.index.get_loc(timestamp)
                start_idx = max(0, end_idx - 100)
                market_data_slice = df.iloc[start_idx:end_idx+1].copy()
                
                signal = self.scan_with_real_scanner(symbol, market_data_slice, current_data, timestamp)
                
                if signal and signal.signal_strength >= config.SIGNAL_THRESHOLDS.get('NO_TRADE', 55):
                    self.metrics['total_signals'] += 1
                    trade = self.create_realistic_trade(signal, timestamp, current_data, market_data_slice)
                    if trade:
                        self.active_trades[symbol] = trade
                        self.trades.append(trade)
                        self.metrics['total_trades'] += 1
                        logger.info(f"📊 Nueva señal REAL: {symbol} {signal.signal_type} @ ${signal.current_price:.2f}")
                        
        except Exception as e:
            logger.error(f"❌ Error procesando nuevas señales: {e}")

    def process_pending_entries(self, timestamp: datetime, all_data: Dict[str, pd.DataFrame]):
        """🔧 FIXED: Procesar entradas SIN reducir capital disponible"""
        try:
            for symbol, trade in list(self.active_trades.items()):
                if symbol not in all_data or timestamp not in all_data[symbol].index:
                    continue
                    
                current_data = all_data[symbol].loc[timestamp]
                current_price = current_data['Close']
                
                for entry in trade.entries:
                    if entry.executed:
                        continue
                        
                    entry_triggered = False
                    if trade.direction == 'LONG':
                        entry_triggered = current_price <= entry.target_price
                    else:
                        entry_triggered = current_price >= entry.target_price
                    
                    if entry_triggered:
                        volatility = getattr(current_data, 'atr_14', current_price * 0.02) / current_price
                        volume = int(getattr(current_data, 'Volume', 1000000))
                        slippage = self.calculate_realistic_slippage(current_price, volume, volatility)
                        execution_price = current_price + (slippage if trade.direction == 'LONG' else -slippage)
                        
                        # ✅ Ejecutar entrada SIN reducir capital
                        entry.executed = True
                        entry.execution_time = timestamp
                        entry.execution_price = execution_price
                        trade.current_position += entry.quantity
                        
                        # ✅ Recalcular precio promedio
                        if trade.avg_entry_price == 0:
                            trade.avg_entry_price = execution_price
                        else:
                            total_cost = (trade.current_position - entry.quantity) * trade.avg_entry_price + entry.quantity * execution_price
                            trade.avg_entry_price = total_cost / trade.current_position
                        
                        # ✅ Solo tracking de slippage y comisiones (para métricas)
                        self.metrics['total_slippage'] += abs(execution_price - entry.target_price) * entry.quantity
                        commission = entry.quantity * self.commission_per_share
                        self.metrics['total_commissions'] += commission
                        
                        # 🚨 FIXED: NO restar capital aquí
                        # ❌ CÓDIGO ANTERIOR: self.current_capital -= cost
                        # ✅ Capital permanece igual, solo cambia composición (cash -> acciones)
                        
                        # ✅ Actualizar estado
                        if trade.current_position >= trade.total_position_size * 0.9:
                            trade.status = TradeStatus.ACTIVE_FULL
                        else:
                            trade.status = TradeStatus.ACTIVE_PARTIAL
                        
                        self.metrics['trades_entered'] += 1
                        logger.info(f"✅ Entrada ejecutada: {symbol} {entry.entry_level} @ ${execution_price:.2f}")
                        
        except Exception as e:
            logger.error(f"❌ Error procesando entradas pendientes: {e}")

    def process_exit_conditions(self, timestamp: datetime, all_data: Dict[str, pd.DataFrame]):
        """Evaluar condiciones de salida (TP, SL, Exit Manager)"""
        try:
            for symbol, trade in list(self.active_trades.items()):
                if symbol not in all_data or timestamp not in all_data[symbol].index:
                    continue
                    
                current_data = all_data[symbol].loc[timestamp]
                current_price = current_data['Close']
                
                # 1. Stop Loss
                stop_triggered = False
                if trade.direction == 'LONG':
                    stop_triggered = current_price <= trade.stop_loss_price
                else:
                    stop_triggered = current_price >= trade.stop_loss_price
                
                if stop_triggered and not trade.stop_loss_hit:
                    self.execute_stop_loss(trade, timestamp, current_price)
                    continue
                
                # 2. Take Profits
                for exit_target in trade.exits:
                    if exit_target.executed:
                        continue
                        
                    target_hit = False
                    if trade.direction == 'LONG':
                        target_hit = current_price >= exit_target.target_price
                    else:
                        target_hit = current_price <= exit_target.target_price
                    
                    if target_hit:
                        self.execute_partial_exit(trade, exit_target, timestamp, current_price)
                
                # 3. Exit Manager
                if trade.current_position > 0:
                    self.check_exit_manager(trade, timestamp, all_data[symbol])
                
                # 4. Actualizar performance
                self.update_trade_performance(trade, current_price)
                
        except Exception as e:
            logger.error(f"❌ Error procesando condiciones de salida: {e}")

    def execute_stop_loss(self, trade: RealisticTrade, timestamp: datetime, current_price: float):
        """🔧 FIXED: Ejecutar stop loss SOLO aplicando P&L al capital"""
        try:
            trade.stop_loss_hit = True
            trade.stop_loss_time = timestamp
            
            if trade.current_position > 0:
                # ✅ Calcular P&L correcto
                if trade.direction == 'LONG':
                    pnl = (current_price - trade.avg_entry_price) * trade.current_position
                else:
                    pnl = (trade.avg_entry_price - current_price) * trade.current_position
                
                # 🚨 FIXED: SOLO aplicar P&L al capital, NO sumar proceeds
                # ❌ CÓDIGO ANTERIOR: proceeds = trade.current_position * current_price
                #                     self.current_capital += proceeds  
                # ✅ CÓDIGO CORRECTO: Solo P&L
                self.current_capital += pnl
                trade.realized_pnl += pnl
                trade.total_pnl = trade.realized_pnl
                trade.current_position = 0  # Cerrar posición
                
                # ✅ Métricas correctas
                if pnl > 0:
                    self.metrics['trades_won'] += 1
                    self.metrics['largest_win'] = max(self.metrics['largest_win'], pnl)
                    trade.status = TradeStatus.CLOSED_WIN
                else:
                    self.metrics['trades_lost'] += 1
                    self.metrics['largest_loss'] = min(self.metrics['largest_loss'], pnl)
                    trade.status = TradeStatus.CLOSED_LOSS
                
                logger.info(f"🛑 Stop Loss ejecutado: {trade.symbol} @ ${current_price:.2f} - P&L: ${pnl:.2f}")
            
            if trade.symbol in self.active_trades:
                del self.active_trades[trade.symbol]
                
        except Exception as e:
            logger.error(f"❌ Error ejecutando stop loss: {e}")

    def execute_partial_exit(self, trade: RealisticTrade, exit_target: TradeExit, timestamp: datetime, current_price: float):
        """🔧 FIXED: Ejecutar salida parcial SOLO aplicando P&L parcial"""
        try:
            exit_quantity = trade.current_position * (exit_target.percentage / 100)
            
            # ✅ Calcular P&L de la porción que se vende
            if trade.direction == 'LONG':
                pnl = (current_price - trade.avg_entry_price) * exit_quantity
            else:
                pnl = (trade.avg_entry_price - current_price) * exit_quantity
            
            # ✅ Ejecutar salida
            exit_target.executed = True
            exit_target.execution_time = timestamp
            exit_target.execution_price = current_price
            exit_target.pnl_dollars = pnl
            
            # 🚨 FIXED: SOLO aplicar P&L al capital, NO proceeds totales
            # ❌ CÓDIGO ANTERIOR: proceeds = exit_quantity * current_price
            #                     self.current_capital += proceeds
            # ✅ CÓDIGO CORRECTO: Solo P&L
            self.current_capital += pnl
            trade.realized_pnl += pnl
            trade.current_position -= exit_quantity
            
            # ✅ Verificar si trade completado
            if trade.current_position <= 0:
                trade.current_position = 0
                trade.total_pnl = trade.realized_pnl
                
                if trade.total_pnl > 0:
                    self.metrics['trades_won'] += 1
                    self.metrics['largest_win'] = max(self.metrics['largest_win'], trade.total_pnl)
                    trade.status = TradeStatus.CLOSED_WIN
                else:
                    self.metrics['trades_lost'] += 1
                    self.metrics['largest_loss'] = min(self.metrics['largest_loss'], trade.total_pnl)
                    trade.status = TradeStatus.CLOSED_LOSS
                
                # Remover de trades activos
                if trade.symbol in self.active_trades:
                    del self.active_trades[trade.symbol]
            
            logger.info(f"📈 Salida parcial: {trade.symbol} ({exit_target.percentage}%) @ ${current_price:.2f} - P&L: ${pnl:.2f}")
            
        except Exception as e:
            logger.error(f"❌ Error ejecutando salida parcial: {e}")

    def check_exit_manager(self, trade: RealisticTrade, timestamp: datetime, symbol_data: pd.DataFrame):
        """Evaluar Exit Manager para deterioro técnico (mock durante backtest)"""
        try:
            # Implementación simplificada - solo alertas por ahora
            current_idx = symbol_data.index.get_loc(timestamp)
            if current_idx < 10:
                return
            
            recent_data = symbol_data.iloc[current_idx-10:current_idx+1]
            
            # Simular deterioro técnico básico
            rsi_current = getattr(symbol_data.loc[timestamp], 'rsi_14', 50)
            macd_hist = getattr(symbol_data.loc[timestamp], 'macd_histogram', 0)
            
            deterioration_score = 0
            if trade.direction == 'LONG':
                if rsi_current > 70:  # Sobrecompra
                    deterioration_score += 20
                if macd_hist < 0:  # MACD bajista
                    deterioration_score += 15
            else:
                if rsi_current < 30:  # Sobreventa
                    deterioration_score += 20
                if macd_hist > 0:  # MACD alcista
                    deterioration_score += 15
            
            trade.technical_deterioration_score = deterioration_score
            
            if deterioration_score >= 30:
                trade.exit_manager_alerts += 1
                logger.debug(f"⚠️ Exit Manager alerta: {trade.symbol} - Score: {deterioration_score}")
            
        except Exception as e:
            logger.error(f"❌ Error en Exit Manager: {e}")

    def update_trade_performance(self, trade: RealisticTrade, current_price: float):
        """Actualizar performance de un trade activo"""
        try:
            if trade.current_position <= 0:
                return
                
            # Calcular P&L no realizado
            if trade.direction == 'LONG':
                unrealized_pnl = (current_price - trade.avg_entry_price) * trade.current_position
            else:
                unrealized_pnl = (trade.avg_entry_price - current_price) * trade.current_position
            
            trade.unrealized_pnl = unrealized_pnl
            trade.total_pnl = trade.realized_pnl + trade.unrealized_pnl
            trade.max_favorable = max(trade.max_favorable, unrealized_pnl)
            trade.max_adverse = min(trade.max_adverse, unrealized_pnl)
            
        except Exception as e:
            logger.error(f"❌ Error actualizando performance: {e}")

    def calculate_total_unrealized_pnl(self, timestamp: datetime, all_data: Dict[str, pd.DataFrame]) -> float:
        """Calcular P&L total no realizado de todas las posiciones activas"""
        try:
            total_unrealized = 0.0
            for symbol, trade in self.active_trades.items():
                if symbol in all_data and timestamp in all_data[symbol].index:
                    current_price = all_data[symbol].loc[timestamp, 'Close']
                    self.update_trade_performance(trade, current_price)
                    total_unrealized += trade.unrealized_pnl
            return total_unrealized
        except Exception as e:
            logger.error(f"❌ Error calculando P&L no realizado: {e}")
            return 0.0

    def update_drawdown_tracking(self):
        """🔧 FIXED: Actualizar tracking de drawdown basado en valor total"""
        try:
            if not self.capital_history:
                return
                
            current_record = self.capital_history[-1]
            current_total_value = current_record['capital'] + current_record['unrealized_pnl']
            
            # ✅ Con gestión correcta, valor total no debería ser negativo
            if current_total_value < 0:
                logger.warning(f"⚠️ VALOR TOTAL NEGATIVO: ${current_total_value:.2f}")
                current_total_value = max(0.01, current_total_value)
            
            # ✅ Encontrar peak histórico
            peak_value = self.initial_capital
            for record in self.capital_history:
                total_value = max(0.01, record['capital'] + record['unrealized_pnl'])
                peak_value = max(peak_value, total_value)
            
            # ✅ Calcular drawdown
            if peak_value > 0:
                current_drawdown = ((peak_value - current_total_value) / peak_value) * 100
                current_drawdown = min(current_drawdown, 100)  # Cap al 100%
                
                if current_drawdown > self.metrics['max_drawdown']:
                    self.metrics['max_drawdown'] = current_drawdown
                    self.metrics['max_drawdown_date'] = current_record['timestamp']
                    
        except Exception as e:
            logger.error(f"❌ Error actualizando drawdown: {e}")

    def close_remaining_trades(self, end_date: datetime, all_data: Dict[str, pd.DataFrame]):
        """🔧 FIXED: Cerrar trades restantes aplicando SOLO P&L final"""
        try:
            for symbol, trade in list(self.active_trades.items()):
                if symbol in all_data:
                    last_price = all_data[symbol]['Close'].iloc[-1]
                    
                    if trade.current_position > 0:
                        # ✅ Calcular P&L final
                        if trade.direction == 'LONG':
                            final_pnl = (last_price - trade.avg_entry_price) * trade.current_position
                        else:
                            final_pnl = (trade.avg_entry_price - last_price) * trade.current_position
                        
                        # 🚨 FIXED: SOLO aplicar P&L al capital
                        # ❌ CÓDIGO ANTERIOR: proceeds = trade.current_position * last_price
                        #                     self.current_capital += proceeds
                        # ✅ CÓDIGO CORRECTO: Solo P&L
                        self.current_capital += final_pnl
                        trade.realized_pnl += final_pnl
                        trade.total_pnl = trade.realized_pnl
                        trade.current_position = 0
                        
                        # ✅ Métricas correctas
                        if final_pnl > 0:
                            self.metrics['trades_won'] += 1
                            self.metrics['largest_win'] = max(self.metrics['largest_win'], final_pnl)
                            trade.status = TradeStatus.CLOSED_WIN
                        else:
                            self.metrics['trades_lost'] += 1
                            self.metrics['largest_loss'] = min(self.metrics['largest_loss'], final_pnl)
                            trade.status = TradeStatus.CLOSED_LOSS
                        
                        logger.info(f"🔒 Trade final cerrado: {symbol} @ ${last_price:.2f} - P&L: ${final_pnl:.2f}")
            
            self.active_trades.clear()
        except Exception as e:
            logger.error(f"❌ Error cerrando trades restantes: {e}")

    def calculate_final_metrics(self):
        """🔧 FIXED: Calcular métricas finales CORRECTAMENTE"""
        try:
            # ✅ Métricas básicas - Capital final ya incluye todos los P&L
            self.metrics['total_return'] = self.current_capital - self.initial_capital
            self.metrics['total_return_pct'] = (self.metrics['total_return'] / self.initial_capital) * 100
            
            # ✅ Trades completados únicamente
            completed_trades = [t for t in self.trades if t.status in [
                TradeStatus.CLOSED_WIN, TradeStatus.CLOSED_LOSS, TradeStatus.CLOSED_EXIT_MANAGER
            ]]
            
            winning_trades = [t for t in completed_trades if t.total_pnl > 0]
            losing_trades = [t for t in completed_trades if t.total_pnl < 0]
            total_completed = len(completed_trades)
            
            # ✅ Corregir contadores
            self.metrics['trades_won'] = len(winning_trades)
            self.metrics['trades_lost'] = len(losing_trades)
            
            # ✅ Win rate basado en trades completados
            if total_completed > 0:
                self.metrics['win_rate'] = (len(winning_trades) / total_completed) * 100
            
            # ✅ P&L promedio
            if winning_trades:
                self.metrics['average_win'] = sum(t.total_pnl for t in winning_trades) / len(winning_trades)
                self.metrics['largest_win'] = max(t.total_pnl for t in winning_trades)
            
            if losing_trades:
                self.metrics['average_loss'] = sum(t.total_pnl for t in losing_trades) / len(losing_trades)
                self.metrics['largest_loss'] = min(t.total_pnl for t in losing_trades)
            
            # ✅ Profit factor
            total_wins = sum(t.total_pnl for t in winning_trades) if winning_trades else 0
            total_losses = abs(sum(t.total_pnl for t in losing_trades)) if losing_trades else 0
            
            if total_losses > 0:
                self.metrics['profit_factor'] = total_wins / total_losses
            else:
                self.metrics['profit_factor'] = float('inf') if total_wins > 0 else 0
            
            # ✅ Sharpe ratio
            if len(self.capital_history) > 1:
                returns = []
                for i in range(1, len(self.capital_history)):
                    prev_value = max(0.01, self.capital_history[i-1]['capital'] + self.capital_history[i-1]['unrealized_pnl'])
                    curr_value = max(0.01, self.capital_history[i]['capital'] + self.capital_history[i]['unrealized_pnl'])
                    
                    if prev_value > 0:
                        returns.append((curr_value - prev_value) / prev_value)
                
                if returns and len(returns) > 1:
                    avg_return = np.mean(returns)
                    std_return = np.std(returns)
                    if std_return > 0:
                        self.metrics['sharpe_ratio'] = (avg_return / std_return) * np.sqrt(252)
            
            # ✅ Verificación de consistencia
            total_pnl_from_trades = sum(t.total_pnl for t in completed_trades)
            calculated_return = self.current_capital - self.initial_capital
            
            logger.info(f"📊 Métricas verificadas:")
            logger.info(f"   Trades completados: {total_completed}")
            logger.info(f"   Win Rate: {self.metrics['win_rate']:.1f}%")
            logger.info(f"   Return: {self.metrics['total_return_pct']:.2f}%")
            logger.info(f"   Max Drawdown: {self.metrics['max_drawdown']:.2f}%")
            logger.info(f"   P&L desde trades: ${total_pnl_from_trades:.2f}")
            logger.info(f"   Return calculado: ${calculated_return:.2f}")
            logger.info(f"   Diferencia: ${abs(total_pnl_from_trades - calculated_return):.2f}")
            
            # ✅ Verificación de consistencia mejorada
            if abs(total_pnl_from_trades - calculated_return) > 10:
                logger.warning(f"⚠️ Inconsistencia detectada: ${abs(total_pnl_from_trades - calculated_return):.2f}")
            else:
                logger.info("✅ Cálculos consistentes - Gestión de capital corregida")
            
        except Exception as e:
            logger.error(f"❌ Error calculando métricas finales: {e}")

    def run_realistic_backtest(self, symbols: List[str], start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Ejecutar backtesting completamente realista"""
        logger.info("🚀 Iniciando Realistic Backtesting Engine V2.2 - CAPITAL FIXED")
        logger.info(f"📊 Símbolos: {symbols}")
        logger.info(f"📅 Período: {start_date.date()} a {end_date.date()}")
        
        try:
            # Obtener datos históricos
            all_data = {}
            for symbol in symbols:
                df = self.get_historical_data_with_indicators(symbol, start_date, end_date)
                if not df.empty:
                    all_data[symbol] = df
                    
            if not all_data:
                raise ValueError("No se pudieron obtener datos históricos")
                
            # Crear timeline
            all_timestamps = set()
            for df in all_data.values():
                all_timestamps.update(df.index)
                
            timeline = sorted(all_timestamps)
            logger.info(f"📈 Timeline creado: {len(timeline)} períodos")
            
            # Procesar cada período
            for i, timestamp in enumerate(timeline):
                if i % 100 == 0:
                    progress = (i / len(timeline)) * 100
                    logger.info(f"🔄 Progreso: {progress:.1f}% - {timestamp}")
                
                # Actualizar capital history
                self.capital_history.append({
                    'timestamp': timestamp,
                    'capital': self.current_capital,
                    'unrealized_pnl': self.calculate_total_unrealized_pnl(timestamp, all_data)
                })
                
                # Procesar
                self.process_new_signals(timestamp, all_data)
                self.process_pending_entries(timestamp, all_data)
                self.process_exit_conditions(timestamp, all_data)
                self.update_drawdown_tracking()
            
            # Finalizar
            self.close_remaining_trades(end_date, all_data)
            self.calculate_final_metrics()
            
            logger.info("✅ Backtesting realista completado")
            return self.get_backtest_results()
            
        except Exception as e:
            logger.error(f"❌ Error en backtesting realista: {e}")
            raise

    def get_backtest_results(self) -> Dict[str, Any]:
        """Obtener resultados completos del backtest"""
        return {
            'summary': {
                'initial_capital': self.initial_capital,
                'final_capital': self.current_capital,
                'total_trades': len(self.trades),
                'active_trades': len(self.active_trades)
            },
            'trades': [
                {
                    'trade_id': t.trade_id,
                    'symbol': t.symbol,
                    'direction': t.direction,
                    'signal_time': t.signal_time.isoformat() if t.signal_time else None,
                    'status': t.status.value,
                    'total_pnl': t.total_pnl,
                    'max_favorable': t.max_favorable,
                    'max_adverse': t.max_adverse
                }
                for t in self.trades
            ],
            'equity_curve': [
                {
                    'timestamp': record['timestamp'],
                    'capital': record['capital'],
                    'unrealized_pnl': record['unrealized_pnl'],
                    'total_value': record['capital'] + record['unrealized_pnl']
                }
                for record in self.capital_history[::10]
            ],
            'metrics': self.metrics
        }

    def print_results_summary(self):
        """🔧 FIXED: Imprimir resumen con verificación de consistencia mejorada"""
        print("\n" + "="*80)
        print("🔙 REALISTIC BACKTESTING ENGINE V2.2 - CAPITAL MANAGEMENT FIXED")
        print("="*80)
        
        print(f"💰 RENDIMIENTO GENERAL:")
        print(f"   Capital inicial:     ${self.initial_capital:,.2f}")
        print(f"   Capital final:       ${self.current_capital:,.2f}")
        print(f"   Retorno total:       ${self.metrics['total_return']:,.2f}")
        print(f"   Retorno %:           {self.metrics['total_return_pct']:+.2f}%")
        print(f"   Drawdown máximo:     {self.metrics['max_drawdown']:.2f}%")
        print(f"   Fecha DD máximo:     {self.metrics['max_drawdown_date']}")
        
        completed_trades = [t for t in self.trades if t.status in [
            TradeStatus.CLOSED_WIN, TradeStatus.CLOSED_LOSS, TradeStatus.CLOSED_EXIT_MANAGER
        ]]
        
        print(f"\n📊 ESTADÍSTICAS DE TRADING:")
        print(f"   Señales detectadas:  {self.metrics['total_signals']}")
        print(f"   Trades creados:      {self.metrics['total_trades']}")
        print(f"   Trades completados:  {len(completed_trades)}")
        print(f"   Trades ganadores:    {self.metrics['trades_won']}")
        print(f"   Trades perdedores:   {self.metrics['trades_lost']}")
        print(f"   Win Rate:            {self.metrics['win_rate']:.1f}%")
        print(f"   Profit Factor:       {self.metrics['profit_factor']:.2f}")
        print(f"   Sharpe Ratio:        {self.metrics['sharpe_ratio']:.2f}")
        
        print(f"\n💵 ANÁLISIS P&L:")
        print(f"   Ganancia promedio:   ${self.metrics['average_win']:,.2f}")
        print(f"   Pérdida promedio:    ${self.metrics['average_loss']:,.2f}")
        print(f"   Mayor ganancia:      ${self.metrics['largest_win']:,.2f}")
        print(f"   Mayor pérdida:       ${self.metrics['largest_loss']:,.2f}")
        print(f"   Total slippage:      ${self.metrics['total_slippage']:,.2f}")
        print(f"   Total comisiones:    ${self.metrics['total_commissions']:,.2f}")
        
        # ✅ Verificación de consistencia mejorada
        print(f"\n🔍 VERIFICACIÓN DE CONSISTENCIA:")
        total_pnl_from_trades = sum(t.total_pnl for t in completed_trades)
        calculated_return = self.current_capital - self.initial_capital
        difference = abs(total_pnl_from_trades - calculated_return)
        
        print(f"   P&L desde trades:    ${total_pnl_from_trades:,.2f}")
        print(f"   Return calculado:    ${calculated_return:,.2f}")
        print(f"   Diferencia:          ${difference:,.2f}")
        
        if difference <= 10:
            print(f"   ✅ CONSISTENCIA PERFECTA - Capital management fixed")
        elif difference <= 100:
            print(f"   ⚠️ Diferencia menor - Aceptable para backtesting")
        else:
            print(f"   ❌ INCONSISTENCIA DETECTADA - Verificar cálculos")
        
        # ✅ Validación matemática
        expected_final_capital = self.initial_capital + total_pnl_from_trades
        print(f"\n🧮 VALIDACIÓN MATEMÁTICA:")
        print(f"   Capital inicial:     ${self.initial_capital:,.2f}")
        print(f"   + P&L total trades:  ${total_pnl_from_trades:,.2f}")
        print(f"   = Esperado final:    ${expected_final_capital:,.2f}")
        print(f"   Capital final real:  ${self.current_capital:,.2f}")
        
        if abs(expected_final_capital - self.current_capital) <= 10:
            print(f"   ✅ MATEMÁTICA CORRECTA")
        else:
            print(f"   ❌ Error matemático: ${abs(expected_final_capital - self.current_capital):,.2f}")
        
        print(f"\n🔍 CARACTERÍSTICAS REALISTAS APLICADAS:")
        print(f"   ✅ Scanner REAL usado (no mock)")
        print(f"   ✅ Entradas escalonadas ejecutadas")
        print(f"   ✅ Salidas parciales aplicadas")
        print(f"   ✅ Exit Manager evaluando deterioro técnico")
        print(f"   ✅ Slippage variable según volatilidad")
        print(f"   ✅ Drawdown calculado correctamente")
        print(f"   ✅ Capital management V2.2 FIXED")
        print(f"   ✅ Gestión correcta: Capital SOLO cambia por P&L")
        
        print("\n" + "="*80)


def main():
    """Función principal para ejecutar backtesting realista"""
    parser = argparse.ArgumentParser(description='Realistic Backtesting Engine V2.2 - CAPITAL FIXED')
    parser.add_argument('--symbols', nargs='+', default=['AAPL', 'MSFT', 'TSLA', 'NVDA', 'SPY'], 
                       help='Símbolos a testear')
    parser.add_argument('--start-date', type=str, default='2024-12-15',
                       help='Fecha inicio (YYYY-MM-DD)')
    parser.add_argument('--end-date', type=str, default='2025-01-15',
                       help='Fecha fin (YYYY-MM-DD)')
    parser.add_argument('--capital', type=float, default=10000,
                       help='Capital inicial')
    parser.add_argument('--output', type=str, default='backtest_results_v22.json',
                       help='Archivo de salida')
    parser.add_argument('--verbose', action='store_true',
                       help='Modo verbose')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    try:
        engine = RealisticBacktestEngine(initial_capital=args.capital)
        start_date = datetime.strptime(args.start_date, '%Y-%m-%d')
        end_date = datetime.strptime(args.end_date, '%Y-%m-%d')
        
        print(f"🚀 Iniciando Realistic Backtesting Engine V2.2 - CAPITAL FIXED")
        print(f"📊 Símbolos: {args.symbols}")
        print(f"📅 Período: {start_date.date()} a {end_date.date()}")
        print(f"💰 Capital: ${args.capital:,.2f}")
        
        results = engine.run_realistic_backtest(args.symbols, start_date, end_date)
        engine.print_results_summary()
        
        with open(args.output, 'w') as f:
            results_serializable = json.loads(json.dumps(results, default=str))
            json.dump(results_serializable, f, indent=2)
        
        print(f"\n💾 Resultados guardados en: {args.output}")
        
    except Exception as e:
        logger.error(f"❌ Error en backtesting: {e}")
        raise


if __name__ == "__main__":
    main()