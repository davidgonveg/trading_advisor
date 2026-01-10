#!/usr/bin/env python3
"""
🧪 DATA INTEGRITY VERIFICATION SCRIPT
=====================================
Verifies the continuity and quality of data in the 'continuous_data' table.
Checks for:
1. Gaps in timestamps during market hours.
2. Consistency of overnight data.
3. Presence of required tables.
"""

import sys
import os
import sqlite3
import pandas as pd
from datetime import datetime, timedelta, time
import logging

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.connection import get_connection

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("DataVerifier")

def verify_table_existence():
    """Verify that all V3.1 tables exist."""
    print("\n🔍 1. Checking Table Structure...")
    conn = get_connection()
    if not conn:
        print("❌ Could not connect to database.")
        return False
    
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    
    required_tables = ['continuous_data', 'gap_reports', 'gap_fills', 'indicators_data', 'signals_sent']
    all_present = True
    
    for table in required_tables:
        if table in tables:
            print(f"   ✅ Table '{table}' found.")
        else:
            print(f"   ❌ Table '{table}' MISSING!")
            all_present = False
            
    conn.close()
    return all_present

def analyze_continuity(symbol="SPY", days_back=7):
    """Analyze data continuity for a specific symbol."""
    print(f"\n🔍 2. Analyzing Continuity for {symbol} (Last {days_back} days)...")
    
    conn = get_connection()
    if not conn:
        return
    
    query = """
    SELECT timestamp, session_type 
    FROM continuous_data 
    WHERE symbol = ? AND datetime(timestamp) >= datetime('now', ?)
    ORDER BY timestamp ASC
    """
    
    try:
        df = pd.read_sql_query(query, conn, params=(symbol, f'-{days_back} days'))
        if df.empty:
            print(f"   ⚠️ No data found in 'continuous_data' for {symbol} in the last {days_back} days.")
            print("      (This might be normal if you just started the collector)")
            return

        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df['diff'] = df['timestamp'].diff()
        
        # Check standard intervals (assuming 15m for REGULAR)
        # Allows for some tolerance
        
        print(f"   📊 Total Data Points: {len(df)}")
        print(f"   📅 Time Range: {df['timestamp'].min()} to {df['timestamp'].max()}")
        
        # Analyze gaps > 30 minutes in REGULAR session
        regular_data = df[df['session_type'] == 'REGULAR'].copy()
        if not regular_data.empty:
            regular_data['diff_minutes'] = regular_data['timestamp'].diff().dt.total_seconds() / 60
            
            # Allow 15 min interval, so gap > 20 min is suspicious
            gaps = regular_data[regular_data['diff_minutes'] > 20]
            
            if len(gaps) == 0:
                print("   ✅ REGULAR Session: No continuity gaps found (>20m).")
            else:
                print(f"   ⚠️ REGULAR Session: {len(gaps)} potential gaps detected:")
                for _, row in gaps.head(5).iterrows():
                    print(f"      - Gap of {row['diff_minutes']:.1f} min ending at {row['timestamp']}")
        else:
            print("   ⚠️ No REGULAR session data found.")

        # Analyze OVERNIGHT data
        overnight_data = df[df['session_type'] == 'OVERNIGHT']
        if not overnight_data.empty:
            print(f"   ✅ OVERNIGHT Session: Found {len(overnight_data)} data points (Good!)")
        else:
            print("   ℹ️ OVERNIGHT Session: No data found (Collector might not be running overnight).")

    except Exception as e:
        print(f"   ❌ Error analyzing continuity: {e}")
    finally:
        conn.close()

def check_recent_activity():
    """Check when data was last written."""
    print("\n🔍 3. Checking Recent Activity...")
    conn = get_connection()
    if not conn:
        return

    cursor = conn.cursor()
    cursor.execute("SELECT MAX(timestamp), symbol FROM continuous_data GROUP BY symbol")
    rows = cursor.fetchall()
    
    if not rows:
        print("   ⚠️ No data in continuous_data table.")
    else:
        # Get UTC now or local aware now
        now = datetime.now()
        
        print(f"   Current System Time: {now}")
        for row in rows:
            last_ts_str = row[0]
            symbol = row[1]
            try:
                # Handle potential timezone offset in string
                if '+' in last_ts_str or '-' in last_ts_str[-6:]: # Simple check for TZ
                     last_ts = datetime.fromisoformat(last_ts_str)
                     # Make now aware if not
                     if last_ts.tzinfo is not None and now.tzinfo is None:
                         now = now.astimezone()
                else:
                     last_ts = datetime.fromisoformat(last_ts_str)

                age = now - last_ts
                status = "✅ Active" if age.total_seconds() < 3600 else "⚠️ Stale"
                print(f"   - {symbol}: Last update {last_ts} ({age} ago) -> {status}")
            except Exception as e:
                 print(f"   - {symbol}: Error parsing date '{last_ts_str}': {e}")
    
    conn.close()

if __name__ == "__main__":
    print("==========================================")
    print("   DATA INTEGRITY VERIFIER V1.0")
    print("==========================================")
    
    if verify_table_existence():
        analyze_continuity("SPY", days_back=5)
        check_recent_activity()
    
    print("\n==========================================")
    print("   VERIFICATION COMPLETE")
    print("==========================================")
