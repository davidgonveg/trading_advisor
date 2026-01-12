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
    take_profits: List[TradeOrder]
    risk_amount: float
    
    def __str__(self):
        return f"TradePlan: {self.signal.symbol} {self.signal.type.value} Size={self.total_size} SL={self.stop_loss_price}"

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
        
    def create_trade_plan(self, signal: Signal, capital: float = 10000.0) -> Optional[TradePlan]:
        """
        Converts a raw Signal into an executable Trade Plan.
        """
        # 1. Calculate ATR-based Sizing
        # We need ATR at time of signal. Signal has it?
        # Signal object has `atr_value`.
        atr = signal.atr_value
        price = signal.price
        
        if atr <= 0 or price <= 0:
            logger.error(f"Invalid ATR/Price for {signal.symbol}: ATR={atr}, Price={price}")
            return None
            
        # Total Max Position Size
        total_qty = self.risk_manager.calculate_size(price, atr, capital)
        
        if total_qty < 1:
            logger.warning(f"Calculated size is 0 for {signal.symbol}. Too risky or low capital.")
            return None
            
        # 2. Entry Structure (E1, E2, E3)
        # E1: 50% at Market (Current Close)
        # E2: 30% at Entry +/- 0.5 * ATR
        # E3: 20% at Entry +/- 1.0 * ATR
        
        q1 = int(total_qty * 0.50)
        q2 = int(total_qty * 0.30)
        q3 = total_qty - q1 - q2 # Remainder
        
        direction = 1 if signal.type == SignalType.LONG else -1
        
        # Prices
        e1_price = price
        e2_price = price - (direction * self.cfg['ENTRY_2_ATR_DIST'] * atr)
        e3_price = price - (direction * self.cfg['ENTRY_3_ATR_DIST'] * atr)
        
        # Stop Loss
        sl_dist = self.cfg['SL_ATR_MULT'] * atr
        # SL is based on Average Entry? 
        # Strategy Doc: "SL = Precio entrada promedio - 2 * ATR".
        # Initially we don't know avg entry. 
        # We usually set SL relative to E1 or worst case?
        # Strategy Doc 5.3: "El stop se calcula sobre el precio promedio ponderado... Si solo se ejecutan E1 y E2..."
        # Initial SL order must be placed somewhere. Usually we place it relative to E1?
        # Or we implement dynamic SL update?
        # Let's set initial SL based on E1.
        sl_price = e1_price - (direction * sl_dist)
        
        orders = []
        orders.append(TradeOrder(signal.symbol, "MARKET", "BUY" if direction > 0 else "SELL", e1_price, q1, tag="E1"))
        orders.append(TradeOrder(signal.symbol, "LIMIT", "BUY" if direction > 0 else "SELL", e2_price, q2, tag="E2"))
        orders.append(TradeOrder(signal.symbol, "LIMIT", "BUY" if direction > 0 else "SELL", e3_price, q3, tag="E3"))
        
        # Take Profits (Based on Avg Entry expected? Use E1 for now)
        # TP1: 1.5 ATR
        # TP2: 2.5 ATR
        # TP3: 4.0 ATR
        
        tp1_price = e1_price + (direction * self.cfg['TP1_ATR_MULT'] * atr)
        tp2_price = e1_price + (direction * self.cfg['TP2_ATR_MULT'] * atr)
        tp3_price = e1_price + (direction * self.cfg['TP3_ATR_MULT'] * atr)
        
        tps = []
        # Quantity distribution for TPs
        # TP1 50%, TP2 30%, TP3 20% OF THE EXECUTED SIZE.
        # This is dynamic.
        # But we can plan the levels.
        tps.append(TradeOrder(signal.symbol, "LIMIT", "SELL" if direction > 0 else "BUY", tp1_price, 0, tag="TP1")) # Qty unknown
        tps.append(TradeOrder(signal.symbol, "LIMIT", "SELL" if direction > 0 else "BUY", tp2_price, 0, tag="TP2"))
        tps.append(TradeOrder(signal.symbol, "LIMIT", "SELL" if direction > 0 else "BUY", tp3_price, 0, tag="TP3"))
        
        plan = TradePlan(
            signal=signal,
            total_size=total_qty,
            entry_orders=orders,
            stop_loss_price=sl_price,
            take_profits=tps,
            risk_amount= (total_qty * abs(price - sl_price)) # Approx risk
        )
        
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
