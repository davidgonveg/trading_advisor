import logging
import pandas as pd
from datetime import datetime
from typing import Optional, Dict, List
from dataclasses import dataclass, field

from config.settings import STRATEGY_CONFIG
from analysis.signal import Signal, SignalType
from analysis.risk import RiskManager
from data.storage.database import Database

logger = logging.getLogger("core.trading.manager")

@dataclass
class TradeOrder:
    """Represents a discrete order (Entry or Exit)"""
    symbol: str
    type: str # MARKET, LIMIT, STOP
    side: str # BUY, SELL
    price: Optional[float]
    quantity: int
    status: str = "PENDING"
    tag: str = "" # E1, E2, SL, TP1

@dataclass
class TradePlan:
    """Complete plan for a trade lifecycle"""
    signal: Signal
    total_size: int
    entry_orders: List[TradeOrder]
    stop_loss_price: float
    stop_loss_order: TradeOrder  # NEW: Actual SL order
    take_profits: List[TradeOrder]
    risk_amount: float
    warnings: List[str] = field(default_factory=list)
    
    def __str__(self):
        warn_str = f" [WARNINGS: {', '.join(self.warnings)}]" if self.warnings else ""
        return f"TradePlan: {self.signal.symbol} {self.signal.type.value} Size={self.total_size} SL={self.stop_loss_price}{warn_str}"

