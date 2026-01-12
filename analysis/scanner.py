import pandas as pd
import logging
from datetime import datetime
from typing import List, Optional

from config.settings import STRATEGY_CONFIG
from analysis.signal import Signal, SignalType, SignalStatus
from analysis.patterns import PatternRecognizer

logger = logging.getLogger("core.analysis.scanner")

class Scanner:
    """
    Main Strategy Logic Engine (Mean Reversion Selectiva).
    """

    def __init__(self):
        self.pattern_recognizer = PatternRecognizer()
        self.cfg = STRATEGY_CONFIG

    def find_signals(self, 
                     df_hourly: pd.DataFrame, 
                     symbol: str) -> List[Signal]:
        """
        Scans a dataframe (Hourly) for entry signals.
        Expects df_hourly to already include technical indicators columns:
        [RSI, BB_Lower, BB_Upper, ADX, SMA_50, Volume_SMA_20, etc.]
        """
        signals = []
        
        if df_hourly.empty:
            return signals

        # We typically scan the *last* closed candle, or iterate over history for backtest.
        # For this implementation, we'll scan the entire DF (vectorized or iterative).
        # Iterative is easier for complex logic (multi-step).
        # Vectorized is faster. Given "Selectiva" (few trades), iterative on recent data is fine.
        # For Backtesting, we loop.
        
        # We need to detect patterns first
        df = self.pattern_recognizer.detect_patterns(df_hourly)
        
        # Iterate to check conditions
        # To avoid re-scanning old data in live mode, caller handles slicing.
        # Here we scan ALL rows provided.
        
        for idx, row in df.iterrows():
            try:
                # SKIP if any required indicator is NaN
                if pd.isna(row['RSI']) or pd.isna(row['SMA_50']) or pd.isna(row['ADX']):
                    continue
                    
                # 1. Common Conditions
                
                # ADX Check (Market must be ranging < 22)
                if row['ADX'] >= self.cfg['ADX_MAX_THRESHOLD']:
                    continue
                    
                # Volume Check (Volume > SMA20)
                # If volume is somehow 0 or nan, skip
                if row['Volume'] <= row.get('Volume_SMA_20', 0):
                    continue

                # 2. LONG Logic
                # - RSI < 35
                # - RSI turned up (Current > Prev) -> Requires looking at prev row
                # - Price <= BB Lower
                # - Price < VWAP
                # - Price > SMA 50 (Daily Trend)
                # - Bullish Pattern
                
                # We need previous row for RSI turn.
                # Locating prev row by integer location is easiest if index is unique & sorted.
                # Using shift() on DF beforehand is better for vectorized, 
                # but inside iterrows we need integer index.
                # Let's rely on caller or use simple tracking.
                
                # Optimization: Check static levels first
                is_long_candidate = (
                    row['RSI'] < self.cfg['RSI_OVERSOLD'] and
                    row['Close'] <= row['BB_Lower'] and
                    row['Close'] < row.get('VWAP', 999999) and
                    row['Close'] > row['SMA_50']
                )
                
                is_short_candidate = (
                    row['RSI'] > self.cfg['RSI_OVERBOUGHT'] and
                    row['Close'] >= row['BB_Upper'] and
                    row['Close'] > row.get('VWAP', 0) and
                    row['Close'] < row['SMA_50']
                )
                
                if not (is_long_candidate or is_short_candidate):
                    continue
                    
                # Get Previous Row safely
                # Assuming index is Timestamp.
                # We can't easily get 'prev' in iterrows without an integer counter or lookup.
                # Let's assume we can peek back if we convert to list or use iloc loop outside.
                # Re-design: Loop by integer index.
                pass 
                
            except KeyError as e:
                logger.warning(f"Missing column in scanner data: {e}")
                continue

        # Re-implementation with Index Looping for lookback
        timestamps = df.index
        for i in range(1, len(df)):
            current = df.iloc[i]
            prev = df.iloc[i-1]
            
            # Common Filtering (Performance Opt)
            if current['ADX'] >= self.cfg['ADX_MAX_THRESHOLD']:
                continue
                
            if current['Volume'] <= current.get('Volume_SMA_20', 0):
                continue

            # --- LONG ---
            if (current['RSI'] < self.cfg['RSI_OVERSOLD'] and
                current['RSI'] > prev['RSI'] and # Turn Up
                current['Close'] <= current['BB_Lower'] and
                current['Close'] < current.get('VWAP', float('inf')) and
                current['Close'] > current['SMA_50']):
                
                # Pattern Check
                if self.pattern_recognizer.check_bullish_reversal(current):
                    # Found Signal
                    sig = Signal(
                        symbol=symbol,
                        timestamp=timestamps[i],
                        type=SignalType.LONG,
                        price=current['Close'],
                        atr_value=current['ATR'],
                        metadata={
                            "rsi": current['RSI'],
                            "adx": current['ADX'],
                            "bb_lower": current['BB_Lower'],
                            "sma_50": current['SMA_50']
                        }
                    )
                    signals.append(sig)
                    continue # One signal per candle max (mutually exclusive usually)

            # --- SHORT ---
            if (current['RSI'] > self.cfg['RSI_OVERBOUGHT'] and
                current['RSI'] < prev['RSI'] and # Turn Down
                current['Close'] >= current['BB_Upper'] and
                current['Close'] > current.get('VWAP', 0) and
                current['Close'] < current['SMA_50']):
                
                # Pattern Check
                if self.pattern_recognizer.check_bearish_reversal(current):
                    # Found Signal
                    sig = Signal(
                        symbol=symbol,
                        timestamp=timestamps[i],
                        type=SignalType.SHORT,
                        price=current['Close'],
                        atr_value=current['ATR'],
                        metadata={
                            "rsi": current['RSI'],
                            "adx": current['ADX'],
                            "bb_upper": current['BB_Upper'],
                            "sma_50": current['SMA_50']
                        }
                    )
                    signals.append(sig)

        return signals
