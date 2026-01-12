import sys
import os
import sqlite3
import pandas as pd

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.connection import get_connection

def inspect_gaps():
    print("🔍 INSPECTING GAP DATABASE RECORDS")
    print("==================================")
    
    conn = get_connection()
    if not conn:
        print("❌ Cannot connect to DB")
        return

    # 1. Check existing fills
    print("\n1. 🛠️ Gap Fills Table (Fixed Gaps):")
    try:
        fills = pd.read_sql_query("SELECT * FROM gap_fills ORDER BY filled_at DESC LIMIT 10", conn)
        if not fills.empty:
            print(fills.to_string())
        else:
            print("   ⚠️ No records in 'gap_fills' table.")
    except Exception as e:
        print(f"   ❌ Error reading gap_fills: {e}")

    # 2. Check gap reports (Detections)
    print("\n2. 📋 Gap Reports Table (Detections):")
    try:
        reports = pd.read_sql_query("SELECT analysis_time, symbol, total_gaps, quality_score FROM gap_reports ORDER BY analysis_time DESC LIMIT 10", conn)
        if not reports.empty:
            print(reports.to_string())
        else:
            print("   ⚠️ No records in 'gap_reports' table.")
    except Exception as e:
        print(f"   ❌ Error reading gap_reports: {e}")
        
    conn.close()

if __name__ == "__main__":
    inspect_gaps()
