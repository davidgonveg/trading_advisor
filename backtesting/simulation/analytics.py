from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime

@dataclass
class RoundTrip:
    """
    Represents a completed "Round Trip" trade (Entry -> Exit).
    Aggregates multiple fills (E1, E2, TP1...) into a single record.
    """
    id: str
    symbol: str
    direction: str # LONG / SHORT
    
    # Timing
    entry_time: datetime
    exit_time: datetime = None
    duration_hours: float = 0.0
    
    # Execution Details
    max_quantity: int = 0
    avg_entry_price: float = 0.0
    avg_exit_price: float = 0.0
    
    # Financials
    gross_pnl: float = 0.0
    commission: float = 0.0
    net_pnl: float = 0.0
    return_pct: float = 0.0 # On invested capital
    
    # Strategy Context
    exit_reason: str = "OPEN" # TP1, TP2, SL, TIME, MANUAL
    tags: List[str] = field(default_factory=list) # E1, E2, TP1...
    
    # Snapshot Data (captured at first entry)
    atr_at_entry: float = 0.0
    adx_at_entry: float = 0.0
    initial_sl: float = 0.0
    tp1_target: float = 0.0
    tp2_target: float = 0.0
    
    # Snapshots (Full Indicator Data)
    entry_snapshot: Dict[str, Any] = field(default_factory=dict)
    exit_snapshot: Dict[str, Any] = field(default_factory=dict)
    
    def close(self, exit_time: datetime):
        self.exit_time = exit_time
        if self.entry_time:
            self.duration_hours = (self.exit_time - self.entry_time).total_seconds() / 3600.0
            
    def to_dict(self):
        base_dict = {
            "id": self.id,
            "symbol": self.symbol,
            "direction": self.direction,
            "entry_time": self.entry_time,
            "exit_time": self.exit_time,
            "duration_h": round(self.duration_hours, 2),
            "qty": self.max_quantity,
            "entry_avg": round(self.avg_entry_price, 2),
            "exit_avg": round(self.avg_exit_price, 2),
            "gross_pnl": round(self.gross_pnl, 2),
            "commission": round(self.commission, 2),
            "pnl_net": round(self.net_pnl, 2),
            "pnl_pct": round(self.return_pct, 2),
            "exit_reason": self.exit_reason,
            "tags": "|".join(self.tags),
            "atr": round(self.atr_at_entry, 2),
            "adx": round(self.adx_at_entry, 1),
            "sl_price": round(self.initial_sl, 2),
            "tp1_price": round(self.tp1_target, 2),
            "tp2_price": round(self.tp2_target, 2)
        }
        
        # Flatten Entry Snapshot
        for k, v in self.entry_snapshot.items():
            base_dict[f"entry_{k}"] = v
            
        # Flatten Exit Snapshot
        for k, v in self.exit_snapshot.items():
            base_dict[f"exit_{k}"] = v
            
        return base_dict
