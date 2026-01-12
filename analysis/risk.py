import logging
from typing import Dict, Optional
from config.settings import RISK_CONFIG, STRATEGY_CONFIG

logger = logging.getLogger("core.analysis.risk")

class RiskManager:
    """
    Handles position sizing and risk calculations.
    """
    
    def __init__(self, capital: float = 10000.0):
        # Default capital if not provided dynamically
        self.default_capital = capital
        self.risk_per_trade_pct = RISK_CONFIG["RISK_PER_TRADE_PCT"] / 100.0
        
    def calculate_size(self, price: float, atr: float, capital: Optional[float] = None) -> int:
        """
        Calculate position size (number of shares/units).
        Formula: (Capital * Risk%) / (2 * ATR * Price) -- Wait, formula in doc says:
        Size = (Capital * 0.015) / (2 * ATR * Price) -> This seems wrong dimensionally.
        
        Standard Risk Formula:
        Risk Amount = Capital * Risk%
        Stop Distance = 2 * ATR
        Shares = Risk Amount / Stop Distance
        
        Doc Formula: "Tamaño Posición = (Capital × 0.015) / (2 × ATR × Precio)"
        If Price is in denominator, it calculates % of portfolio?
        Let's re-read doc example:
        Capital: 10,000
        ATR: 5
        Price: 580
        Size = (10000 * 0.015) / (2 * 5) = 150 / 10 = 15 shares.
        
        Wait, the formula in doc text: "(Capital × 0.015) / (2 × ATR × Precio)"
        But example calculation: "150 / 10 = 15". 
        The example calculation does NOT divide by Price.
        (10000 * 0.015) / (2*5) = 150 / 10 = 15.
        Cost = 15 * 580 = 8700. This is 87% of capital. 
        Risk = 15 * (2*5) = 150. This is 1.5% of 10000. Correct.
        
        So the formula TEXT having "x Price" in denominator might be a typo or I misread "Stop Distance" as "ATR * Price"?
        Actually, usually Position Size = RiskAmount / (Entry - SL).
        Here SL dist = 2 * ATR.
        So Size = (Capital * 0.015) / (2 * ATR).
        
        The doc text says: "Tamaño Posición = (Capital × 0.015) / (2 × ATR × Precio)"
        But the example IGNORES price in denominator.
        I will follow the standard financial logic which matches the EXAMPLE.
        Size = Risk_Amount / Stop_Distance
        """
        
        if capital is None:
            capital = self.default_capital
            
        if atr <= 0 or price <= 0:
            return 0
            
        risk_amount = capital * self.risk_per_trade_pct
        stop_distance = STRATEGY_CONFIG["SL_ATR_MULT"] * atr
        
        if stop_distance == 0:
            return 0
            
        size = risk_amount / stop_distance
        
        # Round down to nearest integer
        return int(size)
        
    def check_volatility_adjustment(self, current_atr: float, avg_atr: float) -> float:
        """
        Returns sizing multiplier (1.0, 0.75, 0.5) based on volatility.
        """
        if avg_atr <= 0:
            return 1.0
            
        ratio = current_atr / avg_atr
        
        if ratio > 2.0:
            return 0.5
        elif ratio > 1.5:
            return 0.75
        else:
            return 1.0
