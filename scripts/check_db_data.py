import sqlite3
import pandas as pd
from datetime import datetime

def check_data():
    conn = sqlite3.connect("data/storage/trading.db")
    
    print("--- ALERTS IN DB ---")
    try:
        alerts = pd.read_sql_query("SELECT * FROM alerts WHERE timestamp LIKE '2026-01-22%'", conn)
        print(alerts)
    except Exception as e:
        print(f"Error reading alerts: {e}")

    print("\n--- MARKET DATA SAMPLE (IWM, 2026-01-22) ---")
    try:
        # Check if we have data for the specific hour reported: 18:30 UTC
        # Note: data_manager likely saves hourly candles
        query = "SELECT * FROM market_data WHERE symbol = 'IWM' AND timestamp LIKE '2026-01-22%' ORDER BY timestamp DESC LIMIT 10"
        data = pd.read_sql_query(query, conn)
        print(data)
    except Exception as e:
        print(f"Error reading market_data: {e}")

    print("\n--- INDICATORS SAMPLE (IWM, 2026-01-22) ---")
    try:
        query = "SELECT * FROM indicators WHERE symbol = 'IWM' AND timestamp LIKE '2026-01-22%' ORDER BY timestamp DESC LIMIT 10"
        inds = pd.read_sql_query(query, conn)
        print(inds)
    except Exception as e:
        print(f"Error reading indicators: {e}")

    conn.close()

if __name__ == "__main__":
    check_data()
