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
            "hour": self.entry_time.hour if self.entry_time else None,
            "weekday": self.entry_time.strftime('%A') if self.entry_time else None,
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

class BacktestAnalyzer:
    """
    Analyzes backtest results (RoundTrips) to provide deep insights.
    """
    def __init__(self, round_trips: List[RoundTrip]):
        self.round_trips = round_trips
        
    def get_summary(self) -> Dict[str, Any]:
        if not self.round_trips:
            return {"error": "No trades to analyze"}
            
        total_pnl = sum(t.net_pnl for t in self.round_trips)
        wins = [t for t in self.round_trips if t.net_pnl > 0]
        losses = [t for t in self.round_trips if t.net_pnl <= 0]
        
        win_rate = len(wins) / len(self.round_trips) if self.round_trips else 0
        profit_factor = sum(w.net_pnl for w in wins) / abs(sum(l.net_pnl for l in losses)) if losses and sum(l.net_pnl for l in losses) != 0 else float('inf')
        
        return {
            "total_trades": len(self.round_trips),
            "total_pnl": round(total_pnl, 2),
            "win_rate": round(win_rate * 100, 2),
            "profit_factor": round(profit_factor, 2),
            "avg_trade": round(total_pnl / len(self.round_trips), 2)
        }
        
    def analyze_by(self, field: str) -> Dict[str, Dict[str, Any]]:
        """
        Group analysis by a specific field (e.g., 'symbol', 'hour', 'weekday').
        """
        stats = {}
        
        for t in self.round_trips:
            # Get value for the field
            if field == 'hour':
                val = t.entry_time.hour
            elif field == 'weekday':
                val = t.entry_time.strftime('%A')
            else:
                val = getattr(t, field, "Unknown")
                
            if val not in stats:
                stats[val] = {"count": 0, "pnl": 0.0, "wins": 0}
                
            stats[val]["count"] += 1
            stats[val]["pnl"] += t.net_pnl
            if t.net_pnl > 0:
                stats[val]["wins"] += 1
                
        # Finalize stats
        for val in stats:
            stats[val]["win_rate"] = round(stats[val]["wins"] / stats[val]["count"] * 100, 2)
            stats[val]["pnl"] = round(stats[val]["pnl"], 2)
            stats[val]["avg_pnl"] = round(stats[val]["pnl"] / stats[val]["count"], 2)
            
        return stats

    def print_report(self):
        summary = self.get_summary()
        if "error" in summary:
            print(f"\n⚠️ {summary['error']}")
            return
            
        print("\n" + "="*40)
        print("📊 BACKTEST DEEP ANALYSIS REPORT")
        print("="*40)
        print(f"Total Trades:  {summary['total_trades']}")
        print(f"Total Net PnL: ${summary['total_pnl']}")
        print(f"Win Rate:      {summary['win_rate']}%")
        print(f"Profit Factor: {summary['profit_factor']}")
        print(f"Avg Trade:     ${summary['avg_trade']}")
        
        print("\n📈 PERFORMANCE BY SYMBOL:")
        by_symbol = self.analyze_by('symbol')
        for sym, data in sorted(by_symbol.items(), key=lambda x: x[1]['pnl'], reverse=True):
            print(f"  {sym:5}: PnL: ${data['pnl']:8.2f} | WinRate: {data['win_rate']:6.2f}% | Count: {data['count']}")
            
        print("\n🕒 PERFORMANCE BY HOUR (UTC):")
        by_hour = self.analyze_by('hour')
        for hr, data in sorted(by_hour.items()):
            print(f"  {hr:02}h: PnL: ${data['pnl']:8.2f} | WinRate: {data['win_rate']:6.2f}% | Count: {data['count']}")
            
        print("\n📅 PERFORMANCE BY DAY:")
        by_day = self.analyze_by('weekday')
        days_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        for day in days_order:
            if day in by_day:
                data = by_day[day]
                print(f"  {day:9}: PnL: ${data['pnl']:8.2f} | WinRate: {data['win_rate']:6.2f}% | Count: {data['count']}")
        print("="*40 + "\n")
