import csv
import os
from typing import List, Dict
from datetime import datetime

class SignalLogger:
    def __init__(self, output_dir="backtesting/results"):
        self.output_dir = output_dir
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        self.signals = []

    def log_signal(self, timestamp: datetime, symbol: str, direction: str, 
                   status: str = "ACCEPTED", reason: str = "",
                   entry_price: float = 0.0, sl_price: float = 0.0, 
                   e1_price: float = 0.0, e2_price: float = 0.0, e3_price: float = 0.0,
                   e1_qty: int = 0, e2_qty: int = 0, e3_qty: int = 0, atr: float = 0.0, 
                   indicators: Dict = None, notes: str = ""):
        
        signal = {
            "timestamp": timestamp,
            "symbol": symbol,
            "direction": direction,
            "status": status,
            "reason": reason,
            "entry_price": entry_price, 
            "sl_price": f"{sl_price:.2f}",
            "e1_price": f"{e1_price:.2f}",
            "e1_qty": e1_qty,
            "e2_price": f"{e2_price:.2f}",
            "e2_qty": e2_qty,
            "e3_price": f"{e3_price:.2f}",
            "e3_qty": e3_qty,
            "atr": f"{atr:.2f}",
            "notes": notes
        }
        
        # Merge Indicators
        if indicators:
            for k, v in indicators.items():
                # Avoid collision or prefix
                signal[k] = v
                
        self.signals.append(signal)

    def save_signals(self, filename="signals.csv"):
        path = os.path.join(self.output_dir, filename)
        if not self.signals:
            print(f"No signals to save to {path}")
            return

        # Dynamic Field Discovery
        # Collect all keys from all signals to ensure full coverage
        all_keys = set()
        for s in self.signals:
            all_keys.update(s.keys())
            
        # Prioritize standard fields order
        standard_fields = ["timestamp", "symbol", "direction", "status", "reason", "entry_price", "sl_price", 
                      "e1_price", "e1_qty", "e2_price", "e2_qty", "e3_price", "e3_qty", "atr", "notes"]
        
        # Sort remaining keys
        remaining = sorted([k for k in all_keys if k not in standard_fields])
        fieldnames = standard_fields + remaining
        
        with open(path, mode='w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(self.signals)
            
        print(f"Saved {len(self.signals)} detailed signals to {path}")
