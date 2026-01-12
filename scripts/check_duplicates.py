
import sys
import os
import pandas as pd
from data.storage.database import Database

# Append root to path
sys.path.append(os.getcwd())

def check_duplicates():
    db = Database()
    symbols = ["SPY", "QQQ", "IWM", "DIA", "GLD", "TLT"]
    
    print("Checking for duplicate timestamps in Database...")
    
    for symbol in symbols:
        print(f"\n--- {symbol} ---")
        try:
            df = db.load_market_data(symbol, "1h")
            if df.empty:
                print("No data.")
                continue
                
            dupes = df.index.duplicated().sum()
            if dupes > 0:
                print(f"❌ FOUND {dupes} DUPLICATE TIMESTAMP ROWS in Market Data!")
                print(df[df.index.duplicated(keep=False)].head())
            else:
                print("✅ Market Data Index Unique.")
                
            # Check Indicators
            df_ind = db.load_indicators(symbol, "1h")
            if not df_ind.empty:
                dupes_ind = df_ind.index.duplicated().sum()
                if dupes_ind > 0:
                    print(f"❌ FOUND {dupes_ind} DUPLICATE TIMESTAMP ROWS in Indicators!")
                else:
                    print("✅ Indicators Index Unique.")

        except Exception as e:
            print(f"Error checking {symbol}: {e}")

if __name__ == "__main__":
    check_duplicates()
