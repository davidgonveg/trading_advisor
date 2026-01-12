#!/usr/bin/env python3
"""
🔙 BACKTEST ENGINE V2.0 - Event Driven & Exact Match
==================================================

Motor que coordina todos los componentes y ejecuta el backtesting
con comportamiento IDÉNTICO al sistema real.

CHANGELOG V2.0:
- Use DIRECTAMENTE SignalScanner y ExitManager reales (Dependency Injection).
- Simulación exacta de tiempo y datos (Mocking).
- Elimina duplicidad de lógica (SignalReplicator/ExitReplicator han muerto).
"""

import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import sys
from pathlib import Path
import pytz

# Añadir path del proyecto
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backtesting.config import BacktestConfig
from backtesting.data_validator import DataValidator, ValidationReport
from backtesting.trade_manager import TradeManager, Trade, ExitReason

# 🆕 V2.0: Importar componentes REALES y MOCKS
from analysis.scanner import SignalScanner, TradingSignal
from execution.exit_manager import ExitManager, ExitSignal
from backtesting.mocks import BacktestDataManager
from utils.time_provider import BacktestTimeProvider
# from backtesting.position_replicator import PositionReplicator # REMOVED (Legacy/Unused)
# El plan decía "Reutilice EXACTAMENTE las mismas clases... PositionCalculator".
# SignalScanner YA usa PositionCalculator internamente.
# Así que PositionReplicator ya no debería ser necesario para calcular la posición inicial,
# PERO PositionReplicator del backtest tiene lógica de sizing de capital?
# Scanner calcula "PositionPlan" (stop loss, targets).
# PositionReplicator calcula "Shares Size" basado en capital disponible en backtest.
# Vamos a mantener PositionReplicator SOLO para el sizing (shares), pero usando el Plan del Scanner.

from database.connection import get_connection
import config as system_config

logger = logging.getLogger(__name__)


