import pandas as pd
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict

from config.settings import DATA_CONFIG, STRATEGY_CONFIG
from data.storage.database import Database
from data.providers.yfinance_provider import YFinanceProvider
from data.providers.polygon_provider import PolygonProvider
from data.providers.twelve_provider import TwelveDataProvider
from data.providers.alphavantage_provider import AlphaVantageProvider
from data.quality.gap_detector import GapDetector
from data.interfaces import Candle
from data.utils.rate_limiter import get_rate_limiter

# Lazy import to avoid circular dependency if any
# from analysis.indicators import Indicators # Assuming this exists or we use TA-Lib wrapper

logger = logging.getLogger("core.data.manager")

class DataManager:
    """
    Orchestrates Data Flow:
    Provider -> Quality Check -> Storage -> Analysis
    """
    
    def __init__(self):
        self.db = Database()
        self.gap_detector = GapDetector(expected_interval_minutes=60) # 1H
        self.rate_limiter = get_rate_limiter()
        
        # Initialize Providers
        self.providers = [
            PolygonProvider(),
            TwelveDataProvider(),
            AlphaVantageProvider(),
            YFinanceProvider()
        ]
        # Sort by priority
        self.providers.sort(key=lambda x: x.priority)
        
        # Cache for simple access? 
        # Better to hit DB for reliability in this architecture.
        
    def get_latest_data(self, symbol: str, days: int = 60) -> pd.DataFrame:
        """
        Get data for analysis from DB.
        """
        # We assume data is already in DB (synced via update_data)
        # But we verify fresh data if needed?
        # For simplicity, we read DB.
        
        # Logic: 
        # 1. Load from DB.
        # 2. If empty or old, trigger fetch.
        
        # Try loading again
        df = self.db.load_market_data(symbol, "1h")
        
        if df.empty:
            logger.info(f"No local data for {symbol}, initializing fetch...")
            # If load from DB fails (e.g. save failed), we might want to return 
            # the fetched data directly if we had it. 
            # But update_data returns None.
            # Let's modify update_data to optionally return the DF?
            # Or just trigger update and re-load.
            self.update_data(symbol)
            df = self.db.load_market_data(symbol, "1h")
            
        return df

    def update_data(self, symbol: str):
        """
        Fetches latest data from Provider and updates DB.
        """
        # logger.info(f"Updating data for {symbol}...") # Too verbose
        logger.debug(f"Checking data update for {symbol}...")
        
        # 1. Fetch
        # Default to BACKFILL_DAYS if empty, or small window if updating.
        # Logic: Find last DB timestamp.
        
        last_ts = self._get_last_timestamp(symbol)
        
        start_date = None
        days_back = DATA_CONFIG['HISTORY_DAYS']
        
        if last_ts:
            # Fetch from last known to now
            # YFinance expects string or datetime.
            # Add a buffer
            start_date = (last_ts - timedelta(hours=24)).strftime('%Y-%m-%d')
            days_back = 0 # Use explicit dates
            
        
        df_new = None
        source_name = "UNKNOWN"
        for provider in self.providers:
            try:
                # Apply rate limiting before making API call
                self.rate_limiter.wait_if_needed(provider.name)
                
                df_new = provider.fetch_data(
                    symbol, 
                    "1h", 
                    start_date=start_date, 
                    days_back=days_back if not start_date else 0
                )
                if df_new is not None and not df_new.empty:
                    source_name = provider.name
                    logger.info(f"Successfully fetched 1h data for {symbol} using {source_name}")
                    break
            except Exception as e:
                logger.warning(f"Provider {provider.name} failed for {symbol}: {e}")
                continue
        
        if df_new is None or df_new.empty:
            logger.warning(f"No new data fetched for {symbol}")
            return
            
        # 2. Save
        candles = []
        for ts, row in df_new.iterrows():
            c = Candle(
                timestamp=ts,
                open=row['Open'],
                high=row['High'],
                low=row['Low'],
                close=row['Close'],
                volume=row['Volume']
            )
            candles.append(c)
            
        self.db.save_bulk_candles(symbol, "1h", candles, source=source_name)
        logger.info(f"Stored {len(candles)} candles for {symbol} from {source_name}")

    def get_latest_daily_data(self, symbol: str, days: int = 730) -> pd.DataFrame:
        """
        Get daily data for analysis (Trend Filter).
        """
        df = self.db.load_market_data(symbol, "1d")
        
        if df.empty:
            logger.info(f"No local DAILY data for {symbol}, initializing fetch...")
            self.update_daily_data(symbol)
            df = self.db.load_market_data(symbol, "1d")
            
        return df

    def update_daily_data(self, symbol: str):
        """
        Fetches latest DAILY data from Provider and updates DB.
        """
        # logger.info(f"Updating DAILY data for {symbol}...") # Too verbose
        logger.debug(f"Checking DAILY data update for {symbol}...")
        
        # Logic: Find last DB timestamp for DAILY
        # We need a way to check last Daily timestamp.
        # Assuming load_market_data works for "1d", we can just check max index.
        df_old = self.db.load_market_data(symbol, "1d")
        last_ts = df_old.index.max().to_pydatetime() if not df_old.empty else None
        
        start_date = None
        days_back = 365 * 2 # 2 Years history for daily
        
        if last_ts:
            start_date = (last_ts - timedelta(days=1)).strftime('%Y-%m-%d')
            days_back = 0
            
        df_new = None
        source_name = "UNKNOWN"
        for provider in self.providers:
            try:
                # Apply rate limiting before making API call
                self.rate_limiter.wait_if_needed(provider.name)
                
                df_new = provider.fetch_data(
                    symbol, 
                    "1d", 
                    start_date=start_date, 
                    days_back=days_back if not start_date else 0
                )
                if df_new is not None and not df_new.empty:
                    source_name = provider.name
                    logger.info(f"Successfully fetched DAILY data for {symbol} using {source_name}")
                    break
            except Exception as e:
                logger.warning(f"Provider {provider.name} failed for {symbol}: {e}")
                continue
        
        if df_new is None or df_new.empty:
            logger.warning(f"No new DAILY data fetched for {symbol}")
            return
            
        # Save
        candles = []
        for ts, row in df_new.iterrows():
            c = Candle(
                timestamp=ts,
                open=row['Open'],
                high=row['High'],
                low=row['Low'],
                close=row['Close'],
                volume=row['Volume']
            )
            candles.append(c)
            
        self.db.save_bulk_candles(symbol, "1d", candles, source=source_name)
        logger.info(f"Stored {len(candles)} DAILY candles for {symbol} from {source_name}")

        
    def resolve_gaps(self, symbol: str):
        """
        Checks for gaps and fills them (Forward Fill).
        """
        df = self.db.load_market_data(symbol, "1h")
        if df.empty:
            return
            
        gaps = self.gap_detector.detect_gaps(df, symbol)
        
        if not gaps:
            logger.info(f"No gaps detected for {symbol}.")
            return
            
        logger.info(f"Found {len(gaps)} gaps for {symbol}. Filling...")
        
        filled_candles = []
        
        for gap in gaps:
            if not gap.is_fillable:
                # Downgrade to INFO to reduce noise for expected gaps (e.g. weekends/holidays)
                logger.info(f"Gap too large to fill safely (likely weekend/holiday): {gap.duration_minutes:.1f} min at {gap.start_time}")
                continue
                
            # Logic: Forward Fill
            # Create candles every hour between start and end.
            # Use 'gap_start' close price for all OHL.
            
            # Find the candle BEFORE the gap to get values
            try:
                # Assuming index is unique
                start_val = df.loc[gap.start_time] # This exists
                
                # Robust extraction in case of remaining duplicates
                if isinstance(start_val, pd.DataFrame):
                    start_val = start_val.iloc[-1]
                
                fill_price = float(start_val['Close'])
                fill_vol = 0 # No volume on filled candles
                
                # Iterate hours
                curr = gap.start_time + timedelta(hours=1)
                while curr < gap.end_time:
                    # Don't overwrite existing?
                    # Gaps are by definition missing rows.
                    
                    c = Candle(
                        timestamp=curr,
                        open=fill_price,
                        high=fill_price,
                        low=fill_price,
                        close=fill_price,
                        volume=fill_vol
                    )
                    filled_candles.append(c)
                    curr += timedelta(hours=1)
                    
            except KeyError:
                logger.error(f"Could not find start candle for gap at {gap.start_time}")
                continue
                
        if filled_candles:
            self.db.save_bulk_candles(symbol, "1h", filled_candles, is_filled_list=[True]*len(filled_candles))
            logger.info(f"Filled {len(filled_candles)} missing hours for {symbol}")

    def _get_last_timestamp(self, symbol: str) -> Optional[datetime]:
        # Simple query to DB or loading DF
        # Optimize later with SQL `SELECT MAX(timestamp)...`
        # Current DB implementation only has `load_market_data`.
        # We'll stick to loading DF for now (cache issue?)
        # For performance, adding `get_last_timestamp` to DB is better.
        # But let's use what we have.
        df = self.db.load_market_data(symbol, "1h")
        if not df.empty:
            return df.index.max().to_pydatetime()
        return None
