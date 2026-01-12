import pandas as pd
import logging
from data.storage.database import Database
from config.settings import SYMBOLS

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("scripts.verify")

def verify_data():
    db = Database()
    conn = db.get_connection()
    
    print("\n🧐 DATA INTEGRITY VERIFICATION")
    print("=" * 60)
    
    # 1. Check Row Counts per Symbol/Timeframe
    print(f"{'SYMBOL':<10} {'TIMEFRAME':<10} {'COUNT':<10} {'START':<20} {'END':<20} {'FILLED %':<10}")
    print("-" * 80)
    
    total_gaps_found = 0
    
    for symbol in SYMBOLS:
        for tf in ["1h", "1d"]:
            query = f'''
                SELECT timestamp, is_filled 
                FROM market_data 
                WHERE symbol = '{symbol}' AND timeframe = '{tf}'
                ORDER BY timestamp ASC
            '''
            df = pd.read_sql_query(query, conn, parse_dates=['timestamp'])
            
            if df.empty:
                print(f"{symbol:<10} {tf:<10} {'0':<10} {'N/A':<20} {'N/A':<20} {'0%':<10}")
                continue
                
            count = len(df)
            start = df['timestamp'].iloc[0]
            end = df['timestamp'].iloc[-1]
            filled_count = df['is_filled'].sum() if 'is_filled' in df.columns else 0
            filled_pct = (filled_count / count) * 100
            
            print(f"{symbol:<10} {tf:<10} {count:<10} {str(start):<20} {str(end):<20} {filled_pct:.1f}%")
            
            # Simple Gap Check (Time delta)
            # Expected delta: 1H or 1D
            # We skip this detail in summary print, but could verify strict continuity.
            
    print("=" * 60)
            
    # 2. Check Indicators
    print("\n📊 INDICATORS VERIFICATION")
    print("=" * 60)
    print(f"{'SYMBOL':<10} {'TIMEFRAME':<10} {'COUNT':<10} {'SMA50 (Daily) EXISTS':<20}")
    print("-" * 80)
    
    for symbol in SYMBOLS:
        # Check 1H indicators
        query = f"SELECT count(*), count(sma_50) FROM indicators WHERE symbol='{symbol}' AND timeframe='1h'"
        res = conn.execute(query).fetchone()
        count = res[0]
        sma_count = res[1]
        
        has_sma = "YES" if sma_count > 0 else "NO"
        print(f"{symbol:<10} {'1h':<10} {count:<10} {has_sma:<20}")
        
    conn.close()

if __name__ == "__main__":
    verify_data()
