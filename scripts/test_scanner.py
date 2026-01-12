
import logging
import sys
import pandas as pd
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from config.settings import SYMBOLS
from data.storage.database import Database
from analysis.scanner import Scanner

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("scripts.test_scanner")

def test_scanner():
    print("\n🔎 TESTING SCANNER LOGIC")
    print("=" * 80)
    
    db = Database()
    scanner = Scanner()
    
    total_signals = 0
    
    for symbol in SYMBOLS:
        # Load Indicators Table which has everything (Prices + Indicators + Daily SMA merged)
        # Wait, indicators table has indicators but does it have OHLC?
        # Database.py schema: indicators table has rsi, bb..., sma_50. 
        # Does it have OPEN/HIGH/LOW/CLOSE/VOLUME?
        # Looking at database.py: 
        # CREATE TABLE market_data (open, high, low, close...)
        # CREATE TABLE indicators (rsi, bb..., sma_50...)
        
        # Scanner needs OHLC (for patterns) AND Indicators.
        # We need to JOIN them or load both and merge.
        
        # Let's load both and join.
        query = f'''
            SELECT 
                m.timestamp, m.open, m.high, m.low, m.close, m.volume,
                i.rsi, i.bb_lower, i.bb_upper, i.adx, i.sma_50, i.vwap, i.volume_sma_20
            FROM market_data m
            LEFT JOIN indicators i ON m.feature_id = i.feature_id
            WHERE m.symbol = '{symbol}' AND m.timeframe = '1h'
            ORDER BY m.timestamp ASC
        '''
        
        conn = db.get_connection()
        df = pd.read_sql_query(query, conn, parse_dates=['timestamp'], index_col='timestamp')
        conn.close()
        
        if df.empty:
            print(f"⚠️ {symbol}: No data found.")
            continue
            
        # Capitalize columns to match internal logic if needed
        # Database columns are lowercase.
        # Scanner expects: 'Close', 'RSI', 'BB_Lower', 'ADX', 'SMA_50' etc.
        # Map them.
        df.columns = [c.capitalize() for c in df.columns]
        # Fix specific casings
        df.rename(columns={
            'Bb_lower': 'BB_Lower', 
            'Bb_upper': 'BB_Upper',
            'Sma_50': 'SMA_50',
            'Volume_sma_20': 'Volume_SMA_20',
            'Vwap': 'VWAP',
            'Adx': 'ADX',
            'Rsi': 'RSI'
        }, inplace=True)
        
        # Also, df needs 'ATR' for the Signal object (scanner sets atr_value=row['ATR'])
        # Is ATR in indicators? Yes.
        # Add to query?
        # "i.rsi, i.bb_lower, i.bb_upper, i.adx, i.sma_50..."
        # I forgot ATR in the query above.
        
        # Let's re-query properly including ATR.
        
    print("... Re-defining query to include ATR ...")
    
    for symbol in SYMBOLS:
        conn = db.get_connection()
        # Full query
        query = f'''
            SELECT 
                m.timestamp, m.open, m.high, m.low, m.close, m.volume,
                i.rsi, i.bb_lower, i.bb_upper, i.adx, i.sma_50, i.vwap, i.volume_sma_20, i.atr
            FROM market_data m
            JOIN indicators i ON m.feature_id = i.feature_id
            WHERE m.symbol = '{symbol}' AND m.timeframe = '1h'
            ORDER BY m.timestamp ASC
        '''
        df = pd.read_sql_query(query, conn, parse_dates=['timestamp'], index_col='timestamp')
        conn.close()
        
        # Rename for Scanner compatibility
        df.rename(columns={
            'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume',
            'rsi': 'RSI', 'adx': 'ADX', 'atr': 'ATR', 'vwap': 'VWAP',
            'bb_lower': 'BB_Lower', 'bb_upper': 'BB_Upper', 
            'sma_50': 'SMA_50', 'volume_sma_20': 'Volume_SMA_20'
        }, inplace=True)
        
        # Run Scanner
        signals = scanner.find_signals(df, symbol)
        
        if signals:
            print(f"✅ {symbol}: Found {len(signals)} signals.")
            total_signals += len(signals)
            # Print last few signals
            for s in signals[-3:]:
                print(f"   -> {s}")
        else:
            print(f"Running... {symbol}: 0 signals.")

    print("=" * 80)
    print(f"TOTAL SIGNALS FOUND IN HISTORY: {total_signals}")

if __name__ == "__main__":
    test_scanner()
