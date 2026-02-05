import sqlite3
import pandas as pd
from datetime import datetime

def check_data_range():
    conn = sqlite3.connect(r"data/storage/trading.db")
    cursor = conn.cursor()
    
    symbols = ["QQQ", "SPY", "IWM", "GLD", "XLK", "XLF", "SMH", "XLE"]
    
    print(f"{'SYMBOL':<10} {'MIN DATE':<25} {'MAX DATE':<25} {'COUNT':<10}")
    print("-" * 75)
    
    for symbol in symbols:
        try:
            # Check 1h
            query = f"SELECT MIN(timestamp), MAX(timestamp), COUNT(*) FROM market_data WHERE symbol = '{symbol}' AND timeframe = '1h'"
            cursor.execute(query)
            min_ts, max_ts, count = cursor.fetchone()
            print(f"{symbol:<10} {str(min_ts):<25} {str(max_ts):<25} {count:<10}")
            
        except Exception as e:
            print(f"{symbol:<10} ERROR: {e}")

    conn.close()

if __name__ == "__main__":
    check_data_range()