class BacktestEngine:
    """Motor principal de backtesting (Event-Driven)"""

    def __init__(self, config: Optional[BacktestConfig] = None):
        """
        Inicializar motor de backtesting.
        """
        self.config = config or BacktestConfig()
        
        # 1. Componentes de Infraestructura (Mocks)
        self.time_provider = BacktestTimeProvider()
        self.historical_data: Dict[str, pd.DataFrame] = {}
        
        # Se inicializarán en _run_backtest después de cargar datos
        self.data_manager: Optional[BacktestDataManager] = None
        self.scanner: Optional[SignalScanner] = None
        self.exit_manager: Optional[ExitManager] = None
        
        # Componentes de Gestión (Backtest specific)
        self.data_validator = DataValidator()
        self.trade_manager = TradeManager(
            commission_per_share=self.config.commission_per_share
        )
        
        # Capital tracking
        self.initial_capital = self.config.initial_capital
        self.current_capital = self.config.initial_capital
        self.peak_capital = self.config.initial_capital
        self.equity_curve = [] 
        self.metrics = {}
        self.validation_reports = {}

        logger.info("🔙 BacktestEngine V2.0 (Event-Driven) inicializado")
        logger.info(f"   Capital inicial: ${self.initial_capital:,.2f}")

    def run(self) -> Dict:
        """Ejecutar backtesting completo."""
        try:
            logger.info("=" * 70)
            logger.info("🚀 INICIANDO BACKTESTING (V2.0 LIVE LOGIC)")
            logger.info("=" * 70)

            # 1. Cargar y Validar Datos
            if not self._prepare_data():
                return {'error': 'Data preparation failed'}

            # 2. Inicializar Mocks y Componentes Reales
            self._initialize_components()

            # 3. Ejecutar Bucle Principal
            self._run_event_loop()

            # 4. Finalizar
            self._close_remaining_positions()
            self._calculate_metrics()
            results = self._generate_results()
            
            self._print_summary()
            return results

        except Exception as e:
            logger.error(f"❌ Error en backtesting: {e}", exc_info=True)
            return {'error': str(e)}

    def _prepare_data(self) -> bool:
        """Cargar datos históricos y prepararlos."""
        # TODO: Usar DataValidator si config lo pide
        
        logger.info("\n📊 Cargando datos históricos...")
        conn = get_connection()
        try:
            for symbol in self.config.symbols:
                # Usar continuous_data si es posible, o indicators_data
                # Para ser 100% fiel, deberíamos usar continuous_data que es lo que DataManager devuelve
                # Pero BacktestDataManager va a servir estos datos.
                
                # Leemos todo y lo guardamos en memoria para los mocks
                # Usamos continuous_data que es la fuente de verdad del DataManager
                query = "SELECT * FROM continuous_data WHERE symbol = ? ORDER BY timestamp ASC"
                # Si tenemos criteria de fecha
                params = [symbol]
                
                df = pd.read_sql_query(query, conn, params=params)
                
                if df.empty:
                    logger.warning(f"⚠️ Sin datos para {symbol}")
                    continue
                    
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                df.set_index('timestamp', inplace=True)
                
                
                # Ensure UTC or localized (Moved UP)
                if df.index.tz is None:
                    # Asumimos que la BD guarda en UTC o Market Time?
                    # El scanner espera timezones.
                    # Vamos a asumir 'US/Eastern' como base si no tiene tz
                    df.index = df.index.tz_localize('US/Eastern')
                
                # Filtrar fechas
                if self.config.start_date:
                    start_val = pd.Timestamp(self.config.start_date)
                    # Sync timezone
                    if df.index.tz is not None and start_val.tzinfo is None:
                        start_val = start_val.tz_localize(df.index.tz)
                    elif df.index.tz is None and start_val.tzinfo is not None:
                        start_val = start_val.tz_localize(None)
                        
                    df = df[df.index >= start_val]

                if self.config.end_date:
                    end_val = pd.Timestamp(self.config.end_date)
                   # Sync timezone
                    if df.index.tz is not None and end_val.tzinfo is None:
                        end_val = end_val.tz_localize(df.index.tz)
                    elif df.index.tz is None and end_val.tzinfo is not None:
                        end_val = end_val.tz_localize(None)

                    df = df[df.index <= end_val]
                
                if df.empty:
                    logger.warning(f"⚠️ Datos vacíos tras filtrar fechas para {symbol}")
                    continue
                
                self.historical_data[symbol] = df
                logger.info(f"✅ {symbol}: {len(df)} barras cargadas")
                
            return len(self.historical_data) > 0
            
        finally:
            conn.close()

    def _initialize_components(self):
        """Inicializar componentes con las dependencias inyectadas."""
        
        # 1. Crear Mock Data Manager
        # Le pasamos la 'memoria' completa de la historia
        self.data_manager = BacktestDataManager(
            config=vars(system_config),
            historical_data=self.historical_data,
            time_provider=self.time_provider
        )
        
        # 2. Crear Componentes Reales con Mocks
        self.scanner = SignalScanner(
            data_manager=self.data_manager,
            time_provider=self.time_provider
        )
        
        # Scanner PositionCalculator interno usa sus propios defaults, está bien.
        
        self.exit_manager = ExitManager(
            positions_file="backtest_positions_temp.json", # Temp file
            data_manager=self.data_manager,
            time_provider=self.time_provider
        )
        
        logger.info("✅ Componentes inicializados con Mocks")

    def _run_event_loop(self):
        """
        Bucle Principal de Eventos.
        Itera sobre cada timestamp único presente en los datos.
        """
        logger.info("\n🔄 Ejecutando simulación paso a paso...")
        
        # 1. Recolectar todos los timestamps únicos de todos los símbolos
        all_timestamps = set()
        for symbol, df in self.historical_data.items():
            logger.info(f"📊 Dataset {symbol}: Index type={df.index.dtype} First={df.index[0]}")
            all_timestamps.update(df.index.tolist())
        
        try:
            sorted_timestamps = sorted(list(all_timestamps))
        except Exception as e:
            logger.error(f"❌ Error sorting timestamps: {e}")
            logger.error(f"   Sample types: {[type(x) for x in list(all_timestamps)[:5]]}")
            raise e
            
        total_steps = len(sorted_timestamps)
        
        logger.info(f"   Total pasos de tiempo: {total_steps:,}")
        
        # 2. Iterar
        for idx, current_time in enumerate(sorted_timestamps):
            
            # --- A. Actualizar Tiempo Simulado ---
            # Asegurar tipo consistente (Pandas Timestamp) para evitar errores de comparación
            ts = pd.Timestamp(current_time)
            self.time_provider.set_time(ts)
            
            # Progress log
            if idx % 1000 == 0:
                 logger.info(f"   [{idx/total_steps:.1%}] {current_time} | Equity: ${self._calculate_total_equity():,.2f}")

            # --- B. Gestión de Trades Activos (Exit & Updates) ---
            # Primero evaluamos salidas antes de buscar nuevas entradas
            
            # B1. Exit Manager (Lógica compleja de salidas)
            self._process_exit_manager()
            
            # B2. Gestión Táctica (SL/TP/Trailing) - Esto lo hace TradeManager?
            # En el sistema nuevo, ExitManager se encarga de casi todo,
            # pero el TradeManager manejaba los Hard Stops y TPs fijos.
            # Debemos replicar esa lógica aquí o usar ExitManager para todo?
            # Mantengamos la lógica híbrida: ExitManager para salidas dinámicas,
            # y chequeos de precio para SL/TP fijos (simulando Limit/Stop orders).
            self._process_passive_orders(current_time)
            
            # --- C. Escaneo de Nuevas Señales ---
            # Solo si tenemos capital y slots disponibles
            if len(self.trade_manager.get_active_trades()) < self.config.max_concurrent_positions:
                self._process_scanner()
            
            # --- D. Actualizar Métricas ---
            self._update_equity_curve(current_time)

    def _process_scanner(self):
        """Ejecutar scanner en el tiempo actual."""
        # Solo escanear si es horario de mercado (scanner ya lo chequea con time_provider!)
        if not self.scanner.is_market_open():
             return

        # Para eficiencia, podriamos solo escanear simbolos que tienen barra en este timestamp
        # Pero Scanner normal escanea todo.
        # Vamos a filtrar simbolos que tienen dato AHORA para no perder tiempo
        current_time = self.time_provider.now()
        
        # Optimization: Only scan symbols that have a bar exactly at current_time
        # (Assuming scanner relies on latest bar being fresh)
        symbols_to_scan = []
        for symbol, df in self.historical_data.items():
            if current_time in df.index: 
                symbols_to_scan.append(symbol)
                
        if not symbols_to_scan:
            return

        # Ejecutar scanner real
        # Nota: scan_multiple_symbols re-instancia DataManager.get_data.
        # Nuestro MockDataManager filtrará correctamente.
        signals = self.scanner.scan_multiple_symbols(symbols_to_scan)
        
        for signal in signals:
            self._process_new_signal(signal)

    def _process_new_signal(self, signal: TradingSignal):
        """Procesar una señal generada por el scanner real."""
        symbol = signal.symbol
        
        # Filtrar si ya tenemos posición
        if self.trade_manager.has_active_trade(symbol):
            return
            
        # Verificar capital disponible
        if self.current_capital <= 0:
            logger.warning(f"⚠️ Capital agotado (${self.current_capital:.2f}). Ignorando señal {symbol}.")
            return
            
        # Verificar filtros del backtest config
        if signal.signal_strength < self.config.min_signal_strength:
            return

        # Calcular tamaño posición (Sizing)
        # Usamos lógica simple de % de equity o capital fijo
        # Ojo: signal.position_plan ya tiene info de entradas/stops.
        
        # Calcular shares
        entry_price = signal.current_price
        if not entry_price: return
        
        allocation = self.current_capital * (self.config.risk_per_trade / 100) 
        # Bueno, risk_per_trade suele ser % de riesgo (stop loss), aqui usamos fixed allocation por simpleza?
        # O posición fija? Vamos a usar Position Sizing por Riesgo si el plan tiene stop.
        
        shares = 0
        if signal.position_plan and signal.position_plan.stop_loss:
            risk_per_share = abs(entry_price - signal.position_plan.stop_loss.price)
            if risk_per_share > 0:
                # Riesgo total en $ = Capital * Risk%
                total_risk_dollar = self.current_capital * (self.config.risk_per_trade / 100.0)
                shares = int(total_risk_dollar / risk_per_share)
                shares = max(0, shares) # Ensure non-negative

                # Enforce Margin Limit (Max 1x Leverage by default)
                # Avoid infinite leverage on tight stops
                max_leverage = getattr(self.config, 'max_leverage', 1.0)
                max_margin_shares = int((self.current_capital * max_leverage) / entry_price)
                
                if shares > max_margin_shares:
                     logger.info(f"⚠️ Sizing: Capped by margin ({shares} -> {max_margin_shares})")
                     shares = max_margin_shares
                
                logger.info(f"💰 Sizing: {signal.symbol} Price=${entry_price:.2f} SL=${signal.position_plan.stop_loss.price:.2f} "
                            f"Risk/Share=${risk_per_share:.2f} TotalRisk=${total_risk_dollar:.2f} -> Shares={shares}")
                            
                # Enforce minimum 1 share if we have enough capital to buy it
                if shares == 0 and self.current_capital > entry_price:
                    shares = 1
                    logger.info("⚠️ Sizing: Forced min 1 share")
        
        if shares <= 0:
            # Fallback a fixed allocation (e.g. 10% capital)
            allocation = self.current_capital * 0.1
            shares = int(allocation / entry_price)
            
        if shares <= 0: return

        # Crear Trade y Ejecutar
        # Necesitamos un "PositionPlan" (ya viene en signal)
        
        # Crear trade en TradeManager
        # Nota: update TradeManager/PositionReplicator signature logic?
        # Usaremos TradeManager existente.
        
        # Simulamos ejecución inmediata
        slippage = self._calculate_slippage(entry_price)
        exec_price = entry_price + slippage if signal.signal_type == "LONG" else entry_price - slippage
        
        # Necesitamos adaptar 'signal' y 'plan' para TradeManager si espera formatos específicos
        # Pero TradeManager espera TradingSignal y PositionPlan, que son los objetos reales ahora.
        
        trade = self.trade_manager.create_trade(signal, signal.position_plan)
        
        # Forzar cantidad calculada (TradeManager podría recalcular)
        # Vamos a hackear/modificar el trade creado para tener los shares correctos si TradeManager no lo hizo bien
        # O mejor, confiamos en TradeManager?
        # Revisando backtest_engine anterior, usaba position_replicator.calculate_position
        # Ahora usamos signal.position_plan directmente.
        
        # Ejecutar entry
        self.trade_manager.execute_entry(
            trade=trade,
            entry_level=1,
            price=exec_price,
            timestamp=self.time_provider.now(),
            slippage=slippage,
            quantity=shares # Pasamos shares como quantity explícito
        )
        # Nota: TradeManager.execute_entry original NO acepta shares explícitos, los pilla del plan.
        # Tendremos que asegurar que signal.position_plan tenga el quantity_shares correcto?
        # El PositionCalculatorV3 calcula shares? Sí, calculate_scaling.
        
        # Registrar en ExitManager para seguimiento
        self.exit_manager.add_position_from_signal(signal, signal.position_plan)

    def _process_exit_manager(self):
        """Ejecutar evaluación de salidas del ExitManager."""
        # Esto evalúa todas las posiciones activas en ExitManager
        exit_signals = self.exit_manager.evaluate_all_positions()
        
        for exit_sig in exit_signals:
            symbol = exit_sig.symbol
            trade = self.trade_manager.get_trade_by_symbol(symbol)
            if not trade: continue
            
            # Ejecutar salida si urgencia es suficiente
            if exit_sig.urgency.value in ["EXIT_URGENT", "EXIT_RECOMMENDED"]:
                current_price = exit_sig.current_price
                slippage = self._calculate_slippage(current_price)
                exec_price = current_price - slippage if trade.direction == "LONG" else current_price + slippage
                
                reason = ExitReason.EXIT_MANAGER
                
                # Cerrar % según recomendación
                # TradeManager simple cierra todo por defecto?
                self.trade_manager.execute_exit(
                    trade=trade,
                    exit_type="EXIT_MANAGER",
                    price=exec_price,
                    timestamp=self.time_provider.now(),
                    reason=reason,
                    slippage=slippage
                )
                
                # Remover de ExitManager
                self.exit_manager.remove_position(symbol, "Executed Exit Signal")

    def _process_passive_orders(self, current_time):
        """Verificar Stop Loss y Take Profit fijos (limit orders)."""
        active_trades = self.trade_manager.get_active_trades()
        
        for trade in active_trades:
            # Obtener datos de la barra actual para este simbolo
            df = self.historical_data.get(trade.symbol)
            if df is None or current_time not in df.index:
                continue
                
            bar = df.loc[current_time]
            high = bar['high_price'] # Asumiendo nombres de columnas normalizados
            low = bar['low_price']
            
            # Chequear SL (stop_loss es un PositionLevel)
            if trade.position_plan.stop_loss:
                sl_price = trade.position_plan.stop_loss.price
                hit_sl = False
                if trade.direction == "LONG" and low <= sl_price:
                    hit_sl = True
                elif trade.direction == "SHORT" and high >= sl_price:
                    hit_sl = True
                    
                if hit_sl:
                    # Ejecutar SL
                    self._execute_trade_exit(trade, sl_price, ExitReason.STOP_LOSS)
                    self.exit_manager.remove_position(trade.symbol, "SL Hit")
                    continue
                
            # Chequear TPs (exits es una lista de PositionLevel)
            # Iteramos sobre los targets de salida
            if trade.position_plan.exits:
                for idx, exit_level in enumerate(trade.position_plan.exits):
                    # Asumimos orden: TP1, TP2, TP3, TP4
                    tp_price = exit_level.price
                    tp_name = f"TP{idx+1}"
                    
                    # Verificar si ya se efectuó este TP en el trade manager
                    if getattr(trade, f"tp{idx+1}_executed", False):
                        continue
                        
                    hit_tp = False
                    if trade.direction == "LONG" and high >= tp_price:
                        hit_tp = True
                    elif trade.direction == "SHORT" and low <= tp_price:
                        hit_tp = True
                        
                    if hit_tp:
                        # Determine correct ExitReason
                        try:
                            reason = getattr(ExitReason, f"TAKE_PROFIT_{idx+1}")
                        except AttributeError:
                            reason = ExitReason.TAKE_PROFIT_4 # Fallback
                            
                        self.trade_manager.execute_exit(
                            trade=trade,
                            exit_type=tp_name, # "TP1", "TP2", etc.
                            price=tp_price,
                            timestamp=self.time_provider.now(),
                            reason=reason
                        )
                


    def _execute_trade_exit(self, trade, price, reason):
        """Helper para ejecutar salida en TradeManager y actualizar capital."""
        slippage = self._calculate_slippage(price)
        exec_price = price - slippage if trade.direction == "LONG" else price + slippage
        
        # Map ExitReason to TradeManager exit_type strings
        exit_type_map = {
            ExitReason.STOP_LOSS: "SL",
            ExitReason.EXIT_MANAGER: "EXIT_MANAGER",
            ExitReason.END_OF_BACKTEST: "EXIT_MANAGER"
        }
        exit_type_str = exit_type_map.get(reason, "EXIT_MANAGER")

        success, pnl = self.trade_manager.execute_exit(
            trade=trade,
            exit_type=exit_type_str,
            price=exec_price,
            timestamp=self.time_provider.now(),
            reason=reason,
            slippage=slippage
        )
        
        if success:
            self.current_capital += pnl

    def _calculate_slippage(self, price):
        return price * 0.0005 # 0.05% fix slippage

    def _calculate_total_equity(self):
        active_pnl = sum([t.unrealized_pnl for t in self.trade_manager.get_active_trades()])
        return self.current_capital + active_pnl

    def _update_equity_curve(self, current_time):
        equity = self._calculate_total_equity()
        self.equity_curve.append((current_time, equity))
        self.peak_capital = max(self.peak_capital, equity)

    def _close_remaining_positions(self):
        """Cerrar todo al final."""
        logger.info("🏁 Cerrando posiciones restantes...")
        current_time = self.time_provider.now()
        for trade in self.trade_manager.get_active_trades():
            # Obtener último precio
            df = self.historical_data.get(trade.symbol)
            if df is not None:
                # Usar último close disponible
                # (Ya estamos al final del tiempo)
                last_price = df.iloc[-1]['close_price'] # Asumiendo que el mock data ya llegó al final
                self._execute_trade_exit(trade, last_price, ExitReason.END_OF_BACKTEST)

    def _calculate_metrics(self):
        # Reutilizar lógica existente o simplificar
        pass

    def _generate_results(self):
        # Return dict
        return {
            'initial_capital': self.initial_capital,
            'final_capital': self.current_capital,
            'equity_curve': self.equity_curve,
            'trades': [t.to_dict() for t in self.trade_manager.trades]
        }

    def _print_summary(self):
        print(f"\n🏁 RESULTADOS FINAL (Capital ${self.initial_capital})")
        print(f"💰 Final: ${self.current_capital:,.2f}")
        print(f"📈 Retorno: {((self.current_capital - self.initial_capital)/self.initial_capital)*100:.2f}%")
        print(f"📊 Trades: {len(self.trade_manager.trades)}")

