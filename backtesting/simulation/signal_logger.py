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
                   entry_price: float, sl_price: float, 
                   e1_price: float, e2_price: float, e3_price: float,
                   e1_qty: int, e2_qty: int, e3_qty: int, atr: float, notes: str = ""):
        
        signal = {
            "timestamp": timestamp,
            "symbol": symbol,
            "direction": direction,
            "entry_price": entry_price, # Reference Price
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
        self.signals.append(signal)

    def save_signals(self, filename="signals.csv"):
        path = os.path.join(self.output_dir, filename)
        if not self.signals:
            print(f"No signals to save to {path}")
            return

        fieldnames = ["timestamp", "symbol", "direction", "entry_price", "sl_price", 
                      "e1_price", "e1_qty", "e2_price", "e2_qty", "e3_price", "e3_qty", "atr", "notes"]
        
        with open(path, mode='w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(self.signals)
            
        print(f"Saved {len(self.signals)} detailed signals to {path}")
