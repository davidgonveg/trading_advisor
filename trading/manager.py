import logging
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
        
    def create_trade_plan(self, signal: Signal, size: int) -> Optional[TradePlan]:
        """
        Converts a raw Signal into an executable Trade Plan.
        Strategy: VWAP Bounce (v3.1)
        - Entry: Market (100%)
        - SL: 0.4% from Entry
        - TP1: 0.8% from Entry (60% Qty)
        - TP2: 1.2% from Entry (40% Qty)
        """
        price = signal.price
        if price <= 0:
            return None
            
        direction = 1 if signal.type == SignalType.LONG else -1
        
        # 1. Levels (Fixed % as per verified Strategy)
        SL_PCT = 0.004
        TP1_PCT = 0.008
        TP2_PCT = 0.012
        
        sl_dist = price * SL_PCT
        tp1_dist = price * TP1_PCT
        tp2_dist = price * TP2_PCT
        
        sl_price = price - (direction * sl_dist)
        tp1_price = price + (direction * tp1_dist)
        tp2_price = price + (direction * tp2_dist)
        
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
            
        # 3. Capital Validation (New)
        # Check if total exposure (Initial Value) exceeds allocated capital
        exposure = total_qty * price
        warnings = []
        if exposure > capital:
            msg = f"CAPITAL OVERFLOW: Exposure (${exposure:.2f}) > Capital (${capital:.2f})"
            logger.warning(f"⚠️ {msg} for {signal.symbol}")
            warnings.append(msg)

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
        
        # Take Profits (Split)
        tp1_qty = int(total_qty * 0.60)
        tp2_qty = total_qty - tp1_qty
        
        tps = []
        if tp1_qty > 0:
            tps.append(TradeOrder(signal.symbol, "LIMIT", "SELL" if direction > 0 else "BUY", tp1_price, tp1_qty, tag="TP1"))
        if tp2_qty > 0:
            tps.append(TradeOrder(signal.symbol, "LIMIT", "SELL" if direction > 0 else "BUY", tp2_price, tp2_qty, tag="TP2"))
            
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
        logger.info(f"🚀 EXECUTING PLAN: {plan}")
        # Here we would insert into 'trades' table.
        # Or print for User.
        pass
