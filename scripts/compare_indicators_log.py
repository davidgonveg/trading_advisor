import sqlite3
import pandas as pd
from datetime import datetime
import sys
from pathlib import Path

# Add root to path
sys.path.append(str(Path(__file__).parent.parent))

from data.storage.database import Database
from backtesting.data.feed import DatabaseFeed
from config.settings import SYMBOLS

def compare():
    db = Database()
    start_date = pd.Timestamp("2026-01-22", tz='UTC')
    end_date = pd.Timestamp("2026-01-23", tz='UTC')
    
    output_file = Path("comparison_log.txt")
    with open(output_file, "w") as f:
        for symbol in ["IWM", "SMH"]:
            f.write(f"\n--- DIAGNOSTIC: COMPARING {symbol} INDICATORS ---\n")
            
            # 1. Load from DB (Live Run)
            conn = db.get_connection()
            db_query = "SELECT * FROM indicators WHERE symbol = ? AND timestamp >= '2026-01-22' AND timestamp < '2026-01-23' ORDER BY timestamp"
            df_db = pd.read_sql_query(db_query, conn, params=(symbol,), parse_dates=['timestamp'])
            df_db.set_index('timestamp', inplace=True)
            conn.close()
            
            # 2. Load from Backtest Feed (Calculated on the fly)
            feed = DatabaseFeed(db, [symbol], start_date, end_date)
            df_bt = feed.data_store[symbol]
            
            # 3. Compare common timestamps
            common_ts = df_db.index.intersection(df_bt.index)
            
            if len(common_ts) == 0:
                f.write("No common timestamps found between DB and Backtest Feed for Jan 22.\n")
                continue

            # Pick target timestamps from your logs
            # IWM: 18:30 UTC
            # SMH: 16:30 UTC
            targets = [15, 16, 17, 18, 19, 20] # Check a range
            
            f.write(f"{'TS':<20} | {'Metric':<12} | {'Live (DB)':<12} | {'Backtest':<12} | {'Diff':<10}\n")
            f.write("-" * 75 + "\n")
            
            for ts in common_ts:
                if ts.hour in targets:
                    row_db = df_db.loc[ts]
                    row_bt = df_bt.loc[ts]
                    
                    # VWAP
                    v_db = row_db.get('vwap', 0)
                    v_bt = row_bt.get('VWAP', 0)
                    diff_v = abs(v_db - v_bt)
                    f.write(f"{str(ts):<20} | {'VWAP':<12} | {v_db:12.6f} | {v_bt:12.6f} | {diff_v:.6f}\n")
                    
                    # Vol SMA
                    vs_db = row_db.get('volume_sma_20', 0)
                    vs_bt = row_bt.get('Volume_SMA_20', 0)
                    diff_vs = abs(vs_db - vs_bt)
                    f.write(f"{'':<20} | {'Vol SMA':<12} | {vs_db:12.2f} | {vs_bt:12.2f} | {diff_vs:.2f}\n")
                    
                    # Wick Bull (BT only)
                    wick_bull = row_bt.get('pat_wick_bull', 0)
                    f.write(f"{'':<20} | {'Wick Bull':<12} | {'N/A':<12} | {wick_bull:12.6f} | {'N/A'}\n")
                    f.write("-" * 75 + "\n")

    print("Comparison log written to comparison_log.txt")

if __name__ == "__main__":
    compare()
