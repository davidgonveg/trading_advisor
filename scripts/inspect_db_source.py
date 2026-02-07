import sqlite3
import pandas as pd

def inspect_source():
    conn = sqlite3.connect('data/storage/trading.db')
    try:
        # Check columns first to see if 'source' exists
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(market_data)")
        cols = [info[1] for info in cursor.fetchall()]
        print(f"Columns: {cols}")
        
        if 'source' in cols:
            df = pd.read_sql_query('SELECT timestamp, open, close, volume, source FROM market_data WHERE symbol="QQQ" AND timeframe="1h" AND volume > 0 LIMIT 20', conn)
        else:
            df = pd.read_sql_query('SELECT timestamp, open, close, volume FROM market_data WHERE symbol="QQQ" AND timeframe="1h" AND volume > 0 LIMIT 20', conn)
            
        print(df)
    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    inspect_source()
