import pandas as pd
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
from data.storage.database import Database

def inspect():
    db = Database()
    conn = db.get_connection()
    symbol = "QQQ"
    
    print(f"--- Market Data {symbol} 1H (Detail) ---")
    # Get 50 rows to see the timestamps
    df_m = pd.read_sql_query(f"SELECT * FROM market_data WHERE symbol='{symbol}' AND timeframe='1h' ORDER BY timestamp ASC LIMIT 50", conn)
    print(df_m[['timestamp', 'open', 'high', 'low', 'close', 'volume']])
    
    conn.close()

if __name__ == "__main__":
    inspect()
