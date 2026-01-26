import sys
import os
import pandas as pd
import sqlite3
from datetime import datetime, timedelta

# Add root to path
sys.path.append(os.getcwd())

try:
    from config.settings import DATABASE_PATH, SYMBOLS
except ImportError:
    # Fallback if config fails
    print("Warning: Could not import config. Using defaults.")
    DATABASE_PATH = "data/storage/trading.db"
    SYMBOLS = ["SPY", "QQQ", "IWM", "XLF", "XLE", "XLK", "SMH"]

def verify_strict():
    print(f"Checking Database: {DATABASE_PATH}")
    if not os.path.exists(DATABASE_PATH):
        print(f"CRITICAL: Database not found at {DATABASE_PATH}")
        return

    conn = sqlite3.connect(DATABASE_PATH)
    
    # 1. DUPLICATE CHECK
    print("\n--- 1. DUPLICATE CHECK ---")
    any_dupes = False
    for symbol in SYMBOLS:
        for tf in ['1h', '1d']:
            df = pd.read_sql(f"SELECT timestamp, symbol, timeframe FROM market_data WHERE symbol='{symbol}' AND timeframe='{tf}'", conn)
            if df.empty:
                print(f"⚠️ {symbol} {tf}: NO DATA found.")
                continue
            
            dupes = df[df.duplicated(subset=['timestamp'], keep=False)]
            if not dupes.empty:
                print(f"❌ {symbol} {tf}: FOUND {len(dupes)} DUPLICATE TIMESTAMPS!")
                print(dupes.head())
                any_dupes = True
            else:
                pass # print(f"✅ {symbol} {tf}: OK")
    
    if not any_dupes:
        print("✅ NO DUPLICATES FOUND IN ANY SYMBOL/TIMEFRAME.")

    # 2. GAP CHECK (Simple Business Day Logic)
    print("\n--- 2. CONTINUITY CHECK (Mon-Fri) ---")
    print("Assuming 1H data should be continuous for 09:30-16:00 ET Mon-Fri")
    
    for symbol in SYMBOLS:
        # Load 1H data
        df = pd.read_sql(f"SELECT timestamp FROM market_data WHERE symbol='{symbol}' AND timeframe='1h' ORDER BY timestamp", conn, parse_dates=['timestamp'])
        if df.empty: continue
        
        df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
        # Convert to ET for easier hour checks
        df['ti_et'] = df['timestamp'].dt.tz_convert('US/Eastern')
        
        # Filter RTH? Or check what we have.
        # Let's just look for "Large Gaps" > 1 hour within Weekdays.
        
        df = df.sort_values('timestamp')
        df['delta'] = df['timestamp'].diff()
        
        # Ignore weekend gaps (Friday close to Monday open)
        # 16:00 Fri -> 09:30 Mon is ~65.5 hours.
        # Overnight: 16:00 -> 09:30 is 17.5 hours.
        
        # We flag anything > 1H that isn't ~17.5h or ~65.5h
        # Allow +/- 1 hour fuzziness
        
        gaps = df[df['delta'] > timedelta(hours=1.1)]
        
        real_gaps = []
        for idx, row in gaps.iterrows():
            curr = row['timestamp']
            prev = row['timestamp'] - row['delta']
            
            hours = row['delta'].total_seconds() / 3600
            
            # Check if it looks like overnight
            is_overnight = (hours > 17 and hours < 18)
            is_weekend = (hours > 65 and hours < 66)
            is_holiday = (hours > 40 and hours < 42) # Maybe holiday?
            
            if not (is_overnight or is_weekend):
                 real_gaps.append((prev, curr, hours))
        
        if real_gaps:
             print(f"⚠️ {symbol} 1H: Found {len(real_gaps)} irregular gaps!")
             for i in range(min(5, len(real_gaps))):
                 p, c, h = real_gaps[i]
                 print(f"   Gap: {p} -> {c} ({h:.2f} hours)")
        else:
             print(f"✅ {symbol} 1H: Continuity looks good (Standard Market Hours).")

    conn.close()

if __name__ == "__main__":
    verify_strict()
