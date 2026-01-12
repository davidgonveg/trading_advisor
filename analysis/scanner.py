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
                     symbol: str, 
                     df_hourly: pd.DataFrame, 
                     df_daily: pd.DataFrame = None,
                     scan_latest: bool = False) -> List[Signal]:
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
        
        # DEBUG: Check for duplicate columns
        # print(f"Scanner scanning {symbol}. Columns: {df.columns.tolist()}")
        if len(df.columns) != len(set(df.columns)):
            logger.error(f"DUPLICATE COLUMNS DETECTED for {symbol}: {df.columns.tolist()}")
            # Determine which are dupes
            from collections import Counter
            counts = Counter(df.columns)
            dupes = [k for k, v in counts.items() if v > 1]
            logger.error(f"Dupes: {dupes}")
            
        for idx, row in df.iterrows():
            try:
                try:
                    # SKIP if any required indicator is NaN
                    if pd.isna(row['RSI']) or pd.isna(row['SMA_50']) or pd.isna(row['ADX']):
                        continue
                except ValueError:
                    logger.error(f"CRASH IN ROW CHECK at {idx}")
                    logger.error(f"Row Index: {row.index}")
                    logger.error(f"RSI: {row['RSI']} Type: {type(row['RSI'])}")
                    logger.error(f"SMA_50: {row['SMA_50']} Type: {type(row['SMA_50'])}")
                    raise
                    
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
        
        # Decision Logger
        decision_logger = logging.getLogger("scanner_decisions")
        
        # Determine Loop Range
        # If scanning latest, we only check the last row.
        # We start at 1 because we need i-1 for previous values.
        if scan_latest:
            start_idx = len(df) - 1
            if start_idx < 1: # Need at least 2 rows
                return signals
        else:
            start_idx = 1
            
        # --- PREPARE DAILY SMA LOOKUP ---
        # Strategy requires comparing price to Daily SMA 50.
        # We need to map each Hourly timestamp to the RELEVANT Daily SMA (Prior Day Close).
        
        daily_sma_series = None
        if df_daily is not None and not df_daily.empty:
            # 1. Calc SMA 50 if not present
            if 'SMA_50' not in df_daily.columns:
                # We do a quick calc here to avoid dependency circularity or use simple rolling
                daily_sma_series = df_daily['Close'].rolling(window=50).mean()
            else:
                daily_sma_series = df_daily['SMA_50']
                
            # 2. Reindex to match hourly timestamps (Forward Fill)
            # This is tricky: For 10:00 AM today, we want YESTERDAY's SMA? 
            # Or Today's (LIVE) SMA?
            # Strategy: "Tendencia macro". Usually prior close is safer (stable).
            # But standard indicators often use "Current Daily SMA" (updates tick by tick).
            # Given we are in "Scanner", let's use the LATEST AVAILABLE closed daily candle logic logic via reindex(method='ffill').
            # If df_daily index is dates (00:00), ffill will propagate yesterday's value until a new date appears.
            # However, if we run this at 15:00, and today's valid entry in df_daily is 00:00, we get today's open?
            # Let's assume df_daily has Date index.
            
            # Efficient Lookup:
            # Reindex daily series to hourly timestamps using ffill
            # This fills "Today 10am" with "Today 00:00" value? 
            # If "Today 00:00" represents the CLOSE of today (which it shouldn't if it's forming), 
            # standard daily data usually has Today's row updating.
            # Backtest data usually has Today's row FINALIZED. 
            # To avoid peek-ahead in backtest, we must shift daily data by 1 day?
            # i.e., at 2023-01-05, we see data of 2023-01-04.
            
            # SAFE APPROACH: Use shift(1) on daily data before reindexing.
            # This guarantees we only use fully closed prior candles.
            shifted_daily = daily_sma_series.shift(1)
            
            # Resample daily to hourly to match the hourly index
            # This creates a series aligned with scan timestamps
            # We reindex using 'ffill' to propagate the last daily value forward
            sma_reindexed = shifted_daily.reindex(df.index, method='ffill')
        else:
            if scan_latest: # Warn only if we are live
                logger.warning(f"No Daily Data provided for {symbol}. Falling back to Hourly SMA (Strategy Divergence!)")
            sma_reindexed = df.get('SMA_50', pd.Series([0]*len(df), index=df.index))
            
        for i in range(start_idx, len(df)):
            current = df.iloc[i]
            prev = df.iloc[i-1]
            ts = timestamps[i]
            
            # Get Daily SMA for this specific timestamp
            # If we failed to build reindexed, default to 0
            sma_50_val = sma_reindexed.iloc[i] if daily_sma_series is not None else current.get('SMA_50', 0)
            
            # --- FILTER CHECK ---
            # 1. ADX
            pass_adx = current['ADX'] < self.cfg['ADX_MAX_THRESHOLD']
            
            # 2. Volume
            pass_vol = current['Volume'] > current.get('Volume_SMA_20', 0)
            
            # 3. Long Inds
            pass_rsi_long = current['RSI'] < self.cfg['RSI_OVERSOLD']
            pass_rsiturn_long = current['RSI'] > prev['RSI']
            pass_bb_long = current['Close'] <= current['BB_Lower']
            # SMA Trend Filter (Daily) - Using hourly SMA50 as proxy if separate daily not passed, 
            # OR better: if 'SMA_50' in dataframe is actually required to be Daily SMA mapped to hourly.
            # Assuming 'SMA_50' column IS the daily 50SMA (mapped) as per Strategy requirements.
            pass_sma_long = current['Close'] > sma_50_val
            
            vwap_val = current.get('VWAP')
            if vwap_val is None: vwap_val = float('inf')
            pass_vwap_long = current['Close'] < vwap_val
            
            # 4. Short Inds
            pass_rsi_short = current['RSI'] > self.cfg['RSI_OVERBOUGHT']
            pass_rsiturn_short = current['RSI'] < prev['RSI']
            pass_bb_short = current['Close'] >= current['BB_Upper']
            pass_sma_short = current['Close'] < sma_50_val 
            
            vwap_val_short = current.get('VWAP')
            if vwap_val_short is None: vwap_val_short = 0
            pass_vwap_short = current['Close'] > vwap_val_short
            
            # Aggregates
            context_ok = pass_adx and pass_vol
            long_setup = pass_rsi_long and pass_rsiturn_long and pass_bb_long and pass_sma_long and pass_vwap_long
            short_setup = pass_rsi_short and pass_rsiturn_short and pass_bb_short and pass_sma_short and pass_vwap_short
            
            # Log Logic: Log if Context OK OR Indicators OK (Close calls)
            if context_ok or long_setup or short_setup:
                # Check Patterns
                has_bull_pat = self.pattern_recognizer.check_bullish_reversal(current)
                has_bear_pat = self.pattern_recognizer.check_bearish_reversal(current)
                
                # Detailed Log Line
                # Format: TIMESTAMP | SYM | TYPE | ADX:OK | VOL:OK | RSI:30(OK) | BB:OK | PAT:FAIL | DECISION:REJECTED
                
                # Determine "Potential Type"
                p_type = "LONG" if (long_setup or pass_rsi_long) else ("SHORT" if (short_setup or pass_rsi_short) else "NONE")
                
                msg = f"{ts} | {symbol} | {p_type} | ADX={current['ADX']:.1f}({'OK' if pass_adx else 'FAIL'}) | VOL={'OK' if pass_vol else 'FAIL'} | "
                
                if p_type == "LONG":
                    msg += f"RSI={current['RSI']:.1f}({'OK' if pass_rsi_long else 'FAIL'}) | BB={'OK' if pass_bb_long else 'FAIL'} | SMA={'OK' if pass_sma_long else 'FAIL'} | "
                    msg += f"PAT={'OK' if has_bull_pat else 'FAIL'}"
                    status = "ACCEPTED" if (context_ok and long_setup and has_bull_pat) else "REJECTED"
                elif p_type == "SHORT":
                     msg += f"RSI={current['RSI']:.1f}({'OK' if pass_rsi_short else 'FAIL'}) | BB={'OK' if pass_bb_short else 'FAIL'} | SMA={'OK' if pass_sma_short else 'FAIL'} | "
                     msg += f"PAT={'OK' if has_bear_pat else 'FAIL'}"
                     status = "ACCEPTED" if (context_ok and short_setup and has_bear_pat) else "REJECTED"
                else:
                    msg += "Inds=FAIL"
                    status = "REJECTED"
                    
                decision_logger.info(f"{msg} -> {status}")

            # --- LONG EXECUTION ---
            if context_ok and long_setup:
                # Pattern Check DISABLED by User Request
                # if self.pattern_recognizer.check_bullish_reversal(current):
                if True:
                    # DEBUG: Ensure Scalars
                    # import pandas as pd <-- Removed to avoid UnboundLocalError
                    vals_to_check = {
                        "Close": current['Close'],
                        "ATR": current['ATR'],
                        "RSI": current['RSI'],
                        "ADX": current['ADX']
                    }
                    for k, v in vals_to_check.items():
                        if isinstance(v, (pd.Series, pd.DataFrame)):
                            logger.error(f"CRITICAL: {k} is a Series/DF! {v}")
                            # Force conversion to scalar if possible (e.g. unique value)
                            # But better to crash with info
                            raise ValueError(f"{k} IS A SERIES: {v}")

                    logger.info(f"SIGNAL FOUND: LONG at {ts}")
                    sig = Signal(
                        symbol=symbol,
                        timestamp=ts,
                        type=SignalType.LONG,
                        price=float(current['Close']), # Force float
                        atr_value=float(current['ATR']),
                        metadata={
                            "rsi": float(current['RSI']),
                            "adx": float(current['ADX']),
                            "bb_lower": float(current['BB_Lower']),
                            "sma_50": float(sma_50_val)
                        }
                    )
                    signals.append(sig)
                    continue 

            # --- SHORT EXECUTION ---
            if context_ok and short_setup:
                # Pattern Check DISABLED by User Request
                # if self.pattern_recognizer.check_bearish_reversal(current):
                if True:
                    # Found Signal
                    sig = Signal(
                        symbol=symbol,
                        timestamp=ts,
                        type=SignalType.SHORT,
                        price=float(current['Close']),
                        atr_value=float(current['ATR']),
                        metadata={
                            "rsi": float(current['RSI']),
                            "adx": float(current['ADX']),
                            "bb_upper": float(current['BB_Upper']),
                            "sma_50": float(sma_50_val)
                        }
                    )
                    signals.append(sig)

        return signals
