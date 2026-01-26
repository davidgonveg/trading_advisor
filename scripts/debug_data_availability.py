import sys
import os
sys.path.insert(0, os.getcwd())
from data.storage.database import Database
from datetime import datetime, timezone

def check():
    db = Database()
    symbols = ["SPY", "QQQ", "IWM", "XLF", "XLE", "XLK", "SMH"]
    start_date = datetime(2023, 1, 1, tzinfo=timezone.utc)
    end_date = datetime(2024, 12, 31, tzinfo=timezone.utc)
    
    print(f"Checking data for {symbols} from {start_date} to {end_date}")
    
    for sym in symbols:
        # Check count of 1H candles
        # Assuming table is 'market_data' and has 'symbol', 'timestamp', 'timeframe'
        # timeframe might be '1h' or '1H'
        
        query = """
        SELECT COUNT(*), MIN(timestamp), MAX(timestamp) 
        FROM market_data 
        WHERE symbol = ? 
        AND timestamp >= ? AND timestamp <= ?
        AND timeframe = '1h'
        """
        
        try:
            with db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, (sym, start_date.isoformat(), end_date.isoformat()))
                res = cursor.fetchone()
                print(f"{sym}: Count={res[0]}, Range={res[1]} to {res[2]}")
                
                if res[0] > 0:
                    # Check Volume
                    q_vol = "SELECT AVG(volume) FROM market_data WHERE symbol = ? AND timeframe = '1h' LIMIT 10"
                    cursor.execute(q_vol, (sym,))
                    vol = cursor.fetchone()
                    print(f"   Avg Vol Sample: {vol[0]}")
        except Exception as e:
            print(f"Error checking {sym}: {e}")

if __name__ == "__main__":
    check()
