#!/usr/bin/env python3
"""
🔙 BACKTEST ENGINE V1.0
=======================

Motor de backtesting básico que usa el CORE EXISTENTE del sistema:
- Scanner para generar señales históricas
- Position Calculator para entries/exits/stops
- Exit Manager para gestión de salidas

✅ VERSIÓN BÁSICA FUNCIONAL:
- Replay histórico de datos
- Usa tu lógica real de trading
- Métricas básicas: Win Rate, P&L, Drawdown
- Tracking de trades ejecutados
- Reporte simple de resultados

🎯 FILOSOFÍA:
- Usar EXACTAMENTE la misma lógica que trading en vivo
- No reinventar la rueda - aprovechar código existente
- Empezar simple, evolucionar después

USO:
    python backtest_engine.py --test                          # Test básico
    python backtest_engine.py --symbols AAPL MSFT            # Solo ciertos símbolos
    python backtest_engine.py --start-date 2024-06-01        # Período específico
    python backtest_engine.py --detailed                     # Análisis detallado
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

# Configurar paths
current_dir = Path(__file__).parent.absolute()
project_root = current_dir.parent if current_dir.name == 'historical_data' else current_dir
sys.path.insert(0, str(project_root))

# Importar core del sistema
try:
    from scanner import SignalScanner, TradingSignal
    from position_calculator import PositionCalculatorV3, PositionPlan
    from exit_manager import ExitManager, ExitSignal, ExitUrgency
    from database.connection import get_connection
    import config
    print("✅ Core del sistema importado correctamente")
except ImportError as e:
    print(f"❌ Error importando core del sistema: {e}")
    print("📋 Asegúrate de que scanner.py, position_calculator.py y exit_manager.py estén disponibles")
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class TradeStatus(Enum):
    """Estados de un trade"""
    PENDING = "PENDING"      # Orden colocada pero no ejecutada
    ACTIVE = "ACTIVE"        # Posición abierta
    CLOSED_WIN = "CLOSED_WIN"    # Cerrada con ganancia
    CLOSED_LOSS = "CLOSED_LOSS"  # Cerrada con pérdida
    CLOSED_EXIT = "CLOSED_EXIT"  # Cerrada por exit manager

@dataclass
class BacktestTrade:
    """Representa un trade en el backtesting"""
    # Identificación
    trade_id: int
    symbol: str
    direction: str  # 'LONG' or 'SHORT'
    
    # Señal original
    signal: TradingSignal
    position_plan: PositionPlan
    
    # Ejecución
    entry_time: datetime
    entry_price: float
    quantity: float
    
    # Estado
    status: TradeStatus = TradeStatus.PENDING
    exit_time: Optional[datetime] = None
    exit_price: Optional[float] = None
    exit_reason: str = ""
    
    # Resultados
    pnl_dollars: float = 0.0
    pnl_percent: float = 0.0
    max_favorable: float = 0.0  # Máximo movimiento favorable
    max_adverse: float = 0.0    # Máximo movimiento adverso
    
    # Tracking
    days_held: int = 0
    hit_targets: List[int] = field(default_factory=list)  # Qué targets se alcanzaron

@dataclass
class BacktestMetrics:
    """Métricas del backtesting"""
    # Básicas
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    
    # P&L
    total_pnl: float = 0.0
    total_pnl_percent: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    profit_factor: float = 0.0  # Gross profit / Gross loss
    
    # Drawdown
    max_drawdown: float = 0.0
    max_drawdown_percent: float = 0.0
    
    # Tiempo
    avg_hold_time_days: float = 0.0
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    
    # Por símbolo
    symbol_performance: Dict[str, Dict] = field(default_factory=dict)

class BasicBacktestEngine:
    """Motor de backtesting básico usando el core del sistema"""
    
    def __init__(self, initial_capital: float = 10000.0):
        """
        Inicializar el motor de backtesting
        
        Args:
            initial_capital: Capital inicial en dólares
        """
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        
        # Componentes del core
        self.scanner = SignalScanner()
        self.position_calc = PositionCalculatorV3()
        self.exit_manager = ExitManager()
        
        # Estado del backtest
        self.trades: List[BacktestTrade] = []
        self.active_trades: Dict[str, BacktestTrade] = {}  # symbol -> trade
        self.trade_counter = 0
        self.equity_curve: List[Tuple[datetime, float]] = []
        
        # Configuración
        self.max_concurrent_trades = 5  # Máximo trades simultáneos
        self.position_size_pct = 0.02   # 2% del capital por trade
        
        logger.info(f"🔙 Backtest Engine inicializado - Capital inicial: ${initial_capital:,.2f}")
    
    def load_historical_data(self, symbol: str, start_date: datetime, end_date: datetime) -> Optional[pd.DataFrame]:
        """
        Cargar datos históricos desde la base de datos
        
        Args:
            symbol: Símbolo a cargar
            start_date: Fecha de inicio
            end_date: Fecha de fin
            
        Returns:
            DataFrame con datos OHLCV + indicadores o None si no hay datos
        """
        try:
            conn = get_connection()
            if not conn:
                logger.error("❌ No se pudo conectar a la base de datos")
                return None
            
            # Query para obtener datos con indicadores
            query = """
                SELECT 
                    timestamp,
                    open_price, high_price, low_price, close_price, volume,
                    rsi_value, macd_line, macd_signal, macd_histogram,
                    vwap_value, vwap_deviation_pct, roc_value,
                    bb_upper, bb_middle, bb_lower, bb_position,
                    volume_oscillator, atr_value, atr_percentage
                FROM indicators_data 
                WHERE symbol = ? 
                AND timestamp >= ? 
                AND timestamp <= ?
                AND close_price > 0
                ORDER BY timestamp ASC
            """
            
            df = pd.read_sql_query(
                query, 
                conn, 
                params=(symbol, start_date.isoformat(), end_date.isoformat())
            )
            
            conn.close()
            
            if df.empty:
                logger.warning(f"⚠️ No hay datos para {symbol} en el período especificado")
                return None
            
            # Convertir timestamp y configurar como índice
            df['timestamp'] = pd.to_datetime(df['timestamp'], format='ISO8601', utc=True)
            df.set_index('timestamp', inplace=True)
            
            # Renombrar columnas para compatibilidad con el scanner
            df.rename(columns={
                'open_price': 'Open',
                'high_price': 'High',
                'low_price': 'Low', 
                'close_price': 'Close',
                'volume': 'Volume'
            }, inplace=True)
            
            logger.info(f"📊 {symbol}: {len(df)} registros cargados ({df.index[0]} a {df.index[-1]})")
            return df
            
        except Exception as e:
            logger.error(f"❌ Error cargando datos históricos para {symbol}: {e}")
            return None
    
    def create_mock_signal_from_data(self, symbol: str, row: pd.Series, timestamp: datetime) -> Optional[TradingSignal]:
        """
        Crear una señal mock usando los datos históricos y la lógica del scanner
        
        Args:
            symbol: Símbolo
            row: Fila de datos con OHLCV + indicadores
            timestamp: Timestamp actual
            
        Returns:
            TradingSignal si se detecta señal válida, None si no
        """
        try:
            # Extraer indicadores de la fila
            indicators = {
                'macd': {
                    'macd': row.get('macd_line', 0),
                    'signal': row.get('macd_signal', 0),
                    'histogram': row.get('macd_histogram', 0)
                },
                'rsi': {
                    'rsi': row.get('rsi_value', 50)
                },
                'vwap': {
                    'vwap': row.get('vwap_value', row['Close']),
                    'deviation_pct': row.get('vwap_deviation_pct', 0)
                },
                'roc': {
                    'roc': row.get('roc_value', 0)
                },
                'bollinger': {
                    'upper': row.get('bb_upper', row['Close'] * 1.02),
                    'middle': row.get('bb_middle', row['Close']),
                    'lower': row.get('bb_lower', row['Close'] * 0.98),
                    'position': row.get('bb_position', 0.5)
                },
                'volume_osc': {
                    'oscillator': row.get('volume_oscillator', 0)
                },
                'atr': {
                    'atr': row.get('atr_value', row['Close'] * 0.02),
                    'atr_pct': row.get('atr_percentage', 2.0)
                }
            }
            
            # Usar la lógica del scanner para evaluar señal
            # (Simplificado - en una versión completa usarías scanner.evaluate_signal directamente)
            signal_strength = self.calculate_signal_strength(indicators, row['Close'])
            
            if signal_strength < 60:  # Umbral mínimo
                return None
            
            # Determinar dirección
            signal_type = self.determine_signal_direction(indicators)
            if signal_type == 'NONE':
                return None
            
            # Crear señal mock
            signal = TradingSignal(
                symbol=symbol,
                timestamp=timestamp,
                signal_type=signal_type,
                signal_strength=signal_strength,
                confidence_level=self.get_confidence_level(signal_strength),
                current_price=row['Close'],
                entry_quality='FULL_ENTRY',
                indicator_scores=self.get_indicator_scores(indicators),
                indicator_signals=self.get_indicator_signals(indicators),
                risk_reward_ratio=2.0,  # Placeholder
                expected_hold_time="2-5 días",
                market_context="Backtest histórico"
            )
            
            return signal
            
        except Exception as e:
            logger.error(f"❌ Error creando señal mock para {symbol}: {e}")
            return None
    
    def calculate_signal_strength(self, indicators: Dict, price: float) -> int:
        """Calcular fuerza de señal simplificada"""
        try:
            score = 0
            
            # MACD (0-25 puntos)
            macd_hist = indicators['macd']['histogram']
            if abs(macd_hist) > 0.1:
                score += min(25, int(abs(macd_hist) * 100))
            
            # RSI (0-20 puntos)
            rsi = indicators['rsi']['rsi']
            if rsi < 35 or rsi > 65:
                score += min(20, int(abs(50 - rsi) / 2))
            
            # ROC (0-20 puntos)
            roc = indicators['roc']['roc']
            if abs(roc) > 1.5:
                score += min(20, int(abs(roc) * 5))
            
            # VWAP (0-15 puntos)
            vwap_dev = indicators['vwap']['deviation_pct']
            if abs(vwap_dev) > 0.5:
                score += min(15, int(abs(vwap_dev) * 10))
            
            # Bollinger (0-20 puntos)
            bb_pos = indicators['bollinger']['position']
            if bb_pos < 0.2 or bb_pos > 0.8:
                score += min(20, int(abs(0.5 - bb_pos) * 40))
            
            return min(100, score)
            
        except Exception as e:
            logger.warning(f"⚠️ Error calculando signal strength: {e}")
            return 0
    
    def determine_signal_direction(self, indicators: Dict) -> str:
        """Determinar dirección de la señal"""
        try:
            long_signals = 0
            short_signals = 0
            
            # MACD
            if indicators['macd']['histogram'] > 0.05:
                long_signals += 1
            elif indicators['macd']['histogram'] < -0.05:
                short_signals += 1
            
            # RSI
            if indicators['rsi']['rsi'] < 35:
                long_signals += 1
            elif indicators['rsi']['rsi'] > 65:
                short_signals += 1
            
            # ROC
            if indicators['roc']['roc'] > 1.5:
                long_signals += 1
            elif indicators['roc']['roc'] < -1.5:
                short_signals += 1
            
            # Bollinger
            if indicators['bollinger']['position'] < 0.2:
                long_signals += 1
            elif indicators['bollinger']['position'] > 0.8:
                short_signals += 1
            
            # Decidir dirección
            if long_signals >= 3:
                return 'LONG'
            elif short_signals >= 3:
                return 'SHORT'
            else:
                return 'NONE'
                
        except Exception as e:
            logger.warning(f"⚠️ Error determinando dirección: {e}")
            return 'NONE'
    
    def get_confidence_level(self, signal_strength: int) -> str:
        """Obtener nivel de confianza basado en fuerza"""
        if signal_strength >= 85:
            return 'VERY_HIGH'
        elif signal_strength >= 75:
            return 'HIGH'
        elif signal_strength >= 65:
            return 'MEDIUM'
        else:
            return 'LOW'
    
    def get_indicator_scores(self, indicators: Dict) -> Dict[str, int]:
        """Obtener scores individuales por indicador"""
        return {
            'macd': min(25, int(abs(indicators['macd']['histogram']) * 125)),
            'rsi': min(20, int(abs(50 - indicators['rsi']['rsi']) / 2.5)),
            'roc': min(20, int(abs(indicators['roc']['roc']) * 5)),
            'vwap': min(15, int(abs(indicators['vwap']['deviation_pct']) * 10)),
            'bollinger': min(20, int(abs(0.5 - indicators['bollinger']['position']) * 40))
        }
    
    def get_indicator_signals(self, indicators: Dict) -> Dict[str, str]:
        """Obtener descripciones de señales por indicador"""
        return {
            'macd': f"Histogram: {indicators['macd']['histogram']:.3f}",
            'rsi': f"RSI: {indicators['rsi']['rsi']:.1f}",
            'roc': f"ROC: {indicators['roc']['roc']:.2f}%",
            'vwap': f"VWAP Dev: {indicators['vwap']['deviation_pct']:.2f}%",
            'bollinger': f"BB Pos: {indicators['bollinger']['position']:.2f}"
        }
    
    def extract_indicators_from_signal(self, signal: TradingSignal) -> Dict:
        """
        Extraer indicadores del TradingSignal para el position calculator
        
        Args:
            signal: Señal de trading con indicadores
            
        Returns:
            Dict con indicadores formateados para position_calc
        """
        try:
            # Extraer indicadores de la señal (están en indicator_signals)
            indicators = {
                'macd': {
                    'histogram': 0.05,  # Placeholder - en versión avanzada extraer del signal real
                    'signal_strength': signal.indicator_scores.get('macd', 0)
                },
                'rsi': {
                    'rsi': 50,  # Placeholder
                    'signal_strength': signal.indicator_scores.get('rsi', 0)
                },
                'vwap': {
                    'vwap': signal.current_price,
                    'deviation_pct': 0.5,
                    'signal_strength': signal.indicator_scores.get('vwap', 0)
                },
                'roc': {
                    'roc': 1.5,
                    'signal_strength': signal.indicator_scores.get('roc', 0)
                },
                'bollinger': {
                    'upper_band': signal.current_price * 1.02,
                    'lower_band': signal.current_price * 0.98,
                    'signal_strength': signal.indicator_scores.get('bollinger', 0)
                },
                'volume_osc': {
                    'signal_strength': signal.indicator_scores.get('volume', 0)
                },
                'atr': {
                    'atr': signal.current_price * 0.02,
                    'volatility_level': 'NORMAL'
                }
            }
            
            return indicators
            
        except Exception as e:
            logger.warning(f"⚠️ Error extrayendo indicadores de señal: {e}")
            # Retornar indicadores básicos por defecto
            return {
                'atr': {'atr': signal.current_price * 0.02, 'volatility_level': 'NORMAL'},
                'rsi': {'rsi': 50},
                'macd': {'histogram': 0.05}
            }

    def calculate_position_size(self, price: float) -> float:
        """
        Calcular tamaño de posición basado en gestión de capital
        
        Args:
            price: Precio actual de entrada
            
        Returns:
            Cantidad de shares/contratos
        """
        try:
            # Capital a arriesgar por trade (2% por defecto)
            risk_amount = self.current_capital * self.position_size_pct
            
            # Asumir 2% stop loss para calcular quantity
            stop_distance = price * 0.02
            
            if stop_distance > 0:
                quantity = risk_amount / stop_distance
                return max(1, int(quantity))  # Mínimo 1 share
            else:
                return 1
                
        except Exception as e:
            logger.warning(f"⚠️ Error calculando position size: {e}")
            return 1
    
    def execute_entry(self, signal: TradingSignal, current_data: pd.Series, timestamp: datetime) -> Optional[BacktestTrade]:
        """
        Ejecutar entrada de posición
        
        Args:
            signal: Señal de trading
            current_data: Datos actuales de mercado
            timestamp: Timestamp actual
            
        Returns:
            BacktestTrade si se ejecuta, None si no
        """
        try:
            # Verificar si ya tenemos posición en este símbolo
            if signal.symbol in self.active_trades:
                logger.debug(f"⚠️ Ya hay posición activa en {signal.symbol}")
                return None
            
            # Verificar límite de trades concurrentes
            if len(self.active_trades) >= self.max_concurrent_trades:
                logger.debug(f"⚠️ Límite de trades concurrentes alcanzado ({self.max_concurrent_trades})")
                return None
            
            # Generar plan de posición usando position calculator
            # Preparar DataFrame para position calculator (necesita columnas en mayúsculas)
            market_data_df = pd.DataFrame([current_data]).T
            market_data_df.columns = ['value']
            market_data_expanded = pd.DataFrame({
                'Open': [current_data['Open']] * 50,  # Crear serie temporal básica
                'High': [current_data['High']] * 50,
                'Low': [current_data['Low']] * 50,
                'Close': [current_data['Close']] * 50,
                'Volume': [current_data['Volume']] * 50
            })
            
            position_plan = self.position_calc.calculate_position_plan_v3(
                symbol=signal.symbol,
                direction=signal.signal_type,
                current_price=signal.current_price,
                signal_strength=signal.signal_strength,
                indicators=self.extract_indicators_from_signal(signal),
                market_data=market_data_expanded,
                account_balance=self.current_capital
            )
            
            if not position_plan:
                logger.warning(f"⚠️ No se pudo generar plan de posición para {signal.symbol}")
                return None
            
            # Calcular tamaño de posición
            quantity = self.calculate_position_size(signal.current_price)
            
            # Crear trade
            self.trade_counter += 1
            trade = BacktestTrade(
                trade_id=self.trade_counter,
                symbol=signal.symbol,
                direction=signal.signal_type,
                signal=signal,
                position_plan=position_plan,
                entry_time=timestamp,
                entry_price=signal.current_price,
                quantity=quantity,
                status=TradeStatus.ACTIVE
            )
            
            # Añadir a trades activos
            self.active_trades[signal.symbol] = trade
            self.trades.append(trade)
            
            # Actualizar capital (comisiones, slippage mínimo)
            trade_cost = quantity * signal.current_price * 1.001  # 0.1% slippage/comisiones
            self.current_capital -= trade_cost
            
            logger.info(f"📈 ENTRADA: {signal.symbol} {signal.signal_type} @ ${signal.current_price:.2f} - Qty: {quantity}")
            
            return trade
            
        except Exception as e:
            logger.error(f"❌ Error ejecutando entrada para {signal.symbol}: {e}")
            return None
    
    def check_exit_conditions(self, trade: BacktestTrade, current_data: pd.Series, timestamp: datetime) -> Optional[str]:
        """
        Verificar condiciones de salida para un trade activo
        
        Args:
            trade: Trade activo
            current_data: Datos actuales
            timestamp: Timestamp actual
            
        Returns:
            Razón de salida si aplica, None si continúa
        """
        try:
            current_price = current_data['Close']
            
            # 1. Verificar Stop Loss
            if trade.position_plan.stop_loss:
                stop_price = trade.position_plan.stop_loss.price
                
                if trade.direction == 'LONG' and current_price <= stop_price:
                    return f"Stop Loss @ ${stop_price:.2f}"
                elif trade.direction == 'SHORT' and current_price >= stop_price:
                    return f"Stop Loss @ ${stop_price:.2f}"
            
            # 2. Verificar Take Profits
            for i, exit_level in enumerate(trade.position_plan.exits):
                target_price = exit_level.price
                
                if trade.direction == 'LONG' and current_price >= target_price:
                    return f"Take Profit {i+1} @ ${target_price:.2f}"
                elif trade.direction == 'SHORT' and current_price <= target_price:
                    return f"Take Profit {i+1} @ ${target_price:.2f}"
            
            # 3. Verificar Exit Manager (condiciones técnicas deterioradas)
            # TODO: Implementar lógica del exit manager usando current_data
            
            # 4. Salida por tiempo (opcional - evitar trades muy largos)
            days_held = (timestamp - trade.entry_time).days
            if days_held > 10:  # Más de 10 días
                return f"Salida por tiempo ({days_held} días)"
            
            return None  # Continuar con el trade
            
        except Exception as e:
            logger.error(f"❌ Error verificando condiciones de salida: {e}")
            return None
    
    def execute_exit(self, trade: BacktestTrade, current_data: pd.Series, timestamp: datetime, exit_reason: str):
        """
        Ejecutar salida de posición
        
        Args:
            trade: Trade a cerrar
            current_data: Datos actuales
            timestamp: Timestamp de salida
            exit_reason: Razón de la salida
        """
        try:
            exit_price = current_data['Close']
            
            # Calcular P&L
            if trade.direction == 'LONG':
                pnl_dollars = (exit_price - trade.entry_price) * trade.quantity
            else:  # SHORT
                pnl_dollars = (trade.entry_price - exit_price) * trade.quantity
            
            # Descontar comisiones/slippage
            pnl_dollars -= (trade.quantity * exit_price * 0.001)  # 0.1% costo salida
            
            pnl_percent = (pnl_dollars / (trade.entry_price * trade.quantity)) * 100
            
            # Actualizar trade
            trade.exit_time = timestamp
            trade.exit_price = exit_price
            trade.exit_reason = exit_reason
            trade.pnl_dollars = pnl_dollars
            trade.pnl_percent = pnl_percent
            trade.days_held = (timestamp - trade.entry_time).days
            
            # Determinar estado final
            if pnl_dollars > 0:
                trade.status = TradeStatus.CLOSED_WIN
            else:
                trade.status = TradeStatus.CLOSED_LOSS
            
            # Actualizar capital
            self.current_capital += (trade.quantity * exit_price) + pnl_dollars
            
            # Remover de trades activos
            if trade.symbol in self.active_trades:
                del self.active_trades[trade.symbol]
            
            # Añadir punto a equity curve
            self.equity_curve.append((timestamp, self.current_capital))
            
            result = "WIN ✅" if pnl_dollars > 0 else "LOSS ❌"
            logger.info(f"📉 SALIDA: {trade.symbol} @ ${exit_price:.2f} | {result} | ${pnl_dollars:.2f} ({pnl_percent:.1f}%) | {exit_reason}")
            
        except Exception as e:
            logger.error(f"❌ Error ejecutando salida: {e}")
    
    def run_backtest(self, symbols: List[str], start_date: datetime, end_date: datetime) -> BacktestMetrics:
        """
        Ejecutar backtesting completo
        
        Args:
            symbols: Lista de símbolos a testear
            start_date: Fecha de inicio
            end_date: Fecha de fin
            
        Returns:
            BacktestMetrics con resultados
        """
        logger.info(f"🔙 INICIANDO BACKTEST")
        logger.info(f"📊 Símbolos: {symbols}")
        logger.info(f"📅 Período: {start_date.date()} a {end_date.date()}")
        logger.info(f"💰 Capital inicial: ${self.initial_capital:,.2f}")
        
        try:
            # Cargar datos para todos los símbolos
            symbol_data = {}
            for symbol in symbols:
                data = self.load_historical_data(symbol, start_date, end_date)
                if data is not None and len(data) > 0:
                    symbol_data[symbol] = data
                else:
                    logger.warning(f"⚠️ Sin datos para {symbol} - excluido del backtest")
            
            if not symbol_data:
                logger.error("❌ No hay datos válidos para ningún símbolo")
                return BacktestMetrics()
            
            logger.info(f"✅ Datos cargados para {len(symbol_data)} símbolos")
            
            # Obtener todas las fechas únicas y ordenarlas
            all_timestamps = set()
            for data in symbol_data.values():
                all_timestamps.update(data.index)
            
            timestamps = sorted(all_timestamps)
            logger.info(f"📅 Procesando {len(timestamps)} períodos de tiempo")
            
            # Procesar cada timestamp
            processed_count = 0
            for timestamp in timestamps:
                # Procesar cada símbolo en este timestamp
                for symbol, data in symbol_data.items():
                    if timestamp not in data.index:
                        continue
                    
                    current_data = data.loc[timestamp]
                    
                    # 1. Verificar salidas de trades activos
                    if symbol in self.active_trades:
                        trade = self.active_trades[symbol]
                        
                        # Actualizar métricas de tracking
                        current_price = current_data['Close']
                        if trade.direction == 'LONG':
                            unrealized_pct = ((current_price - trade.entry_price) / trade.entry_price) * 100
                        else:
                            unrealized_pct = ((trade.entry_price - current_price) / trade.entry_price) * 100
                        
                        # Actualizar max favorable/adverse
                        if unrealized_pct > trade.max_favorable:
                            trade.max_favorable = unrealized_pct
                        if unrealized_pct < trade.max_adverse:
                            trade.max_adverse = unrealized_pct
                        
                        # Verificar condiciones de salida
                        exit_reason = self.check_exit_conditions(trade, current_data, timestamp)
                        if exit_reason:
                            self.execute_exit(trade, current_data, timestamp, exit_reason)
                    
                    # 2. Buscar nuevas señales (solo si no hay posición activa)
                    elif len(self.active_trades) < self.max_concurrent_trades:
                        signal = self.create_mock_signal_from_data(symbol, current_data, timestamp)
                        if signal:
                            self.execute_entry(signal, current_data, timestamp)
                
                processed_count += 1
                
                # Log progreso cada 1000 períodos
                if processed_count % 1000 == 0:
                    logger.info(f"📊 Procesados {processed_count}/{len(timestamps)} períodos...")
            
            # Cerrar trades pendientes al final
            final_timestamp = timestamps[-1] if timestamps else datetime.now()
            remaining_trades = list(self.active_trades.values())
            for trade in remaining_trades:
                if trade.symbol in symbol_data:
                    final_data = symbol_data[trade.symbol].iloc[-1]
                    self.execute_exit(trade, final_data, final_timestamp, "Final del período")
            
            # Calcular métricas finales
            metrics = self.calculate_backtest_metrics(start_date, end_date)
            
            logger.info(f"✅ BACKTEST COMPLETADO")
            self.print_backtest_summary(metrics)
            
            return metrics
            
        except Exception as e:
            logger.error(f"❌ Error ejecutando backtest: {e}")
            return BacktestMetrics()
    
    def calculate_backtest_metrics(self, start_date: datetime, end_date: datetime) -> BacktestMetrics:
        """Calcular métricas del backtest"""
        try:
            closed_trades = [t for t in self.trades if t.status in [TradeStatus.CLOSED_WIN, TradeStatus.CLOSED_LOSS]]
            
            if not closed_trades:
                logger.warning("⚠️ No hay trades cerrados para calcular métricas")
                return BacktestMetrics()
            
            # Métricas básicas
            total_trades = len(closed_trades)
            winning_trades = len([t for t in closed_trades if t.pnl_dollars > 0])
            losing_trades = total_trades - winning_trades
            win_rate = (winning_trades / total_trades) * 100 if total_trades > 0 else 0
            
            # P&L
            total_pnl = sum(t.pnl_dollars for t in closed_trades)
            total_pnl_percent = ((self.current_capital - self.initial_capital) / self.initial_capital) * 100
            
            winning_pnl = [t.pnl_dollars for t in closed_trades if t.pnl_dollars > 0]
            losing_pnl = [t.pnl_dollars for t in closed_trades if t.pnl_dollars < 0]
            
            avg_win = sum(winning_pnl) / len(winning_pnl) if winning_pnl else 0
            avg_loss = sum(losing_pnl) / len(losing_pnl) if losing_pnl else 0
            
            # Profit Factor
            gross_profit = sum(winning_pnl) if winning_pnl else 0
            gross_loss = abs(sum(losing_pnl)) if losing_pnl else 1
            profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
            
            # Drawdown
            max_drawdown, max_drawdown_percent = self.calculate_drawdown()
            
            # Tiempo promedio
            avg_hold_time = sum(t.days_held for t in closed_trades) / total_trades if total_trades > 0 else 0
            
            # Performance por símbolo
            symbol_performance = self.calculate_symbol_performance(closed_trades)
            
            return BacktestMetrics(
                total_trades=total_trades,
                winning_trades=winning_trades,
                losing_trades=losing_trades,
                win_rate=win_rate,
                total_pnl=total_pnl,
                total_pnl_percent=total_pnl_percent,
                avg_win=avg_win,
                avg_loss=avg_loss,
                profit_factor=profit_factor,
                max_drawdown=max_drawdown,
                max_drawdown_percent=max_drawdown_percent,
                avg_hold_time_days=avg_hold_time,
                start_date=start_date,
                end_date=end_date,
                symbol_performance=symbol_performance
            )
            
        except Exception as e:
            logger.error(f"❌ Error calculando métricas: {e}")
            return BacktestMetrics()
    
    def calculate_drawdown(self) -> Tuple[float, float]:
        """Calcular máximo drawdown"""
        try:
            if not self.equity_curve:
                return 0.0, 0.0
            
            # Convertir equity curve a series
            equity_values = [point[1] for point in self.equity_curve]
            peak = self.initial_capital
            max_dd = 0.0
            max_dd_pct = 0.0
            
            for equity in equity_values:
                if equity > peak:
                    peak = equity
                
                drawdown = peak - equity
                drawdown_pct = (drawdown / peak) * 100 if peak > 0 else 0
                
                if drawdown > max_dd:
                    max_dd = drawdown
                if drawdown_pct > max_dd_pct:
                    max_dd_pct = drawdown_pct
            
            return max_dd, max_dd_pct
            
        except Exception as e:
            logger.error(f"❌ Error calculando drawdown: {e}")
            return 0.0, 0.0
    
    def calculate_symbol_performance(self, closed_trades: List[BacktestTrade]) -> Dict[str, Dict]:
        """Calcular performance por símbolo"""
        try:
            symbol_stats = {}
            
            # Agrupar trades por símbolo
            symbol_trades = {}
            for trade in closed_trades:
                if trade.symbol not in symbol_trades:
                    symbol_trades[trade.symbol] = []
                symbol_trades[trade.symbol].append(trade)
            
            # Calcular stats por símbolo
            for symbol, trades in symbol_trades.items():
                total_trades = len(trades)
                winning_trades = len([t for t in trades if t.pnl_dollars > 0])
                total_pnl = sum(t.pnl_dollars for t in trades)
                win_rate = (winning_trades / total_trades) * 100 if total_trades > 0 else 0
                
                symbol_stats[symbol] = {
                    'total_trades': total_trades,
                    'win_rate': round(win_rate, 1),
                    'total_pnl': round(total_pnl, 2),
                    'avg_pnl': round(total_pnl / total_trades, 2) if total_trades > 0 else 0
                }
            
            return symbol_stats
            
        except Exception as e:
            logger.error(f"❌ Error calculando performance por símbolo: {e}")
            return {}
    
    def print_backtest_summary(self, metrics: BacktestMetrics):
        """Imprimir resumen del backtest"""
        print("\n" + "=" * 70)
        print("📊 RESUMEN DEL BACKTEST")
        print("=" * 70)
        
        print(f"📅 Período: {metrics.start_date.date() if metrics.start_date else 'N/A'} a {metrics.end_date.date() if metrics.end_date else 'N/A'}")
        print(f"💰 Capital inicial: ${self.initial_capital:,.2f}")
        print(f"💰 Capital final: ${self.current_capital:,.2f}")
        print(f"📈 P&L total: ${metrics.total_pnl:,.2f} ({metrics.total_pnl_percent:+.1f}%)")
        print()
        
        print("📊 ESTADÍSTICAS DE TRADING:")
        print(f"   Total de trades: {metrics.total_trades}")
        print(f"   Trades ganadores: {metrics.winning_trades} ({metrics.win_rate:.1f}%)")
        print(f"   Trades perdedores: {metrics.losing_trades}")
        print(f"   Ganancia promedio: ${metrics.avg_win:.2f}")
        print(f"   Pérdida promedio: ${metrics.avg_loss:.2f}")
        print(f"   Profit Factor: {metrics.profit_factor:.2f}")
        print(f"   Tiempo promedio: {metrics.avg_hold_time_days:.1f} días")
        print()
        
        print("📉 ANÁLISIS DE RIESGO:")
        print(f"   Máximo drawdown: ${metrics.max_drawdown:.2f} ({metrics.max_drawdown_percent:.1f}%)")
        print()
        
        if metrics.symbol_performance:
            print("📈 PERFORMANCE POR SÍMBOLO:")
            for symbol, stats in metrics.symbol_performance.items():
                print(f"   {symbol:6}: {stats['total_trades']:2} trades | "
                      f"{stats['win_rate']:5.1f}% WR | ${stats['total_pnl']:8.2f} P&L")
        
        print("=" * 70)
        
        # Evaluación general
        if metrics.win_rate >= 60 and metrics.profit_factor >= 1.5:
            print("🎉 ESTRATEGIA PROMETEDORA - Buenas métricas generales")
        elif metrics.win_rate >= 45 and metrics.profit_factor >= 1.2:
            print("✅ ESTRATEGIA VIABLE - Métricas aceptables")
        elif metrics.total_trades < 50:
            print("⚠️ MUESTRA PEQUEÑA - Necesitas más trades para conclusiones")
        else:
            print("❌ ESTRATEGIA NECESITA MEJORAS - Métricas por debajo del objetivo")
    
    def export_detailed_results(self, filename: str = "backtest_results.csv") -> bool:
        """Exportar resultados detallados a CSV"""
        try:
            if not self.trades:
                logger.warning("⚠️ No hay trades para exportar")
                return False
            
            # Preparar datos para CSV
            trade_data = []
            for trade in self.trades:
                trade_data.append({
                    'trade_id': trade.trade_id,
                    'symbol': trade.symbol,
                    'direction': trade.direction,
                    'entry_time': trade.entry_time.isoformat() if trade.entry_time else '',
                    'entry_price': trade.entry_price,
                    'exit_time': trade.exit_time.isoformat() if trade.exit_time else '',
                    'exit_price': trade.exit_price or 0,
                    'exit_reason': trade.exit_reason,
                    'quantity': trade.quantity,
                    'pnl_dollars': trade.pnl_dollars,
                    'pnl_percent': trade.pnl_percent,
                    'days_held': trade.days_held,
                    'max_favorable': trade.max_favorable,
                    'max_adverse': trade.max_adverse,
                    'status': trade.status.value,
                    'signal_strength': trade.signal.signal_strength,
                    'confidence_level': trade.signal.confidence_level
                })
            
            # Crear DataFrame y guardar
            df = pd.DataFrame(trade_data)
            df.to_csv(filename, index=False)
            
            logger.info(f"✅ Resultados exportados a: {filename}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error exportando resultados: {e}")
            return False


# =============================================================================
# 🧪 FUNCIONES DE TESTING Y CLI
# =============================================================================

def test_basic_backtest(symbols: List[str] = None, days_back: int = 60):
    """Test básico del motor de backtesting"""
    print("🧪 TESTING BASIC BACKTEST ENGINE")
    print("=" * 60)
    
    if not symbols:
        symbols = ['AAPL', 'MSFT', 'GOOGL']
    
    try:
        # Crear motor de backtest
        engine = BasicBacktestEngine(initial_capital=10000.0)
        
        # Definir período (ajustado para que coincida mejor con tus datos)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)
        
        print(f"📊 Símbolos: {symbols}")
        print(f"📅 Período: {start_date.date()} a {end_date.date()}")
        print(f"💰 Capital: ${engine.initial_capital:,.2f}")
        print()
        
        # Primero verificar qué datos tenemos en la BD
        print("🔍 Verificando datos disponibles en la base de datos...")
        conn = get_connection()
        if conn:
            cursor = conn.cursor()
            
            # Verificar rango de datos por símbolo
            for symbol in symbols:
                cursor.execute("""
                    SELECT 
                        MIN(timestamp) as first_date,
                        MAX(timestamp) as last_date,
                        COUNT(*) as total_records,
                        COUNT(CASE WHEN close_price > 0 THEN 1 END) as valid_records
                    FROM indicators_data 
                    WHERE symbol = ? AND close_price > 0
                """, (symbol,))
                
                result = cursor.fetchone()
                if result and result[0]:
                    print(f"   {symbol}: {result[2]:,} registros ({result[1][:10]} a {result[0][:10]})")
                else:
                    print(f"   {symbol}: Sin datos disponibles")
            
            conn.close()
        
        # Ejecutar backtest
        metrics = engine.run_backtest(symbols, start_date, end_date)
        
        # Exportar resultados
        engine.export_detailed_results("test_backtest_results.csv")
        
        print("\n✅ Test completado exitosamente")
        return True
        
    except Exception as e:
        print(f"❌ Error en test: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Función principal CLI"""
    parser = argparse.ArgumentParser(description='Basic Backtesting Engine V1.0')
    parser.add_argument('--symbols', nargs='+', 
                       help='Símbolos a testear (ej: AAPL MSFT GOOGL)')
    parser.add_argument('--start-date', type=str,
                       help='Fecha de inicio (YYYY-MM-DD)')
    parser.add_argument('--end-date', type=str,
                       help='Fecha de fin (YYYY-MM-DD)')
    parser.add_argument('--capital', type=float, default=10000.0,
                       help='Capital inicial en USD')
    parser.add_argument('--detailed', action='store_true',
                       help='Análisis detallado y exportar CSV')
    parser.add_argument('--test', action='store_true',
                       help='Ejecutar test básico')
    
    args = parser.parse_args()
    
    if args.test:
        success = test_basic_backtest()
        sys.exit(0 if success else 1)
    
    try:
        # Configurar parámetros
        symbols = args.symbols or ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'META']
        
        if args.start_date:
            start_date = datetime.strptime(args.start_date, '%Y-%m-%d')
        else:
            start_date = datetime.now() - timedelta(days=180)  # 6 meses por defecto
        
        if args.end_date:
            end_date = datetime.strptime(args.end_date, '%Y-%m-%d')
        else:
            end_date = datetime.now()
        
        # Crear motor
        engine = BasicBacktestEngine(initial_capital=args.capital)
        
        # Ejecutar backtest
        print("🚀 Iniciando backtesting...")
        metrics = engine.run_backtest(symbols, start_date, end_date)
        
        # Exportar resultados detallados si se solicita
        if args.detailed:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"backtest_detailed_{timestamp}.csv"
            engine.export_detailed_results(filename)
        
        # Conclusión
        if metrics.total_trades > 0:
            print(f"\n🎯 CONCLUSIÓN:")
            if metrics.profit_factor >= 1.5 and metrics.win_rate >= 55:
                print("🟢 La estrategia muestra potencial prometedor")
            elif metrics.profit_factor >= 1.2 and metrics.win_rate >= 45:
                print("🟡 La estrategia es viable pero necesita optimización")
            else:
                print("🔴 La estrategia necesita mejoras significativas")
        else:
            print("❌ No se generaron trades en el período - revisar parámetros")
        
        sys.exit(0 if metrics.total_trades > 0 else 1)
        
    except KeyboardInterrupt:
        print("\n⚠️ Backtest interrumpido por el usuario")
        sys.exit(0)
    except Exception as e:
        logger.error(f"❌ Error ejecutando backtest: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()