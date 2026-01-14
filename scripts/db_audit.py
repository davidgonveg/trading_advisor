
import sqlite3
import pandas as pd
import sys
from pathlib import Path
from datetime import datetime

# Setup Path to include root
current_dir = Path.cwd()
sys.path.append(str(current_dir))

# Try importing as package, if fails, try direct file import mock or ensure proper structure
try:
    from config.settings import SYMBOLS, DATABASE_PATH
except ImportError:
    # Fallback if running from scripts dir directly or package issue
    sys.path.append(str(current_dir.parent))
    from config.settings import SYMBOLS, DATABASE_PATH

def audit_database():
    print(f"--- DATABASE AUDIT ---")
    print(f"DB Path: {DATABASE_PATH}")
    
    if not DATABASE_PATH.exists():
        print("❌ Database file not found!")
        return

    conn = sqlite3.connect(DATABASE_PATH)
    
    results = []
    
    try:
        for symbol in SYMBOLS:
            for timeframe in ["1h", "1d"]:
                # Query Market Data
                query_md = f"""
                    SELECT 
                        MIN(timestamp) as start_date, 
                        MAX(timestamp) as end_date, 
                        COUNT(*) as count 
                    FROM market_data 
                    WHERE symbol = '{symbol}' AND timeframe = '{timeframe}'
                """
                df_md = pd.read_sql_query(query_md, conn)
                
                # Query Indicators
                query_ind = f"""
                    SELECT 
                        COUNT(*) as count 
                    FROM indicators 
                    WHERE symbol = '{symbol}' AND timeframe = '{timeframe}'
                """
                # Indicators might only exist for 1h usually, but verifying both
                try:
                    df_ind = pd.read_sql_query(query_ind, conn)
                    ind_count = df_ind['count'].iloc[0]
                except Exception:
                    ind_count = 0
                
                start = df_md['start_date'].iloc[0]
                end = df_md['end_date'].iloc[0]
                count = df_md['count'].iloc[0]
                
                results.append({
                    "Symbol": symbol,
                    "TF": timeframe,
                    "Start": start,
                    "End": end,
                    "Rows (Data)": count,
                    "Rows (Inds)": ind_count,
                    "Status": "✅ OK" if count > 0 else "❌ EMPTY"
                })
                
    except Exception as e:
        print(f"Error during audit: {e}")
    finally:
        conn.close()
        
    # Display
    df_res = pd.DataFrame(results)
    if not df_res.empty:
        # Format for readability
        print(df_res.to_string(index=False))
        
        # Summary Check
        total_rows = df_res['Rows (Data)'].sum()
        print(f"\nTotal Data Rows: {total_rows}")
        print("Audit Complete.")
    else:
        print("No results generated.")

if __name__ == "__main__":
    audit_database()