class TradeManager:
    """
    Orchestrates Trade Lifecycle:
    1. Signal -> Plan (Sizing, Levels)
    2. Plan -> Execution (Broker API - Future)
    3. Monitor (Open Trades)
    """
    
    def __init__(self):
        self.risk_manager = RiskManager()
        self.cfg = STRATEGY_CONFIG
        self.db = Database() # For persistence of trades
        from alerts.telegram import TelegramBot
        self.telegram = TelegramBot()
        
    def create_trade_plan(self, signal: Signal, size: int) -> Optional[TradePlan]:
        """
        Converts a raw Signal into an executable Trade Plan.
        Strategy: VWAP Bounce (v3.2 - Simplified)
        - Entry: Market
        - SL: ATR * 2.0
        - TP: ATR * 4.0
        """
        price = signal.price
        if price <= 0:
            return None
            
        direction = 1 if signal.type == SignalType.LONG else -1
        atr = getattr(signal, 'atr_value', 0)
        
        # 1. Levels (ATR-based for alignment with Backtesting)
        # Use config or defaults
        SL_MULT = 2.0
        TP_MULT = 4.0
        
        # Fallback to Fixed % if ATR is missing (though scanner should provide it)
        if atr > 0:
            sl_dist = atr * SL_MULT
            tp_dist = atr * TP_MULT
        else:
            # Fallback 0.4% / 1.0%
            sl_dist = price * 0.004
            tp_dist = price * 0.010
        
        sl_price = price - (direction * sl_dist)
        tp_price = price + (direction * tp_dist)
        
        # 2. Sizing
        # Determine quantity if 'size' is Capital?
        # WARNING: 'main.py' currently passes 1000. If that's Quantity, we use it. 
        # If it's Capital, we calculate.
        # Let's assume 'size' is intended as 'Available Capital' generally, but currently hardcoded.
        # Let's calculate Quantity based on Risk Management (1.5% Risk).
        # Risk per unit = sl_dist
        # Max Risk = size * 0.015 (Assuming size is capital)
        # If size is 1000 (Capital), Risk is $15. 
        # If Price is 400, SL is 1.6. Qty = 15 / 1.6 = ~9 shares.
        # If size=1000 is Qty, then Qty=1000. Risk is 1000 * 1.6 = $1600.
        # Let's assume for now 'size' is CAPITAL.
        # Because passing fixed qty (1000 shares) for SPY ($500) = $500k exposure. Unlikely default.
        
        capital = float(size)
        risk_per_trade = 0.015
        max_risk_amount = capital * risk_per_trade
        
        # Qty = Risk / Distance
        if sl_dist == 0: return None
        total_qty = int(max_risk_amount / sl_dist)
        
        if total_qty < 1:
            logger.warning(f"Calculated size < 1 for {signal.symbol}. Capital: {capital}, Price: {price}, SL Dist: {sl_dist:.2f}")
            return None
            
        # 3. Capital Validation & Capping
        exposure = total_qty * price
        
        # If exposure exceeds capital, scale down
        if exposure > capital:
            total_qty = int(capital / price)
            exposure = total_qty * price
            logger.warning(f"EXPOSURE CAP HIT: Scaled down {signal.symbol} to {total_qty} units (${exposure:.2f})")
            
        warnings = []

        # 4. Orders
        
        # Entry (Market)
        entry_order = TradeOrder(signal.symbol, "MARKET", "BUY" if direction > 0 else "SELL", price, total_qty, tag="ENTRY")
        
        # Stop Loss
        sl_order = TradeOrder(
            signal.symbol, 
            "STOP", 
            "SELL" if direction > 0 else "BUY", 
            sl_price, 
            total_qty, 
            tag="SL"
        )
        
        # Take Profit (Single)
        tps = [
            TradeOrder(signal.symbol, "LIMIT", "SELL" if direction > 0 else "BUY", tp_price, total_qty, tag="TP")
        ]
            
        plan = TradePlan(
            signal=signal,
            total_size=total_qty,
            entry_orders=[entry_order],
            stop_loss_price=sl_price,
            stop_loss_order=sl_order,
            take_profits=tps,
            risk_amount=(total_qty * sl_dist),
            warnings=warnings
        )
        
        logger.info(f"Generated Plan for {signal.symbol}: Qty={total_qty}, Exposure=${exposure:.2f}, Risk=${plan.risk_amount:.2f}")
        return plan

    def execute_plan(self, plan: TradePlan):
        """
        Simulate execution or send to broker.
        For now: Log and Save to DB.
        """
        logger.info(f"EXECUTING PLAN: {plan}")
        # Here we would insert into 'trades' table.
        # Or print for User.
        pass
    def monitor_positions(self, data_mgr):
        """
        Main entry point for monitoring active alerts.
        """
        active_alerts = self.db.get_active_alerts()
        if not active_alerts:
            return

        logger.info(f"Monitoring {len(active_alerts)} active positions/alerts...")
        
        for alert in active_alerts:
            symbol = alert['symbol']
            try:
                # Get latest data for this symbol
                df = data_mgr.get_latest_data(symbol)
                if df.empty:
                    continue
                
                latest_price = float(df.iloc[-1]['Close'])
                latest_ts = df.index[-1]
                
                # Check exit conditions
                self.check_exit_conditions(alert, latest_price, latest_ts, df)
                
            except Exception as e:
                logger.error(f"Error monitoring {symbol}: {e}")

    def check_exit_conditions(self, alert: Dict, current_price: float, current_ts: datetime, df: pd.DataFrame):
        """
        Evaluates SL, TP, and worsening conditions.
        """
        alert_id = alert['id']
        symbol = alert['symbol']
        entry_price = alert['price']
        side = alert['signal_type'] # LONG/SHORT
        sl_price = alert['sl_price']
        tp1_price = alert['tp1_price']
        
        # Calculate R-Multiple
        # R = Distance to SL
        r_dist = abs(entry_price - sl_price)
        if r_dist == 0: r_dist = 0.01 # Safety
        
        current_pnl_r = (current_price - entry_price) / r_dist if side == 'LONG' else (entry_price - current_price) / r_dist
        
        outcome = None

        # 1. Stop Loss Hit
        if (side == 'LONG' and current_price <= sl_price) or (side == 'SHORT' and current_price >= sl_price):
            logger.warning(f"STOP LOSS HIT for {symbol} @ {current_price:.2f}")
            outcome = "SL"

        # 2. Take Profit Hit (TP1)
        elif tp1_price and ((side == 'LONG' and current_price >= tp1_price) or (side == 'SHORT' and current_price <= tp1_price)):
            logger.info(f"TAKE PROFIT HIT for {symbol} @ {current_price:.2f}")
            outcome = "TP1"

        # 3. Worsening Conditions (Early Exit)
        # Strategy specific: If Close < VWAP for LONG, or Close > VWAP for SHORT
        else:
            # A. VWAP Check
            vwap_val = df.iloc[-1].get('VWAP')
            if vwap_val:
                if (side == 'LONG' and current_price < vwap_val) or (side == 'SHORT' and current_price > vwap_val):
                    logger.info(f"EARLY EXIT for {symbol} @ {current_price:.2f} due to worsening conditions (Price vs VWAP)")
                    outcome = "EARLY_EXIT"
            
            # B. Time Stop
            if not outcome:
                alert_ts = pd.to_datetime(alert['timestamp'], utc=True)
                current_ts_dt = pd.to_datetime(current_ts, utc=True)
                duration = (current_ts_dt - alert_ts).total_seconds() / 3600
                limit = self.cfg.get('TIME_STOP_HOURS', 8)
                if duration >= limit:
                    logger.info(f"TIME STOP for {symbol} after {duration:.1f} hours (Limit: {limit}h)")
                    outcome = "TIME_STOP"

            # C. Session Close (EOD)
            if not outcome and self.is_market_closing_soon(current_ts):
                logger.info(f"SESSION CLOSE exit for {symbol}")
                outcome = "TIME_STOP"

        if outcome:
            # 1. Update DB
            self.db.update_alert_performance(alert_id, outcome, current_pnl_r, current_price, current_ts)
            
            # 2. Notify
            self.telegram.send_exit_notification(symbol, outcome, current_pnl_r, current_price)

    def generate_performance_report(self, data_mgr=None) -> str:
        """
        Generates a summary of recent alert performance.
        Includes Active positions if data_mgr is provided.
        """
        conn = self.db.get_connection()
        try:
            # 1. Closed Trades Stats
            query = """
                SELECT outcome, COUNT(*) as count, SUM(pnl_r_multiple) as total_r
                FROM alert_performance
                GROUP BY outcome
            """
            df_closed = pd.read_sql_query(query, conn)
            
            # 2. Get Active Alerts for Floating PnL
            active_alerts = self.db.get_active_alerts()
            
            report = "*INFORME DE RENDIMIENTO*\n"
            report += "━━━━━━━━━━━━━━━━━━━━━\n"
            
            if not df_closed.empty:
                total_trades = df_closed['count'].sum()
                total_r = df_closed['total_r'].sum()
                win_rate = (df_closed[df_closed['outcome'].isin(['TP1', 'TP2', 'TP3'])]['count'].sum() / total_trades) * 100 if total_trades > 0 else 0
                
                report += f"*Cerrados:* {total_trades} trades\n"
                report += f"- Beneficio Realizado: {total_r:+.2f}R\n"
                report += f"- Win Rate: {win_rate:.1f}%\n"
                
                report += "\n*Desglose:* "
                outcomes = []
                for _, row in df_closed.iterrows():
                    outcomes.append(f"{row['outcome']}: {row['count']} ({row['total_r']:+.2f}R)")
                report += ", ".join(outcomes) + "\n"
            else:
                report += "_No hay trades cerrados aún._\n"

            report += "\n━━━━━━━━━━━━━━━━━━━━━\n"
            
            # 3. Active Positions Section
            if active_alerts:
                report += f"*POSICIONES ABIERTAS:* {len(active_alerts)}\n"
                for alert in active_alerts:
                    symbol = alert['symbol']
                    entry_price = alert['price']
                    side = alert['signal_type']
                    sl_price = alert['sl_price']
                    
                    floating_pnl_r = 0
                    if data_mgr:
                        df = data_mgr.get_latest_data(symbol)
                        if not df.empty:
                            current_price = float(df.iloc[-1]['Close'])
                            r_dist = abs(entry_price - sl_price) or 0.01
                            floating_pnl_r = (current_price - entry_price) / r_dist if side == 'LONG' else (entry_price - current_price) / r_dist
                    
                    report += f"• {symbol}: {side} @ {entry_price:.2f} (PnL: {floating_pnl_r:+.2f}R)\n"
            else:
                report += "🏖️ *Sin posiciones abiertas.*\n"
            
            return report
        except Exception as e:
            logger.error(f"Error generating report: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return "Error generating performance report."
        finally:
            conn.close()
    def is_market_closing_soon(self, current_ts: datetime) -> bool:
        """
        Checks if the US market is close to ending (15:55 EST/EDT).
        """
        try:
            # Convert to NY time
            if current_ts.tzinfo is None:
                current_ts = current_ts.replace(tzinfo=pd.Timestamp.now(tz='UTC').tzinfo) # Assume UTC if naive
            
            ny_ts = pd.Timestamp(current_ts).tz_convert('America/New_York')
            
            # Market closes at 16:00. We trigger at 15:50 or later.
            # Only on weekdays
            if ny_ts.weekday() >= 5: # Weekend
                return False
                
            if ny_ts.hour == 15 and ny_ts.minute >= 50:
                return True
            if ny_ts.hour >= 16: # Already after close
                return True
                
            return False
        except Exception as e:
            logger.error(f"Error checking market close: {e}")
            return False
