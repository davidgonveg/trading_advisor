import sqlite3
from pathlib import Path

db_path = Path("data/storage/trading.db")
if not db_path.exists():
    print(f"Error: Database not found at {db_path}")
else:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    query = """
        SELECT symbol, timestamp, close 
        FROM market_data 
        WHERE (symbol, timestamp) IN (
            SELECT symbol, MAX(timestamp) 
            FROM market_data 
            GROUP BY symbol
        )
    """
    cursor.execute(query)
    rows = cursor.fetchall()
    conn.close()
    if not rows:
        print("No data found in market_data table.")
    else:
        print(f"{'Symbol':<10} {'Timestamp':<25} {'Price':<10}")
        print("-" * 50)
        for row in rows:
            print(f"{row[0]:<10} {row[1]:<25} {row[2]:<10.2f}")
