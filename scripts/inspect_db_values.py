
import pandas as pd
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
from data.storage.database import Database

def inspect():
    db = Database()
    conn = db.get_connection()
    symbol = "SPY"
    
    print(f"--- Market Data {symbol} 1H ---")
    df_m = pd.read_sql_query(f"SELECT * FROM market_data WHERE symbol='{symbol}' AND timeframe='1h' LIMIT 5", conn)
    print(df_m)
    
    print(f"\n--- Indicators {symbol} 1H ---")
    df_i = pd.read_sql_query(f"SELECT * FROM indicators WHERE symbol='{symbol}' AND timeframe='1h' LIMIT 5", conn)
    print(df_i) 
    
    conn.close()

if __name__ == "__main__":
    inspect()
