import csv
import os
from typing import List
from backtesting.simulation.broker_schema import Trade
from backtesting.simulation.analytics import RoundTrip

class TradeLogger:
    def __init__(self, output_dir="backtesting/results"):
        self.output_dir = output_dir
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
    def save_trades(self, trades: List[Trade], filename="trades.csv"):
        path = os.path.join(self.output_dir, filename)
        
        if not trades:
            print(f"No trades to save to {path}")
            return
            
        fieldnames = ["id", "order_id", "timestamp", "symbol", "side", "quantity", "price", "commission"]
        
        with open(path, mode='w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            
            for t in trades:
                row = {
                    "id": t.id,
                    "order_id": t.order_id,
                    "timestamp": t.timestamp,
                    "symbol": t.symbol,
                    "side": t.side.value,
                    "quantity": t.quantity,
                    "price": f"{t.price:.2f}",
                    "commission": f"{t.commission:.4f}"
                }
                writer.writerow(row)
        
        print(f"Saved {len(trades)} trades to {path}")

    def save_round_trips(self, trades: List[RoundTrip], filename="round_trips_detailed.csv"):
        path = os.path.join(self.output_dir, filename)
        
        if not trades:
            print(f"No round trips to save to {path}")
            return
            
        # Get fields from first object
        fieldnames = trades[0].to_dict().keys()
        
        with open(path, mode='w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            
            for t in trades:
                writer.writerow(t.to_dict())
                
        print(f"Saved {len(trades)} completed round trips to {path}")

    def save_equity_curve(self, curve: List[dict], filename="equity.csv"):
        path = os.path.join(self.output_dir, filename)
        
        if not curve:
            print(f"No equity curve data to save to {path}")
            return
            
        fieldnames = ["timestamp", "equity", "cash", "drawdown"]
        
        with open(path, mode='w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            
            for row in curve:
                writer.writerow(row)
                
        print(f"Saved {len(curve)} equity points to {path}")
