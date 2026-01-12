import sqlite3
import logging
from datetime import datetime
from typing import List, Optional, Dict
from pathlib import Path
import pandas as pd # Needed for type hinting and indicator saving
from config.settings import DATABASE_PATH
from data.interfaces import Candle

logger = logging.getLogger("core.data.database")

class Database:
    """
    SQLite Database Manager.
    Handles connection and schema initialization.
    """
    
    def __init__(self, db_path: Path = DATABASE_PATH):
        self.db_path = db_path
        self._ensure_db_dir()
        self._init_schema()
        
    def _ensure_db_dir(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
    def get_connection(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)
    
    def _init_schema(self):
        """Initialize the database schema if it doesn't exist."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # 1. Continuous Data (OHLCV)
            # Storing raw market data
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS market_data (
                feature_id TEXT PRIMARY KEY, -- symbol_timeframe_timestamp
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                timestamp DATETIME NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume REAL NOT NULL,
                source TEXT DEFAULT 'YFINANCE',
                is_filled BOOLEAN DEFAULT 0,
                UNIQUE(symbol, timeframe, timestamp)
            )
            ''')
            
            # Indicators Table
            # Storing JSON blobb or specific columns?
            # Specific columns are better for querying.
            # We'll store key indicators.
            conn.execute('''
            CREATE TABLE IF NOT EXISTS indicators (
                feature_id TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                timestamp DATETIME NOT NULL,
                
                rsi REAL,
                bb_upper REAL,
                bb_middle REAL,
                bb_lower REAL,
                adx REAL,
                atr REAL,
                vwap REAL,
                sma_50 REAL,
                volume_sma_20 REAL,
                
                UNIQUE(symbol, timeframe, timestamp)
            )
            ''')
            
            # 2. Signals (Trading Opportunities)
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME NOT NULL,
                symbol TEXT NOT NULL,
                signal_type TEXT NOT NULL, -- LONG/SHORT
                strength REAL,
                status TEXT DEFAULT 'NEW',  -- NEW, PROCESSED, EXECUTED
                metadata TEXT -- JSON string for extra details
            )
            ''')
            
            # 3. Trades (Execution History)
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                entry_time DATETIME NOT NULL,
                entry_price REAL NOT NULL,
                side TEXT NOT NULL,
                size REAL,
                exit_time DATETIME,
                exit_price REAL,
                pnl REAL,
                status TEXT -- OPEN, CLOSED
            )
            ''')
            
            conn.commit()
            logger.info("Database schema initialized.")
            
        except Exception as e:
            logger.error(f"Failed to init schema: {e}")
            raise
        finally:
            conn.close()

    def save_candle(self, symbol: str, timeframe: str, candle: Candle, is_filled: bool = False):
        """Save a single candle."""
        conn = self.get_connection()
        try:
            # Create a unique ID or let SQLite handle uniqueness constraint
            conn.execute('''
            INSERT OR REPLACE INTO market_data 
            (feature_id, symbol, timeframe, timestamp, open, high, low, close, volume, is_filled)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                f"{symbol}_{timeframe}_{candle.timestamp.isoformat()}",
                symbol, timeframe, candle.timestamp,
                candle.open, candle.high, candle.low, candle.close, candle.volume, is_filled
            ))
            conn.commit()
        except Exception as e:
            logger.error(f"Error saving candle: {e}")
        finally:
            conn.close()

    def save_bulk_candles(self, symbol: str, timeframe: str, candles: List[Candle], is_filled_list: List[bool] = None):
        """Save multiple candles efficiently."""
        conn = self.get_connection()
        try:
            if is_filled_list is None:
                is_filled_list = [False] * len(candles)
                
            data = [
                (
                    f"{symbol}_{timeframe}_{c.timestamp.isoformat()}",
                    symbol, timeframe, c.timestamp,
                    c.open, c.high, c.low, c.close, c.volume, filled
                )
                for c, filled in zip(candles, is_filled_list)
            ]
            
            conn.executemany('''
            INSERT OR REPLACE INTO market_data 
            (feature_id, symbol, timeframe, timestamp, open, high, low, close, volume, is_filled)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', data)
            conn.commit()
            logger.info(f"Saved {len(candles)} candles for {symbol}")
        except Exception as e:
            logger.error(f"Error saving bulk candles: {e}")
        finally:
            conn.close()

    def save_indicators(self, symbol: str, timeframe: str, df: pd.DataFrame):
        """Save calculated indicators to DB."""
        conn = self.get_connection()
        try:
            data = []
            for idx, row in df.iterrows():
                # Timestamp is the index
                ts = idx.to_pydatetime()
                fid = f"{symbol}_{timeframe}_{ts.isoformat()}"
                
                # Extract values safely
                rsi = row.get('RSI')
                bbu = row.get('BB_Upper')
                bbm = row.get('BB_Middle')
                bbl = row.get('BB_Lower')
                adx = row.get('ADX')
                atr = row.get('ATR')
                vwap = row.get('VWAP')
                sma50 = row.get('SMA_50')
                vsma20 = row.get('Volume_SMA_20')
                
                # Check for nan before insertion? SQLite handles NULL for None.
                # Pandas NaN should be converted to None.
                def to_val(v): return None if pd.isna(v) else float(v)
                
                data.append((
                    fid, symbol, timeframe, ts,
                    to_val(rsi), to_val(bbu), to_val(bbm), to_val(bbl),
                    to_val(adx), to_val(atr), to_val(vwap), to_val(sma50), to_val(vsma20)
                ))
            
            conn.executemany('''
            INSERT OR REPLACE INTO indicators 
            (feature_id, symbol, timeframe, timestamp, rsi, bb_upper, bb_middle, bb_lower, adx, atr, vwap, sma_50, volume_sma_20)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', data)
            conn.commit()
            logger.info(f"Saved {len(data)} indicator rows for {symbol}")
            
        except Exception as e:
            logger.error(f"Error saving indicators: {e}")
        finally:
            conn.close()
