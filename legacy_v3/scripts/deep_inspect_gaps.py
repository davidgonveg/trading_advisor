import sqlite3
import pandas as pd
import json
import sys
import os
from datetime import datetime

# Add project root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.connection import get_connection

def deep_inspect(symbol="^NDX"):
    print(f"\n=======================================================")
    print(f"🕵️‍♂️ DEEP INSPECTION FOR {symbol}")
    print(f"=======================================================")
    
    conn = get_connection()
    if not conn:
        print("❌ Connect failed")
        return

    # 1. Check GAP REPORTS (What does the system SEE?)
    print(f"\n📊 --- LATEST GAP REPORT ---")
    query_report = '''
    SELECT * FROM gap_reports 
    WHERE symbol = ? 
    ORDER BY analysis_time DESC 
    LIMIT 1
    '''
    df_report = pd.read_sql_query(query_report, conn, params=(symbol,))
    
    if not df_report.empty:
        row = df_report.iloc[0]
        print(f"📅 Report Time: {row['analysis_time']}")
        print(f"📉 Total Gaps: {row['total_gaps']}")
        print(f"🔧 Gaps Filled: {row['gaps_filled_count']}")
        
        # Parse JSONs safely
        print("🏷️ Details:")
        try:
            if row['gaps_by_type']:
                print(f"   Types: {json.loads(row['gaps_by_type'])}")
            else:
                print("   Types: (empty)")
        except:
            print(f"   Types: {row['gaps_by_type']}")
            
        sys.stdout.flush()
    else:
        print("⚠️ No gap reports found.")

    # 2. Check CONTINUOUS DATA (What is SAVED?)
    print(f"\n💾 --- CONTINUOUS DATA STORAGE ---")
    
    # Count total
    cursor = conn.cursor()
    cursor.execute("SELECT count(*) FROM continuous_data WHERE symbol=?", (symbol,))
    total = cursor.fetchone()[0]
    
    cursor.execute("SELECT count(*) FROM continuous_data WHERE symbol=? AND is_gap_filled=1", (symbol,))
    filled = cursor.fetchone()[0]
    
    print(f"📦 Total Rows: {total}")
    print(f"🩹 Filled Rows (is_gap_filled=1): {filled}")
    
    sys.stdout.flush()
    
    # Show distribution of data sources
    print("\nDates Source Distribution:")
    df_sources = pd.read_sql_query(
        "SELECT data_source, count(*) as count FROM continuous_data WHERE symbol=? GROUP BY data_source",
        conn, params=(symbol,)
    )
    print(df_sources)
    
    # Show last 10 filled rows to check timestamps
    if filled > 0:
        print("\n📝 Last 5 FILLED rows:")
        df_filled = pd.read_sql_query(
            "SELECT timestamp, open_price, is_gap_filled, data_source FROM continuous_data WHERE symbol=? AND is_gap_filled=1 ORDER BY timestamp DESC LIMIT 5",
            conn, params=(symbol,)
        )
        print(df_filled)

    conn.close()

if __name__ == "__main__":
    deep_inspect("^NDX")
    deep_inspect("AAPL")
