import sqlite3
import pandas as pd

def check_alerts():
    conn = sqlite3.connect("data/storage/trading.db")
    query = "SELECT timestamp, symbol FROM alerts WHERE timestamp LIKE '2026-01-22%'"
    df = pd.read_sql_query(query, conn)
    print(df)
    conn.close()

if __name__ == "__main__":
    check_alerts()
