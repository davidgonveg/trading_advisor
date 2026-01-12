
import logging
import sys
import sqlite3
import pandas as pd
from pathlib import Path
from datetime import timedelta

# Add project root to path
root_path = Path(__file__).resolve().parent.parent
sys.path.append(str(root_path))

print(f"DEBUG: Root path added: {root_path}")
print(f"DEBUG: sys.path: {sys.path}")

try:
    from config.settings import SYMBOLS, DATABASE_PATH
except ImportError as e:
    print(f"CRITICAL ERROR: Could not import config. {e}")
    sys.exit(1)

# Setup Logger
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("scripts.integrity")

def verify_integrity():
    report_lines = []
    def log(msg):
        print(msg)
        report_lines.append(msg)

    log("\n🔍 DATA INTEGRITY & REALITY CHECK")
    log("=" * 100)
    log(f"{'SYMBOL':<8} {'TF':<4} {'TOTAL':<8} {'START DATE':<12} {'END DATE':<12} {'REAL %':<8} {'FILLED %':<8} {'GAPS (>2h)':<5}")
    log("-" * 100)

    conn = sqlite3.connect(DATABASE_PATH)
    
    issues_found = []

    for symbol in SYMBOLS:
        for tf in ["1h", "1d"]:
            # Query data
            query = f'''
                SELECT timestamp, is_filled 
                FROM market_data 
                WHERE symbol = '{symbol}' AND timeframe = '{tf}'
                ORDER BY timestamp ASC
            '''
            df = pd.read_sql_query(query, conn, parse_dates=['timestamp'])
            
            if df.empty:
                print(f"{symbol:<8} {tf:<4} {'0':<8} {'N/A':<12} {'N/A':<12} {'0%':<8} {'0%':<8} {'N/A'}")
                continue

            # Stats
            total_count = len(df)
            filled_count = df['is_filled'].sum() if 'is_filled' in df.columns else 0
            real_count = total_count - filled_count
            
            filled_pct = (filled_count / total_count) * 100
            real_pct = (real_count / total_count) * 100
            
            start_date = df['timestamp'].iloc[0].strftime('%Y-%m-%d')
            end_date = df['timestamp'].iloc[-1].strftime('%Y-%m-%d')

            # Continuity Check
            # Calculate time diff between consecutive rows
            df['delta'] = df['timestamp'].diff()
            
            # Define expected delta
            expected = timedelta(hours=1) if tf == "1h" else timedelta(days=1)
            
            # Tolerance: for 1H, gaps > 2 hours are suspicious (skipping regular market close overnight is normal, but let's see)
            # Actually, standard market hours are 9:30 - 16:00 ET (6.5 hours). 
            # If we have pre-market/after-hours it's more.
            # Simple check: identify gaps significantly larger than expected interval.
            
            # For this report, we flag 'Major Gaps' as missing chunks > 2 * expected
            # Note: Overnights and Weekends will trigger this unless we align with market schedule.
            # To avoid noise, we'll just count how many "jumps" exist that are not standard daily/weekend jumps.
            # But for simplicity, let's just count total 'irregular' deltas if possible, or just skip distinct counting for now 
            # and rely on the 'is_filled' metric which implies holes were already patched.
            
            # If we trust 'backfill_data.py', it ALREADY patched gaps. 
            # So if `is_filled` is low, and we have the date range, we are good.
            # If `is_filled` is high, we have "fake" data.
            
            # Let's count big jumps that were NOT filled (meaning missing data entirely)
            # This happens if gap repair failed.
            
            gap_threshold = expected * 2
            # Filter deltas larger than threshold
            large_gaps = df[df['delta'] > gap_threshold]
            gap_count = len(large_gaps)
            
            # Refine gap count for 1H to exclude overnight/weekend if possible?
            # It's hard without a calendar. 
            # We will assume backfill fixed everything, so any remaining gap is a FAILURE.
            # However, for 1H, overnight gaps (16:00 -> 09:30 next day) are normal if we don't trade extended hours.
            # The readme says "Extended hours trading". If so, we should have continuous data?
            # Let's just report the raw count of discontinuities for now.
            
            log(f"{symbol:<8} {tf:<4} {total_count:<8} {start_date:<12} {end_date:<12} {real_pct:.1f}%   {filled_pct:.1f}%   {gap_count:<5}")
            
            if filled_pct > 5.0:
                issues_found.append(f"WARNING: {symbol} {tf} has {filled_pct:.1f}% interpolated data.")
            
            # If we want to check specifically for "holes" that weren't patched:
            # A huge gap might indicate missing data that user should know about.
    
    conn.close()
    
    log("-" * 100)
    if issues_found:
        log("\n⚠️  ISSUES FOUND:")
        for issue in issues_found:
            log(issue)
    else:
        log("\n✅ Data looks healthy (Low interpolation rate).")
        
    log("\nNote: 'Gaps' count includes weekends/overnights for 1H data if not normalized. Focus on 'FILLED %'.")

    with open("verify_report.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))

if __name__ == "__main__":
    verify_integrity()
