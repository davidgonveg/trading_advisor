import pandas as pd
from typing import List, Dict, Iterator
from datetime import datetime
import logging

from .schema import DataFeed, BarData, Candle
from .validator import GapValidator, DataValidationException
from data.storage.database import Database # Importing from main project

from analysis.indicators import TechnicalIndicators
from analysis.patterns import PatternRecognizer

logger = logging.getLogger("backtesting.data.feed")

class DatabaseFeed(DataFeed):
    def __init__(self, db: Database, symbols: List[str], start_date: datetime, end_date: datetime):
        self.db = db
        self._symbols = symbols
        self.start = start_date
        self.end = end_date
        self.validator = GapValidator()
        self.calculator = TechnicalIndicators()
        self.pattern_recognizer = PatternRecognizer()
        
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
            df_full = self.db.load_market_data(sym, "1h") 
            
            if df_full.empty:
                logger.warning(f"No data found in DB for {sym}")
                self.data_store[sym] = pd.DataFrame()
                continue

            # Ensure sorted and unique index
            df_full = df_full.sort_index()
            df_full = df_full[~df_full.index.duplicated(keep='first')]

            # 1. Identify Target Range with Warm-up Buffer
            # We need ~100 periods of buffer for SMA200, ATR14, VolumeSMA20, etc.
            # searchsorted is robust for sorted indices
            start_pos = df_full.index.searchsorted(self.start)
            warmup_pos = max(0, start_pos - 100)
            
            # Slice from warm-up to end
            df_slice = df_full.iloc[warmup_pos:].copy()
            df_slice = df_slice[df_slice.index <= self.end]
            
            # 2. Calculate Indicators (using buffered data)
            if not df_slice.empty:
                logger.info(f"Pre-calculating indicators for {sym} (with warm-up)...")
                df_slice = self.calculator.calculate_all(df_slice)
                
                # Pre-calculate Patterns
                logger.info(f"Pre-calculating patterns for {sym}...")
                df_slice = self.pattern_recognizer.detect_patterns(df_slice)
                
                # 3. Final Slice to exact backtest range
                df_final = df_slice[df_slice.index >= self.start]
                self.data_store[sym] = df_final
            else:
                self.data_store[sym] = pd.DataFrame()
            
            # Load 1D (For Trend Filter)
            df_1d = self.db.load_market_data(sym, "1d")
            
            # Pre-calculate Daily Indicators (SMA 50, SMA 200)
            if not df_1d.empty:
                df_1d['SMA_50'] = df_1d['Close'].rolling(window=50).mean()
                df_1d['SMA_200'] = df_1d['Close'].rolling(window=200).mean() # v3.1
            
            self.daily_data_store[sym] = df_1d
            
        # Create Master Timeline
        indices = [df.index for df in self.data_store.values() if not df.empty]
        if indices:
            from functools import reduce
            self.timeline = reduce(lambda x, y: x.union(y), indices).sort_values().unique()
        else:
            self.timeline = []
            
    def __len__(self):
        return len(self.timeline)

    def __iter__(self) -> Iterator[BarData]:
        """
        Yields BarData events step-by-step.
        Synchronizes all symbols.
        """
        if len(self.timeline) == 0:
            return
            
        logger.info(f"Starting Feed. Steps: {len(self.timeline)}")
        
        # Identify indicator columns (non-OHLCV)
        # We assume they are consistent across symbols roughly, but we can check per row
        ohlcv = {'Open', 'High', 'Low', 'Close', 'Volume'}
        
        for ts in self.timeline:
            current_bars = {}
            current_daily = {}
            current_daily_indicators = {}
            
            for sym in self._symbols:
                # 1H Candle
                if ts in self.data_store[sym].index:
                    row = self.data_store[sym].loc[ts]
                    
                    # Extract Indicators
                    # Optimization: Convert all non-OHLCV cols to dict
                    # Note: row is a Series. to_dict() includes everything.
                    full_dict = row.to_dict()
                    indicators = {k: v for k, v in full_dict.items() if k not in ohlcv}
                    
                    current_bars[sym] = Candle(
                        timestamp=ts,
                        symbol=sym,
                        open=row['Open'],
                        high=row['High'],
                        low=row['Low'],
                        close=row['Close'],
                        volume=row['Volume'],
                        indicators=indicators
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
