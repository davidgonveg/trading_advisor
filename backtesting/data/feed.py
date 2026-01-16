import pandas as pd
from typing import List, Dict, Iterator
from datetime import datetime
import logging

from .schema import DataFeed, BarData, Candle
from .validator import GapValidator, DataValidationException
from data.storage.database import Database # Importing from main project

logger = logging.getLogger("backtesting.data.feed")

class DatabaseFeed(DataFeed):
    def __init__(self, db: Database, symbols: List[str], start_date: datetime, end_date: datetime):
        self.db = db
        self._symbols = symbols
        self.start = start_date
        self.end = end_date
        self.validator = GapValidator()
        
        # Preloaded Data (Memory limit? For 20 tickets 1H 2 years, it fits in RAM easily)
        self.data_store: Dict[str, pd.DataFrame] = {} 
        self.daily_data_store: Dict[str, pd.DataFrame] = {}
        
        self.load_data()
        
    @property
    def symbols(self) -> List[str]:
        return self._symbols
        
    def load_data(self):
        """Loads and Validates data from DB"""
        logger.info("Loading backtest data...")
        for sym in self._symbols:
            # Load 1H
            df_1h = self.db.load_market_data(sym, "1h") # Need to filter by date? schema.py doesn't do filtering yet
            # Filter range
            if not df_1h.empty:
                df_1h = df_1h[(df_1h.index >= self.start) & (df_1h.index <= self.end)]
                
            # Validate
            try:
                self.validator.validate_continuity(df_1h, sym)
            except DataValidationException as e:
                logger.error(f"Validation FAILED for {sym}: {e}")
                raise e
                
            self.data_store[sym] = df_1h
            
            # Load 1D (For Trend Filter)
            df_1d = self.db.load_market_data(sym, "1d")
            
            # Pre-calculate Daily Indicators (SMA 50, SMA 200)
            if not df_1d.empty:
                df_1d['SMA_50'] = df_1d['Close'].rolling(window=50).mean()
                df_1d['SMA_200'] = df_1d['Close'].rolling(window=200).mean() # v3.1
            
            self.daily_data_store[sym] = df_1d

    def __iter__(self) -> Iterator[BarData]:
        """
        Yields BarData events step-by-step.
        Synchronizes all symbols.
        """
        # 1. Union of all indices to create Master Timeline
        indices = [df.index for df in self.data_store.values() if not df.empty]
        if not indices:
            return
            
        from functools import reduce
        master_timeline = reduce(lambda x, y: x.union(y), indices).sort_values().unique()
        
        logger.info(f"Starting Feed. Steps: {len(master_timeline)}")
        
        for ts in master_timeline:
            current_bars = {}
            current_daily = {}
            current_daily_indicators = {}
            
            for sym in self._symbols:
                # 1H Candle
                if ts in self.data_store[sym].index:
                    row = self.data_store[sym].loc[ts]
                    current_bars[sym] = Candle(
                        timestamp=ts,
                        symbol=sym,
                        open=row['Open'],
                        high=row['High'],
                        low=row['Low'],
                        close=row['Close'],
                        volume=row['Volume']
                    )
                
                # Daily Candle (Lookback)
                daily_df = self.daily_data_store.get(sym)
                if daily_df is not None and not daily_df.empty:
                    # Efficient lookup:
                    idx_pos = daily_df.index.searchsorted(ts) 
                    if idx_pos > 0:
                        prev_row = daily_df.iloc[idx_pos - 1]
                        prev_ts = daily_df.index[idx_pos -1]
                        
                        current_daily[sym] = Candle(
                            timestamp=prev_ts,
                            symbol=sym,
                            open=prev_row['Open'],
                            high=prev_row['High'],
                            low=prev_row['Low'],
                            close=prev_row['Close'],
                            volume=prev_row['Volume']
                        )
                        
                        # Populate Daily Indicators
                        current_daily_indicators[sym] = {
                            'SMA_50': prev_row['SMA_50'] if not pd.isna(prev_row['SMA_50']) else 0.0,
                            'SMA_200': prev_row['SMA_200'] if not pd.isna(prev_row['SMA_200']) else 0.0
                        }
            
            yield BarData(timestamp=ts, 
                          bars=current_bars, 
                          daily_bars=current_daily,
                          daily_indicators=current_daily_indicators)
