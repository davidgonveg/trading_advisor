import sqlite3
import pandas as pd

def check_ohlc():
    conn = sqlite3.connect("data/storage/trading.db")
    query = "SELECT timestamp, open, high, low, close, volume FROM market_data WHERE symbol = 'IWM' AND timestamp LIKE '2026-01-22%'"
    df = pd.read_sql_query(query, conn)
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
    target = pd.Timestamp("2026-01-22 18:30:00", tz='UTC')
    row = df[df['timestamp'] == target]
    with open("iwm_data.txt", "w") as f:
        if not row.empty:
            f.write(str(row.to_dict('records')[0]))
        else:
            f.write("Not found")
    conn.close()

if __name__ == "__main__":
    check_ohlc()
