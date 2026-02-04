
import logging
import sys
import os
import sqlite3
import pandas as pd
from datetime import datetime

# Adjust path to find core modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from data.storage.database import Database
from config.settings import DATABASE_PATH

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("db_cleanup")

def cleanup_duplicates():
    logger.info("Starting Database Cleanup...")
    db = Database()
    conn = sqlite3.connect(DATABASE_PATH)
    
    try:
        # Get all symbols and timeframes
        query = "SELECT DISTINCT symbol, timeframe FROM market_data"
        cursor = conn.cursor()
        cursor.execute(query)
        pairs = cursor.fetchall()
        
        logger.info(f"Found {len(pairs)} symbol/timeframe pairs to process.")
        
        for symbol, timeframe in pairs:
            logger.info(f"Processing {symbol} {timeframe}...")
            
            # Load raw data
            df = pd.read_sql_query(
                "SELECT * FROM market_data WHERE symbol = ? AND timeframe = ?", 
                conn, 
                params=(symbol, timeframe)
            )
            
            if df.empty:
                continue
                
            original_count = len(df)
            
            # Normalize timestamps to UTC
            # Some might be strings like '2023-01-01 10:00:00' (naive) or '...-05:00' (offset)
            df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True, format='mixed')
            
            # Drop duplicates based on timestamp, keeping the LAST one (assuming latest fetch is best)
            df_clean = df.drop_duplicates(subset=['timestamp'], keep='last')
            
            clean_count = len(df_clean)
            removed = original_count - clean_count
            
            if removed > 0:
                logger.info(f"  - Removing {removed} duplicates for {symbol} {timeframe}...")
                
                # Delete ALL for this symbol/timeframe
                cursor.execute(
                    "DELETE FROM market_data WHERE symbol = ? AND timeframe = ?", 
                    (symbol, timeframe)
                )
                
                # Re-insert clean data
                # We need to map DataFrame back to SQL insert format
                # The schema is: feature_id, symbol, timeframe, timestamp, open, high, low, close, volume, source, is_filled
                
                # Re-generate feature_id to be safe and consistent
                # feature_id = symbol_timeframe_timestamp
                # Ensure timestamp is ISO string
                
                data_to_insert = []
                for idx, row in df_clean.iterrows():
                    ts_iso = row['timestamp'].isoformat()
                    feature_id = f"{symbol}_{timeframe}_{ts_iso}"
                    
                    data_to_insert.append((
                        feature_id,
                        symbol,
                        timeframe,
                        ts_iso,
                        row['open'],
                        row['high'],
                        row['low'],
                        row['close'],
                        row['volume'],
                        row.get('source', 'UNKNOWN'),
                        row.get('is_filled', 0)
                    ))
                
                cursor.executemany('''
                INSERT INTO market_data 
                (feature_id, symbol, timeframe, timestamp, open, high, low, close, volume, source, is_filled)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', data_to_insert)
                
                conn.commit()
                logger.info(f"  - Cleaned and re-inserted {clean_count} records.")
            else:
                logger.info(f"  - No duplicates found (Clean count: {clean_count}).")
                
    except Exception as e:
        logger.error(f"Cleanup failed: {e}")
        conn.rollback()
    finally:
        conn.close()
        logger.info("Cleanup Complete.")

if __name__ == "__main__":
    cleanup_duplicates()
