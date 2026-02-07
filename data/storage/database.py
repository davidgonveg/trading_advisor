import sqlite3
import logging
from datetime import datetime
from typing import List, Optional, Dict
from pathlib import Path
import pandas as pd
from config.settings import DATABASE_PATH
from data.interfaces import Candle

logger = logging.getLogger("core.data.database")

class Database:
    """
    SQLite Database Manager.
    Handles persistent connection and schema initialization.
    """
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(Database, cls).__new__(cls)
        return cls._instance

    def __init__(self, db_path: Path = DATABASE_PATH):
        # Singleton init check
        if hasattr(self, 'initialized'): return
        
        self.db_path = db_path
        self._ensure_db_dir()
        
        # Persistent Connection
        # check_same_thread=False allows using connection across threads (e.g. Scanning vs Main Loop)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row # Return dict-like rows by default
        
        self._init_schema()
        self.initialized = True
        logger.info(f"Database connected at {self.db_path}")

    def _ensure_db_dir(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
    
    def is_connected(self) -> bool:
        """Check if database connection is alive."""
        try:
            if self.conn is None:
                return False
            # Try a simple query to verify connection
            self.conn.execute("SELECT 1")
            return True
        except (sqlite3.ProgrammingError, sqlite3.OperationalError):
            return False
    
    def _ensure_connection(self):
        """Ensure database connection is alive, reconnect if needed."""
        if not self.is_connected():
            logger.warning("Database connection lost, attempting to reconnect...")
            try:
                # Close old connection if it exists
                if self.conn:
                    try:
                        self.conn.close()
                    except:
                        pass
                
                # Reconnect
                self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
                self.conn.row_factory = sqlite3.Row
                logger.info("Database reconnected successfully")
            except Exception as e:
                logger.error(f"Failed to reconnect to database: {e}")
                raise
        
    def get_connection(self) -> sqlite3.Connection:
        """Returns the persistent connection, ensuring it's alive."""
        self._ensure_connection()
        return self.conn
    
    def close(self):
        """Explicitly close the connection."""
        if self.conn:
            try:
                self.conn.close()
                self.conn = None
                logger.info("Database connection closed.")
            except Exception as e:
                logger.error(f"Error closing database connection: {e}")
    
    def _init_schema(self):
        """Initialize the database schema if it doesn't exist."""
        cursor = self.conn.cursor()
        
        try:
            # 1. Continuous Data (OHLCV)
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
            cursor.execute('''
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
            
            # 2. Signals
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME NOT NULL,
                symbol TEXT NOT NULL,
                signal_type TEXT NOT NULL,
                strength REAL,
                status TEXT DEFAULT 'NEW',
                metadata TEXT
            )
            ''')
            
            # 3. Trades
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
                status TEXT
            )
            ''')

            # 4. Alerts
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME NOT NULL,
                symbol TEXT NOT NULL,
                signal_type TEXT NOT NULL,
                price REAL NOT NULL,
                quantity REAL, -- New field for Position Size
                
                -- Targets
                sl_price REAL,
                tp1_price REAL,
                tp2_price REAL,
                tp3_price REAL,
                
                -- Context
                atr REAL,
                adx REAL,
                rsi REAL,
                
                status TEXT DEFAULT 'SENT',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                snapshot_data TEXT
            )
            ''')
            
            try:
                cursor.execute('ALTER TABLE alerts ADD COLUMN snapshot_data TEXT')
            except sqlite3.OperationalError:
                pass

            try:
                cursor.execute('ALTER TABLE alerts ADD COLUMN quantity REAL')
            except sqlite3.OperationalError:
                pass
            
            # 5. Alert Performance
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS alert_performance (
                alert_id INTEGER PRIMARY KEY,
                triggered BOOLEAN DEFAULT 0,
                entry_time DATETIME,
                entry_price REAL,
                
                outcome TEXT,
                pnl_r_multiple REAL,
                pnl_amount REAL,
                duration_minutes REAL,
                
                max_favorable_excursion REAL,
                max_adverse_excursion REAL,
                
                closed_at DATETIME,
                FOREIGN KEY(alert_id) REFERENCES alerts(id)
            )
            ''')

            try:
                cursor.execute('ALTER TABLE alert_performance ADD COLUMN pnl_amount REAL')
                cursor.execute('ALTER TABLE alert_performance ADD COLUMN duration_minutes REAL')
            except sqlite3.OperationalError:
                pass
            
            # 6. Indices (Performance)
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_market_data_lookup ON market_data (symbol, timeframe, timestamp)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_indicators_lookup ON indicators (symbol, timeframe, timestamp)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_market_data_ts ON market_data (timestamp)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_indicators_ts ON indicators (timestamp)')
            
            self.conn.commit()
            logger.info("Database schema and indices initialized.")
            
        except Exception as e:
            logger.error(f"Failed to init schema: {e}")
            raise
        # DO NOT CLOSE CONN HERE

    def save_candle(self, symbol: str, timeframe: str, candle: Candle, is_filled: bool = False):
        """Save a single candle."""
        try:
            self._ensure_connection()
            self.conn.execute('''
            INSERT OR REPLACE INTO market_data 
            (feature_id, symbol, timeframe, timestamp, open, high, low, close, volume, is_filled)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                f"{symbol}_{timeframe}_{candle.timestamp.isoformat()}",
                symbol, timeframe, candle.timestamp,
                candle.open, candle.high, candle.low, candle.close, candle.volume, is_filled
            ))
            self.conn.commit()
        except Exception as e:
            logger.error(f"Error saving candle: {e}")
        # DO NOT CLOSE

    def save_bulk_candles(self, symbol: str, timeframe: str, candles: List[Candle], is_filled_list: List[bool] = None, source: str = "YFINANCE"):
        """Save multiple candles efficiently."""
        try:
            # Ensure connection is alive before saving
            self._ensure_connection()
            
            if is_filled_list is None:
                is_filled_list = [False] * len(candles)
                
            data = [
                (
                    f"{symbol}_{timeframe}_{c.timestamp.isoformat()}",
                    symbol, timeframe, c.timestamp.isoformat(),
                    c.open, c.high, c.low, c.close, c.volume, source, filled
                )
                for c, filled in zip(candles, is_filled_list)
            ]
            
            self.conn.executemany('''
            INSERT OR REPLACE INTO market_data 
            (feature_id, symbol, timeframe, timestamp, open, high, low, close, volume, source, is_filled)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', data)
            self.conn.commit()
            logger.info(f"Saved {len(candles)} candles for {symbol}")
        except Exception as e:
            logger.error(f"Error saving bulk candles: {e}")

    def save_indicators(self, symbol: str, timeframe: str, df: pd.DataFrame):
        """Save calculated indicators to DB."""
        try:
            self._ensure_connection()
            data = []
            for idx, row in df.iterrows():
                ts = idx.to_pydatetime()
                fid = f"{symbol}_{timeframe}_{ts.isoformat()}"
                
                rsi = row.get('RSI')
                bbu = row.get('BB_Upper')
                bbm = row.get('BB_Middle')
                bbl = row.get('BB_Lower')
                adx = row.get('ADX')
                atr = row.get('ATR')
                vwap = row.get('VWAP')
                sma50 = row.get('SMA_50')
                vsma20 = row.get('Volume_SMA_20')
                
                def to_val(v): return None if pd.isna(v) else float(v)
                
                data.append((
                    fid, symbol, timeframe, ts.isoformat(),
                    to_val(rsi), to_val(bbu), to_val(bbm), to_val(bbl),
                    to_val(adx), to_val(atr), to_val(vwap), to_val(sma50), to_val(vsma20)
                ))
            
            self.conn.executemany('''
            INSERT OR REPLACE INTO indicators 
            (feature_id, symbol, timeframe, timestamp, rsi, bb_upper, bb_middle, bb_lower, adx, atr, vwap, sma_50, volume_sma_20)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', data)
            self.conn.commit()
            logger.info(f"Saved {len(data)} indicator rows for {symbol}")
            
        except Exception as e:
            logger.error(f"Error saving indicators: {e}")

    def load_market_data(self, symbol: str, timeframe: str) -> pd.DataFrame:
        """Load market data as DataFrame."""
        try:
            self._ensure_connection()
            query = """
                SELECT timestamp, open, high, low, close, volume, is_filled 
                FROM market_data 
                WHERE symbol = ? AND timeframe = ? 
                ORDER BY timestamp ASC
            """
            df = pd.read_sql_query(query, self.conn, params=(symbol, timeframe))
            if not df.empty:
                df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True, format='mixed')
                df.set_index('timestamp', inplace=True)
                
                if df.index.duplicated().any():
                    # Check duplication logic?
                    df = df[~df.index.duplicated(keep='last')]
                
                df.rename(columns={
                    'open': 'Open',
                    'high': 'High',
                    'low': 'Low',
                    'close': 'Close',
                    'volume': 'Volume'
                }, inplace=True)
            return df
        except Exception as e:
            logger.error(f"Error loading market data {symbol} {timeframe}: {e}")
            return pd.DataFrame()

    def load_indicators(self, symbol: str, timeframe: str) -> pd.DataFrame:
        """Load indicators as DataFrame."""
        try:
            self._ensure_connection()
            query = """
                SELECT timestamp, rsi, bb_upper, bb_middle, bb_lower, adx, atr, vwap, sma_50, volume_sma_20 
                FROM indicators 
                WHERE symbol = ? AND timeframe = ? 
                ORDER BY timestamp ASC
            """
            df = pd.read_sql_query(query, self.conn, params=(symbol, timeframe))
            if not df.empty:
                df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True, format='mixed')
            
            rename_map = {
                'rsi': 'RSI',
                'bb_upper': 'BB_Upper',
                'bb_middle': 'BB_Middle',
                'bb_lower': 'BB_Lower',
                'adx': 'ADX',
                'atr': 'ATR',
                'vwap': 'VWAP',
                'sma_50': 'SMA_50',
                'volume_sma_20': 'Volume_SMA_20'
            }
            df.rename(columns=rename_map, inplace=True)
            
            if not df.empty:
                df.set_index('timestamp', inplace=True)
            return df
        except Exception as e:
            logger.error(f"Error loading indicators {symbol} {timeframe}: {e}")
            return pd.DataFrame()

    def save_alert(self, signal, plan, snapshot_data: str = None):
        """Persists a generated alert with its trade plan targets."""
        try:
            tp1, tp2, tp3 = None, None, None
            
            for tp in plan.take_profits:
                if tp.tag == "TP1": tp1 = tp.price
                elif tp.tag == "TP2": tp2 = tp.price
                elif tp.tag == "TP3": tp3 = tp.price

            atr = signal.atr_value
            adx = signal.metadata.get('adx')
            rsi = signal.metadata.get('rsi')
            
            qty = getattr(plan, 'total_size', 0)

            self.conn.execute('''
            INSERT INTO alerts (
                timestamp, symbol, signal_type, price, quantity,
                sl_price, tp1_price, tp2_price, tp3_price,
                atr, adx, rsi, status, snapshot_data
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                signal.timestamp.isoformat() if hasattr(signal.timestamp, 'isoformat') else str(signal.timestamp),
                signal.symbol,
                signal.type.value if hasattr(signal.type, 'value') else str(signal.type),
                signal.price,
                qty,
                plan.stop_loss_price,
                tp1, tp2, tp3,
                atr, adx, rsi,
                'SENT',
                snapshot_data
            ))
            self.conn.commit()
            logger.info(f"Alert saved to DB for {signal.symbol} (Qty: {qty})")
        except Exception as e:
            logger.error(f"Failed to save alert for {signal.symbol}: {e}")

    def get_active_alerts(self) -> List[Dict]:
        """Returns all alerts that are currently SENT (active)."""
        try:
            cursor = self.conn.cursor()
            cursor.execute('SELECT * FROM alerts WHERE status = "SENT"')
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error fetching active alerts: {e}")
            return []

    def update_alert_performance(self, alert_id: int, outcome: str, pnl_r: float, exit_price: float, exit_time: datetime, pnl_amount: float = 0.0, duration_minutes: float = 0.0):
        """Updates or inserts performance record and closes the alert."""
        try:
            self.conn.execute('UPDATE alerts SET status = "CLOSED" WHERE id = ?', (alert_id,))
            
            self.conn.execute('''
            INSERT OR REPLACE INTO alert_performance 
            (alert_id, triggered, outcome, pnl_r_multiple, pnl_amount, duration_minutes, entry_price, closed_at)
            VALUES (?, ?, ?, ?, ?, ?, (SELECT price FROM alerts WHERE id = ?), ?)
            ''', (
                alert_id, 1, outcome, pnl_r, pnl_amount, duration_minutes, alert_id, exit_time.isoformat()
            ))
            
            self.conn.commit()
            logger.info(f"Updated performance for alert {alert_id}: {outcome} ({pnl_r:.2f}R)")
        except Exception as e:
            logger.error(f"Error updating alert performance {alert_id}: {e}")

    def signal_exists(self, symbol: str, timestamp: datetime) -> bool:
        """
        Checks if an alert already exists for this symbol and candle timestamp.
        Used to prevent duplicate signals (spam) for the same candle.
        """
        try:
            ts_str = timestamp.isoformat() if hasattr(timestamp, 'isoformat') else str(timestamp)
            cursor = self.conn.cursor()
            cursor.execute('SELECT 1 FROM alerts WHERE symbol = ? AND timestamp = ?', (symbol, ts_str))
            return cursor.fetchone() is not None
        except Exception as e:
            logger.error(f"Error checking signal existence: {e}")
            return False
