import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import sys
import os

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.connection import get_connection

def inspect_data(symbol="^GSPC"):
    print(f"\n🔍 INSPECTING CONTINUOUS DATA FOR {symbol}")
    conn = get_connection()
    if not conn:
        print("❌ No DB connection")
        return

    # Count total rows
    cursor = conn.cursor()
    cursor.execute("SELECT count(*) FROM continuous_data WHERE symbol=?", (symbol,))
    count = cursor.fetchone()[0]
    print(f"📊 Total rows: {count}")

    # Check filled gaps specifically
    cursor.execute("SELECT count(*) FROM continuous_data WHERE symbol=? AND is_gap_filled=1", (symbol,))
    filled_count = cursor.fetchone()[0]
    print(f"🔧 Filled gap rows: {filled_count}")

    # Dump last 5 filled rows
    print("\n📝 Last 5 FILLED rows:")
    query_filled = '''
    SELECT timestamp, open_price, close_price, is_gap_filled, data_source
    FROM continuous_data 
    WHERE symbol=? AND is_gap_filled=1
    ORDER BY timestamp DESC
    LIMIT 5
    '''
    df_filled = pd.read_sql_query(query_filled, conn, params=(symbol,))
    print(df_filled)
    
    # Dump last 5 Regular rows
    print("\n📝 Last 5 REGULAR rows:")
    query_reg = '''
    SELECT timestamp, open_price, close_price, is_gap_filled, data_source
    FROM continuous_data 
    WHERE symbol=?
    ORDER BY timestamp DESC
    LIMIT 5
    '''
    df_reg = pd.read_sql_query(query_reg, conn, params=(symbol,))
    print(df_reg)

    conn.close()

if __name__ == "__main__":
    inspect_data("^GSPC")
    inspect_data("AAPL")
