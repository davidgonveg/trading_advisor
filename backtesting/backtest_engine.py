#!/usr/bin/env python3
"""
🔙 BACKTEST ENGINE - Motor Principal de Backtesting
=================================================

Motor que coordina todos los componentes y ejecuta el backtesting
con comportamiento IDÉNTICO al sistema real.

Flujo:
1. Validar datos históricos
2. Cargar datos ordenados por timestamp
3. Procesar barra por barra (time-forward, sin look-ahead bias)
4. Generar señales con SignalReplicator
5. Calcular posiciones con PositionReplicator
6. Gestionar entradas/salidas escalonadas con TradeManager
7. Evaluar TPs/SL en cada barra
8. Evaluar exit manager si está activo
9. Trackear capital y equity curve
10. Generar métricas finales
"""

import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import sys
from pathlib import Path

# Añadir path del proyecto
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backtesting.config import BacktestConfig
from backtesting.data_validator import DataValidator, ValidationReport
from backtesting.signal_replicator import SignalReplicator
from backtesting.position_replicator import PositionReplicator
from backtesting.exit_replicator import ExitReplicator
from backtesting.trade_manager import TradeManager, Trade, TradeStatus, ExitReason
from database.connection import get_connection

logger = logging.getLogger(__name__)


class BacktestEngine:
    """Motor principal de backtesting"""

    def __init__(self, config: Optional[BacktestConfig] = None):
        """
        Inicializar motor de backtesting.

        Args:
            config: Configuración del backtesting
        """
        self.config = config or BacktestConfig()

        # Componentes
        self.data_validator = DataValidator()
        self.signal_replicator = SignalReplicator()
        self.position_replicator = PositionReplicator(
            capital=self.config.initial_capital,
            risk_per_trade=self.config.risk_per_trade
        )
        self.exit_replicator = ExitReplicator()
        self.trade_manager = TradeManager(
            commission_per_share=self.config.commission_per_share
        )

        # Capital tracking
        self.initial_capital = self.config.initial_capital
        self.current_capital = self.config.initial_capital
        self.peak_capital = self.config.initial_capital

        # Equity curve
        self.equity_curve = []  # Lista de (timestamp, equity)

        # Métricas
        self.metrics = {}

        # Datos históricos cargados
        self.historical_data: Dict[str, pd.DataFrame] = {}

        # Validation reports
        self.validation_reports: Dict[str, ValidationReport] = {}

        logger.info("🔙 BacktestEngine inicializado")
        logger.info(f"   Capital inicial: ${self.initial_capital:,.2f}")
        logger.info(f"   Símbolos: {len(self.config.symbols)}")
        logger.info(f"   Riesgo por trade: {self.config.risk_per_trade}%")

    def run(self) -> Dict:
        """
        Ejecutar backtesting completo.

        Returns:
            Diccionario con resultados y métricas
        """
        try:
            logger.info("=" * 70)
            logger.info("🚀 INICIANDO BACKTESTING")
            logger.info("=" * 70)

            # 1. Validar datos
            if self.config.validate_data_before_backtest:
                logger.info("\n📋 FASE 1: Validando datos históricos...")
                if not self._validate_all_data():
                    logger.error("❌ Validación de datos falló")
                    return {'error': 'Data validation failed'}

            # 2. Cargar datos
            logger.info("\n📊 FASE 2: Cargando datos históricos...")
            if not self._load_all_data():
                logger.error("❌ Error cargando datos")
                return {'error': 'Data loading failed'}

            # 3. Ejecutar backtesting
            logger.info("\n🔄 FASE 3: Ejecutando backtesting...")
            self._run_backtest()

            # 4. Cerrar posiciones abiertas al final
            logger.info("\n🏁 FASE 4: Cerrando posiciones abiertas...")
            self._close_remaining_positions()

            # 5. Calcular métricas
            logger.info("\n📊 FASE 5: Calculando métricas...")
            self._calculate_metrics()

            # 6. Generar resultados
            results = self._generate_results()

            logger.info("\n" + "=" * 70)
            logger.info("✅ BACKTESTING COMPLETADO")
            logger.info("=" * 70)

            self._print_summary()

            return results

        except Exception as e:
            logger.error(f"❌ Error en backtesting: {e}", exc_info=True)
            return {'error': str(e)}

    def _validate_all_data(self) -> bool:
        """Validar datos de todos los símbolos"""
        try:
            valid_symbols = []

            for symbol in self.config.symbols:
                logger.info(f"   Validando {symbol}...")
                report = self.data_validator.validate_symbol(
                    symbol,
                    self.config.start_date,
                    self.config.end_date
                )
                self.validation_reports[symbol] = report

                if report.overall_score >= self.config.min_data_quality_score:
                    valid_symbols.append(symbol)
                    logger.info(f"     ✅ Score: {report.overall_score:.1f}/100")
                else:
                    logger.warning(f"     ⚠️  Score bajo: {report.overall_score:.1f}/100")
                    if self.config.skip_invalid_symbols:
                        logger.warning(f"     ⏭️  Saltando {symbol}")
                    else:
                        logger.error(f"     ❌ {symbol} no apto para backtesting")
                        return False

            if not valid_symbols:
                logger.error("❌ Ningún símbolo válido para backtesting")
                return False

            # Actualizar lista de símbolos si se saltaron algunos
            if len(valid_symbols) < len(self.config.symbols):
                logger.info(f"   Símbolos válidos: {len(valid_symbols)}/{len(self.config.symbols)}")
                self.config.symbols = valid_symbols

            return True

        except Exception as e:
            logger.error(f"❌ Error validando datos: {e}")
            return False

    def _load_all_data(self) -> bool:
        """Cargar datos históricos de todos los símbolos"""
        try:
            conn = get_connection()
            if not conn:
                return False

            for symbol in self.config.symbols:
                logger.info(f"   Cargando {symbol}...")

                query = """
                SELECT * FROM indicators_data
                WHERE symbol = ?
                """

                params = [symbol]

                if self.config.start_date:
                    query += " AND timestamp >= ?"
                    params.append(self.config.start_date.isoformat())

                if self.config.end_date:
                    query += " AND timestamp <= ?"
                    params.append(self.config.end_date.isoformat())

                query += " ORDER BY timestamp ASC"

                df = pd.read_sql_query(query, conn, params=params)

                if df.empty:
                    logger.warning(f"     ⚠️  Sin datos para {symbol}")
                    continue

                # Convertir timestamp
                df['timestamp'] = pd.to_datetime(df['timestamp'])

                # Guardar
                self.historical_data[symbol] = df

                logger.info(f"     ✅ {len(df):,} filas cargadas")

            conn.close()

            if not self.historical_data:
                logger.error("❌ No se cargaron datos")
                return False

            return True

        except Exception as e:
            logger.error(f"❌ Error cargando datos: {e}")
            return False

    def _run_backtest(self):
        """
        Ejecutar backtesting principal.

        Procesa todas las barras de todos los símbolos de forma cronológica.
        """
        try:
            # Combinar todos los dataframes con columna de símbolo
            all_data = []
            for symbol, df in self.historical_data.items():
                df_copy = df.copy()
                df_copy['symbol'] = symbol
                all_data.append(df_copy)

            # Concatenar y ordenar por timestamp
            combined_df = pd.concat(all_data, ignore_index=True)
            combined_df = combined_df.sort_values('timestamp').reset_index(drop=True)

            total_bars = len(combined_df)
            logger.info(f"   Procesando {total_bars:,} barras...")

            last_timestamp = None
            bars_processed = 0

            # Procesar barra por barra
            for idx in range(len(combined_df)):
                current_row = combined_df.iloc[idx]
                symbol = current_row['symbol']
                timestamp = current_row['timestamp']

                # Progress logging
                if idx % 1000 == 0 or timestamp != last_timestamp:
                    progress = (idx / total_bars) * 100
                    logger.info(f"     [{progress:.1f}%] {timestamp} - Capital: ${self.current_capital:,.2f}")

                last_timestamp = timestamp

                # Obtener índice dentro del dataframe del símbolo
                symbol_df = self.historical_data[symbol]
                symbol_idx = symbol_df[symbol_df['timestamp'] == timestamp].index[0]

                # 1. Evaluar señales (solo si no hay posición activa en este símbolo)
                if not self.trade_manager.has_active_trade(symbol):
                    self._evaluate_signals(symbol, current_row, symbol_df, symbol_idx, timestamp)

                # 2. Evaluar trades activos (entradas, exits, stops)
                self._evaluate_active_trades(current_row, timestamp)

                # 3. Actualizar equity curve
                self._update_equity(timestamp)

                bars_processed += 1

            logger.info(f"   ✅ {bars_processed:,} barras procesadas")

        except Exception as e:
            logger.error(f"❌ Error en backtesting: {e}", exc_info=True)

    def _evaluate_signals(
        self,
        symbol: str,
        current_row: pd.Series,
        symbol_df: pd.DataFrame,
        symbol_idx: int,
        timestamp: datetime
    ):
        """Evaluar y crear nuevas señales/trades"""
        try:
            # Verificar límite de posiciones concurrentes
            active_count = len(self.trade_manager.get_active_trades())
            if active_count >= self.config.max_concurrent_positions:
                return

            # Generar señal
            signal = self.signal_replicator.generate_signal_from_historical_data(
                symbol=symbol,
                current_row=current_row,
                historical_df=symbol_df,
                current_index=symbol_idx
            )

            if not signal:
                return

            # Verificar fuerza mínima
            if signal.signal_strength < self.config.min_signal_strength:
                return

            # Verificar calidad de entrada
            min_quality = self.config.min_entry_quality
            quality_order = ["NO_TRADE", "PARTIAL_ENTRY", "FULL_ENTRY"]
            if quality_order.index(signal.entry_quality) < quality_order.index(min_quality):
                return

            # Calcular posición
            position_plan = self.position_replicator.calculate_position(
                signal=signal,
                available_capital=self.current_capital
            )

            if not position_plan:
                return

            # Crear trade
            trade = self.trade_manager.create_trade(signal, position_plan)

            # Ejecutar primera entrada inmediatamente
            price = current_row['close_price']
            slippage = self._calculate_slippage(current_row)
            execution_price = price + slippage if signal.signal_type == "LONG" else price - slippage

            self.trade_manager.execute_entry(
                trade=trade,
                entry_level=1,
                price=execution_price,
                timestamp=timestamp,
                slippage=slippage
            )

            logger.debug(
                f"🎯 Nueva señal: {symbol} {signal.signal_type} ({signal.signal_strength} pts) @ ${execution_price:.2f}"
            )

        except Exception as e:
            logger.error(f"❌ Error evaluando señal de {symbol}: {e}")

    def _evaluate_active_trades(self, current_row: pd.Series, timestamp: datetime):
        """Evaluar todos los trades activos"""
        try:
            symbol = current_row['symbol']
            trade = self.trade_manager.get_trade_by_symbol(symbol)

            if not trade:
                return

            current_price = current_row['close_price']
            high_price = current_row['high_price']
            low_price = current_row['low_price']

            # Actualizar P&L y excursiones
            trade.update_unrealized_pnl(current_price)
            trade.update_excursions(current_price)
            trade.bars_held += 1

            # 1. Evaluar entradas pendientes
            self._evaluate_pending_entries(trade, current_row, timestamp)

            # 2. Evaluar stop loss (prioritario)
            if self._check_stop_loss(trade, low_price if trade.direction == "LONG" else high_price, timestamp):
                return  # Trade cerrado

            # 3. Evaluar exit manager (si está activo)
            if self.config.enable_exit_manager:
                if self._check_exit_manager(trade, current_row, timestamp):
                    return  # Trade cerrado

            # 4. Evaluar take profits
            self._evaluate_take_profits(trade, high_price if trade.direction == "LONG" else low_price, timestamp)

        except Exception as e:
            logger.error(f"❌ Error evaluando trade activo: {e}")

    def _evaluate_pending_entries(self, trade: Trade, current_row: pd.Series, timestamp: datetime):
        """Evaluar y ejecutar entradas pendientes"""
        try:
            current_price = current_row['close_price']
            low_price = current_row['low_price']

            # Entry 2
            if not trade.entry_2_executed and trade.entry_1_executed:
                target_price = trade.position_plan.entry_2_price
                if trade.direction == "LONG" and low_price <= target_price:
                    slippage = self._calculate_slippage(current_row)
                    execution_price = target_price + slippage
                    self.trade_manager.execute_entry(trade, 2, execution_price, timestamp, slippage)

                elif trade.direction == "SHORT" and current_row['high_price'] >= target_price:
                    slippage = self._calculate_slippage(current_row)
                    execution_price = target_price - slippage
                    self.trade_manager.execute_entry(trade, 2, execution_price, timestamp, slippage)

            # Entry 3
            if not trade.entry_3_executed and trade.entry_2_executed:
                target_price = trade.position_plan.entry_3_price
                if trade.direction == "LONG" and low_price <= target_price:
                    slippage = self._calculate_slippage(current_row)
                    execution_price = target_price + slippage
                    self.trade_manager.execute_entry(trade, 3, execution_price, timestamp, slippage)

                elif trade.direction == "SHORT" and current_row['high_price'] >= target_price:
                    slippage = self._calculate_slippage(current_row)
                    execution_price = target_price - slippage
                    self.trade_manager.execute_entry(trade, 3, execution_price, timestamp, slippage)

        except Exception as e:
            logger.error(f"❌ Error evaluando entradas pendientes: {e}")

    def _check_stop_loss(self, trade: Trade, extreme_price: float, timestamp: datetime) -> bool:
        """Verificar si se hit stop loss"""
        try:
            if trade.stop_loss_hit:
                return False

            sl_price = trade.position_plan.stop_loss

            # Para LONG: stop loss se hit si price cae por debajo
            # Para SHORT: stop loss se hit si price sube por encima
            hit_sl = False
            if trade.direction == "LONG" and extreme_price <= sl_price:
                hit_sl = True
            elif trade.direction == "SHORT" and extreme_price >= sl_price:
                hit_sl = True

            if hit_sl:
                slippage = self._calculate_slippage_from_price(sl_price)
                execution_price = sl_price - slippage if trade.direction == "LONG" else sl_price + slippage

                success, pnl = self.trade_manager.execute_exit(
                    trade=trade,
                    exit_type="SL",
                    price=execution_price,
                    timestamp=timestamp,
                    reason=ExitReason.STOP_LOSS,
                    slippage=slippage
                )

                if success:
                    # Actualizar capital
                    self.current_capital += pnl
                    logger.debug(f"🛑 Stop Loss hit: {trade.symbol} @ ${execution_price:.2f} P&L=${pnl:.2f}")
                    return True

            return False

        except Exception as e:
            logger.error(f"❌ Error checking stop loss: {e}")
            return False

    def _check_exit_manager(self, trade: Trade, current_row: pd.Series, timestamp: datetime) -> bool:
        """Verificar condiciones de exit manager"""
        try:
            current_price = current_row['close_price']

            should_exit, urgency, score, reason = self.exit_replicator.evaluate_exit_conditions(
                original_signal=trade.signal,
                current_row=current_row,
                entry_price=trade.avg_entry_price,
                current_price=current_price,
                bars_held=trade.bars_held
            )

            if should_exit:
                trade.exit_manager_urgency = urgency
                trade.exit_manager_score = score
                trade.exit_manager_reason = reason

                slippage = self._calculate_slippage(current_row)
                execution_price = current_price - slippage if trade.direction == "LONG" else current_price + slippage

                success, pnl = self.trade_manager.execute_exit(
                    trade=trade,
                    exit_type="EXIT_MANAGER",
                    price=execution_price,
                    timestamp=timestamp,
                    reason=ExitReason.EXIT_MANAGER,
                    slippage=slippage
                )

                if success:
                    self.current_capital += pnl
                    logger.debug(
                        f"🚨 Exit Manager: {trade.symbol} @ ${execution_price:.2f} "
                        f"P&L=${pnl:.2f} ({urgency.value})"
                    )
                    return True

            return False

        except Exception as e:
            logger.error(f"❌ Error checking exit manager: {e}")
            return False

    def _evaluate_take_profits(self, trade: Trade, extreme_price: float, timestamp: datetime):
        """Evaluar take profits"""
        try:
            # TP1
            if not trade.tp1_executed and extreme_price >= trade.position_plan.take_profit_1 if trade.direction == "LONG" else extreme_price <= trade.position_plan.take_profit_1:
                tp_price = trade.position_plan.take_profit_1
                slippage = self._calculate_slippage_from_price(tp_price)
                execution_price = tp_price - slippage if trade.direction == "LONG" else tp_price + slippage

                success, pnl = self.trade_manager.execute_exit(
                    trade, "TP1", execution_price, timestamp, ExitReason.TAKE_PROFIT_1, slippage
                )
                if success:
                    self.current_capital += pnl
                    logger.debug(f"✅ TP1: {trade.symbol} @ ${execution_price:.2f} P&L=${pnl:.2f}")

            # TP2
            elif not trade.tp2_executed and trade.tp1_executed and (extreme_price >= trade.position_plan.take_profit_2 if trade.direction == "LONG" else extreme_price <= trade.position_plan.take_profit_2):
                tp_price = trade.position_plan.take_profit_2
                slippage = self._calculate_slippage_from_price(tp_price)
                execution_price = tp_price - slippage if trade.direction == "LONG" else tp_price + slippage

                success, pnl = self.trade_manager.execute_exit(
                    trade, "TP2", execution_price, timestamp, ExitReason.TAKE_PROFIT_2, slippage
                )
                if success:
                    self.current_capital += pnl
                    logger.debug(f"✅ TP2: {trade.symbol} @ ${execution_price:.2f} P&L=${pnl:.2f}")

            # TP3
            elif not trade.tp3_executed and trade.tp2_executed and (extreme_price >= trade.position_plan.take_profit_3 if trade.direction == "LONG" else extreme_price <= trade.position_plan.take_profit_3):
                tp_price = trade.position_plan.take_profit_3
                slippage = self._calculate_slippage_from_price(tp_price)
                execution_price = tp_price - slippage if trade.direction == "LONG" else tp_price + slippage

                success, pnl = self.trade_manager.execute_exit(
                    trade, "TP3", execution_price, timestamp, ExitReason.TAKE_PROFIT_3, slippage
                )
                if success:
                    self.current_capital += pnl
                    logger.debug(f"✅ TP3: {trade.symbol} @ ${execution_price:.2f} P&L=${pnl:.2f}")

            # TP4
            elif not trade.tp4_executed and trade.tp3_executed and (extreme_price >= trade.position_plan.take_profit_4 if trade.direction == "LONG" else extreme_price <= trade.position_plan.take_profit_4):
                tp_price = trade.position_plan.take_profit_4
                slippage = self._calculate_slippage_from_price(tp_price)
                execution_price = tp_price - slippage if trade.direction == "LONG" else tp_price + slippage

                success, pnl = self.trade_manager.execute_exit(
                    trade, "TP4", execution_price, timestamp, ExitReason.TAKE_PROFIT_4, slippage
                )
                if success:
                    self.current_capital += pnl
                    logger.debug(f"✅ TP4: {trade.symbol} @ ${execution_price:.2f} P&L=${pnl:.2f}")

        except Exception as e:
            logger.error(f"❌ Error evaluando TPs: {e}")

    def _calculate_slippage(self, row: pd.Series) -> float:
        """Calcular slippage realista basado en ATR"""
        try:
            price = row['close_price']
            atr_pct = row.get('atr_percentage', 2.0)
            base_slippage = price * (self.config.base_slippage_pct / 100)
            volatility_multiplier = 1.0 + (atr_pct / 10.0)
            slippage = base_slippage * volatility_multiplier
            max_slippage = price * (self.config.max_slippage_pct / 100)
            return min(slippage, max_slippage)
        except:
            return row['close_price'] * 0.001

    def _calculate_slippage_from_price(self, price: float) -> float:
        """Calcular slippage desde un precio (fallback)"""
        return price * (self.config.base_slippage_pct / 100)

    def _update_equity(self, timestamp: datetime):
        """Actualizar equity curve"""
        try:
            # Calcular equity total = capital + unrealized P&L de posiciones activas
            unrealized_pnl = sum(t.unrealized_pnl for t in self.trade_manager.get_active_trades())
            total_equity = self.current_capital + unrealized_pnl

            self.equity_curve.append((timestamp, total_equity))

            # Actualizar peak para drawdown
            if total_equity > self.peak_capital:
                self.peak_capital = total_equity

        except Exception as e:
            logger.error(f"❌ Error updating equity: {e}")

    def _close_remaining_positions(self):
        """Cerrar posiciones abiertas al final del backtest"""
        try:
            active_trades = self.trade_manager.get_active_trades()

            if not active_trades:
                return

            logger.info(f"   Cerrando {len(active_trades)} posiciones abiertas...")

            for trade in active_trades:
                # Obtener último precio conocido
                symbol_df = self.historical_data[trade.symbol]
                last_row = symbol_df.iloc[-1]
                last_price = last_row['close_price']
                last_timestamp = last_row['timestamp']

                # Cerrar posición
                slippage = self._calculate_slippage(last_row)
                execution_price = last_price - slippage if trade.direction == "LONG" else last_price + slippage

                success, pnl = self.trade_manager.execute_exit(
                    trade=trade,
                    exit_type="TP4",  # Cerrar todo como TP4
                    price=execution_price,
                    timestamp=last_timestamp,
                    reason=ExitReason.END_OF_BACKTEST,
                    slippage=slippage
                )

                if success:
                    self.current_capital += pnl
                    logger.debug(f"   Cerrado: {trade.symbol} @ ${execution_price:.2f} P&L=${pnl:.2f}")

        except Exception as e:
            logger.error(f"❌ Error cerrando posiciones: {e}")

    def _calculate_metrics(self):
        """Calcular métricas finales del backtesting"""
        try:
            closed_trades = self.trade_manager.get_closed_trades()

            if not closed_trades:
                logger.warning("⚠️  No hay trades cerrados para calcular métricas")
                self.metrics = {'error': 'No closed trades'}
                return

            # Trades ganadores y perdedores
            winning_trades = [t for t in closed_trades if t.total_pnl > 0]
            losing_trades = [t for t in closed_trades if t.total_pnl <= 0]

            total_trades = len(closed_trades)
            wins = len(winning_trades)
            losses = len(losing_trades)

            # Win rate
            win_rate = (wins / total_trades * 100) if total_trades > 0 else 0

            # P&L
            total_profit = sum(t.total_pnl for t in winning_trades)
            total_loss = abs(sum(t.total_pnl for t in losing_trades))

            # Profit factor
            profit_factor = (total_profit / total_loss) if total_loss > 0 else 0

            # Average win/loss
            avg_win = (total_profit / wins) if wins > 0 else 0
            avg_loss = (total_loss / losses) if losses > 0 else 0

            # Return
            net_pnl = self.current_capital - self.initial_capital
            return_pct = (net_pnl / self.initial_capital) * 100

            # Drawdown
            max_drawdown, max_dd_date = self._calculate_max_drawdown()

            # Sharpe ratio (simplificado)
            sharpe = self._calculate_sharpe_ratio()

            # Total comisiones
            total_commissions = sum(t.total_commissions for t in closed_trades)

            self.metrics = {
                'initial_capital': self.initial_capital,
                'final_capital': self.current_capital,
                'net_pnl': net_pnl,
                'return_pct': return_pct,
                'total_trades': total_trades,
                'winning_trades': wins,
                'losing_trades': losses,
                'win_rate': win_rate,
                'profit_factor': profit_factor,
                'total_profit': total_profit,
                'total_loss': total_loss,
                'avg_win': avg_win,
                'avg_loss': avg_loss,
                'largest_win': max(t.total_pnl for t in winning_trades) if winning_trades else 0,
                'largest_loss': min(t.total_pnl for t in closed_trades) if closed_trades else 0,
                'max_drawdown_pct': max_drawdown,
                'max_drawdown_date': max_dd_date,
                'sharpe_ratio': sharpe,
                'total_commissions': total_commissions,
                'avg_bars_held': np.mean([t.bars_held for t in closed_trades]),
            }

        except Exception as e:
            logger.error(f"❌ Error calculando métricas: {e}")
            self.metrics = {'error': str(e)}

    def _calculate_max_drawdown(self) -> Tuple[float, Optional[datetime]]:
        """Calcular máximo drawdown"""
        try:
            if not self.equity_curve:
                return 0.0, None

            peak = self.equity_curve[0][1]
            max_dd = 0.0
            max_dd_date = None

            for timestamp, equity in self.equity_curve:
                if equity > peak:
                    peak = equity
                else:
                    dd = ((peak - equity) / peak) * 100
                    if dd > max_dd:
                        max_dd = dd
                        max_dd_date = timestamp

            return max_dd, max_dd_date

        except Exception as e:
            logger.error(f"❌ Error calculando drawdown: {e}")
            return 0.0, None

    def _calculate_sharpe_ratio(self) -> float:
        """Calcular Sharpe ratio (simplificado)"""
        try:
            if len(self.equity_curve) < 2:
                return 0.0

            # Calcular retornos diarios
            equities = [e[1] for e in self.equity_curve]
            returns = np.diff(equities) / equities[:-1]

            if len(returns) == 0:
                return 0.0

            # Sharpe = (mean return - risk free rate) / std return
            mean_return = np.mean(returns)
            std_return = np.std(returns)

            if std_return == 0:
                return 0.0

            # Anualizar (aproximado)
            sharpe = (mean_return - self.config.risk_free_rate / 252) / std_return * np.sqrt(252)

            return sharpe

        except Exception as e:
            logger.error(f"❌ Error calculando Sharpe: {e}")
            return 0.0

    def _generate_results(self) -> Dict:
        """Generar diccionario de resultados completo"""
        return {
            'config': self.config.to_dict(),
            'metrics': self.metrics,
            'trades': [t.to_dict() for t in self.trade_manager.trades],
            'equity_curve': [(ts.isoformat(), eq) for ts, eq in self.equity_curve],
            'validation_reports': {
                symbol: {
                    'overall_score': report.overall_score,
                    'is_backtest_ready': report.is_backtest_ready,
                    'total_rows': report.total_rows,
                    'completeness_pct': report.completeness_pct,
                }
                for symbol, report in self.validation_reports.items()
            }
        }

    def _print_summary(self):
        """Imprimir resumen de resultados"""
        m = self.metrics

        print("\n" + "=" * 70)
        print("📊 RESUMEN DE BACKTESTING")
        print("=" * 70)
        print(f"Capital Inicial:    ${m['initial_capital']:,.2f}")
        print(f"Capital Final:      ${m['final_capital']:,.2f}")
        print(f"P&L Neto:           ${m['net_pnl']:,.2f} ({m['return_pct']:.2f}%)")
        print(f"")
        print(f"Total Trades:       {m['total_trades']}")
        print(f"Ganadores:          {m['winning_trades']} ({m['win_rate']:.1f}%)")
        print(f"Perdedores:         {m['losing_trades']}")
        print(f"")
        print(f"Profit Factor:      {m['profit_factor']:.2f}")
        print(f"Ganancia Promedio:  ${m['avg_win']:,.2f}")
        print(f"Pérdida Promedio:   ${m['avg_loss']:,.2f}")
        print(f"Mayor Ganancia:     ${m['largest_win']:,.2f}")
        print(f"Mayor Pérdida:      ${m['largest_loss']:,.2f}")
        print(f"")
        print(f"Max Drawdown:       {m['max_drawdown_pct']:.2f}%")
        print(f"Sharpe Ratio:       {m['sharpe_ratio']:.2f}")
        print(f"Total Comisiones:   ${m['total_commissions']:,.2f}")
        print(f"Barras Promedio:    {m['avg_bars_held']:.0f}")
        print("=" * 70)


if __name__ == "__main__":
    # Test del motor
    logging.basicConfig(level=logging.INFO)

    print("🔙 BACKTEST ENGINE - TEST")
    print("=" * 70)

    # Crear config de prueba
    config = BacktestConfig(
        symbols=["AAPL"],
        initial_capital=10000.0,
        risk_per_trade=1.5,
        max_concurrent_positions=3,
        min_signal_strength=65,
    )

    # Crear y ejecutar motor
    engine = BacktestEngine(config)
    results = engine.run()

    print("\n✅ Test completado")
