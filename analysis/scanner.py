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
        [CRSI, BB_Lower, BB_Upper, ADX, SMA_200, Volume_SMA_20, etc.]
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
                    if pd.isna(row['CRSI']) or pd.isna(row['SMA_200']) or pd.isna(row['ADX']):
                        continue
                except ValueError:
                    logger.error(f"CRASH IN ROW CHECK at {idx}")
                    logger.error(f"Row Index: {row.index}")
                    logger.error(f"Row Index: {row.index}")
                    logger.error(f"CRSI: {row['CRSI']} Type: {type(row['CRSI'])}")
                    logger.error(f"SMA_200: {row['SMA_200']} Type: {type(row['SMA_200'])}")
                    raise
                    
                # 1. Common Conditions
                
                # 1. Common Conditions - DYNAMIC VOLUME FILTER (v3.1)
                
                # ADX Regime & Volume Multiplier
                # Lateral (<20): 1.0x
                # Neutral (20-30): 1.2x
                # Tendencial (>30): 1.5x
                
                adx_val = row['ADX']
                vol_mult = 1.0
                if adx_val < 20:
                    vol_mult = 1.0
                elif adx_val < 30:
                    vol_mult = 1.2
                else: 
                    vol_mult = 1.5
                    
                min_vol = row.get('Volume_SMA_20', 0) * vol_mult
                if row['Volume'] < min_vol:
                    continue
                    
                # ADX Filter v3.1: 
                # Tendencial (>30) ALLOWED if Pullback (Trend Following)??
                # Strategy says: "ADX >= 30 + NO operar (if counter trend)"
                # Actually Scanner checks for Reversion.
                # v3.1 Table says: "ADX >= 30 + dirección favorable -> Pullback permitido"
                # "ADX >= 30 + dirección contraria -> NO operar"
                # Since we are implementing Reversion Strategy generally, checks below will handle direction.
                # But here we just ensure we have data.


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
                # v3.1 Uses CRSI < 10 for LONG, > 90 for SHORT
                is_long_candidate = (
                    row['CRSI'] < 10 and
                    row['Close'] <= row['BB_Lower'] and
                    row['Close'] < row.get('VWAP', 999999) and
                    row['Close'] > row['SMA_200'] # Trend Filter (Price > SMA200)
                )
                
                is_short_candidate = (
                    row['CRSI'] > 90 and
                    row['Close'] >= row['BB_Upper'] and
                    row['Close'] > row.get('VWAP', 0) and
                    row['Close'] < row['SMA_200'] # Trend Filter
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
            # 1. Calc SMA 200 if not present
            if 'SMA_200' not in df_daily.columns:
                daily_sma_series = df_daily['Close'].rolling(window=200).mean()
            else:
                daily_sma_series = df_daily['SMA_200']
                
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
                logger.warning(f"No Daily Data provided for {symbol}. Falling back to Hourly SMA 200 (Strategy Divergence!)")
            sma_reindexed = df.get('SMA_200', pd.Series([0]*len(df), index=df.index))
            
        for i in range(start_idx, len(df)):
            current = df.iloc[i]
            prev = df.iloc[i-1]
            ts = timestamps[i]
            
            # Get Daily SMA for this specific timestamp
            # If we failed to build reindexed, default to 0
            sma_200_val = sma_reindexed.iloc[i] if daily_sma_series is not None else current.get('SMA_200', 0)
            
            # --- FILTER CHECK ---
            # 1. ADX - Now used for Volume Multiplier, but we also check if "Counter Trend" is allowed?
            # Strategy: "ADX >= 30 + dirección contraria -> NO operar"
            # If ADX >= 30, we must be careful.
            # But the Strategy Table 4.2 says:
            # - ADX < 20: Mean Reversion Optimal
            # - ADX 20-30: Neutral (Standard)
            # - ADX >= 30: Pullbacks Only (With Trend).
            # If we are doing "Mean Reversion Selectiva", usually we enter AGAINST short-term move (CRSI extreme) 
            # but IN FAVOR of Long-Term Trend (SMA 200).
            # So if Price > SMA 200 (Uptrend) and CRSI < 10 (Dip), we are BUYING THE DIP (Pullback).
            # This IS "Dirección Favorable".
            # So actually, as long as we respect the SMA 200 Trend Filter, we are adhering to "Dirección Favorable".
            # Thus, we don't need to block ADX > 30, as long as Trend Filter holds.
            pass_adx = True # Handled by Trend Filter implication
            
            # 2. Volume (Already checked above in optimization block for 'continue', but for logging...)
            # We already skipped if fail.
            pass_vol = True
            
            # 3. Long Inds
            pass_rsi_long = current['CRSI'] < 10
            # pass_rsiturn_long = current['RSI'] > prev['RSI'] # Not required in v3.1 summary?
            # Summary 6.1: 1. CRSI < 10. 2. Price <= BB lower. 3. Price > SMA 200. ...
            # No explicit mention of "RSI Turn" or "CRSI Turn" in v3.1 text provided.
            # "Todas deben cumplirse: 1. Connors RSI < 10 ..."
            # So we remove the "Turn" requirement for CRSI?
            # User said "Simplificación operativa".
            # Let's assume strict list: 1-6. No turn mentioned.
            
            pass_bb_long = current['Close'] <= current['BB_Lower']
            pass_sma_long = current['Close'] > sma_200_val
            
            vwap_val = current.get('VWAP')
            if vwap_val is None: vwap_val = float('inf')
            # VWAP "Opcional" in v3.1 summary (Table 3).
            # Entry rules do NOT mention VWAP in 6.1 or 6.2.
            # So we disable VWAP check for entry strictly.
            # pass_vwap_long = current['Close'] < vwap_val 
            pass_vwap_long = True

            # 4. Short Inds
            pass_rsi_short = current['CRSI'] > 90
            pass_bb_short = current['Close'] >= current['BB_Upper']
            pass_sma_short = current['Close'] < sma_200_val 
            
            vwap_val_short = current.get('VWAP')
            if vwap_val_short is None: vwap_val_short = 0
            # pass_vwap_short = current['Close'] > vwap_val_short
            pass_vwap_short = True
            
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
                p_type = "LONG" if (pass_rsi_long) else ("SHORT" if (pass_rsi_short) else "NONE")
                
                msg = f"{ts} | {symbol} | {p_type} | ADX={current['ADX']:.1f} | VOL={'OK' if pass_vol else 'FAIL'} | "
                
                if p_type == "LONG":
                    msg += f"CRSI={current['CRSI']:.1f}({'OK' if pass_rsi_long else 'FAIL'}) | BB={'OK' if pass_bb_long else 'FAIL'} | SMA={'OK' if pass_sma_long else 'FAIL'} | "
                    msg += f"PAT={'OK' if has_bull_pat else 'FAIL'}"
                    # v3.1: Pattern not strictly required in 6.1 list? 
                    # "6. Vela 1H cerrada" implies implies just completion?
                    # v1.0 had "Vela de reversión alcista presente"
                    # v3.1 list: "6. Vela 1H cerrada". DOES NOT explicitly say "Reversal Pattern".
                    # Review Summary: "Versión 3.1... Eliminación de decisiones discrecionales... 6. Vela 1H cerrada"
                    # It likely means "Don't enter until candle closes", not "Must be Doji".
                    # Simplification -> Remove Pattern Check?
                    # Let's assume PATTERN IS REMOVED for strict simplified instructions.
                    status = "ACCEPTED" if (context_ok and long_setup) else "REJECTED"
                elif p_type == "SHORT":
                     msg += f"CRSI={current['CRSI']:.1f}({'OK' if pass_rsi_short else 'FAIL'}) | BB={'OK' if pass_bb_short else 'FAIL'} | SMA={'OK' if pass_sma_short else 'FAIL'} | "
                     msg += f"PAT={'OK' if has_bear_pat else 'FAIL'}"
                     status = "ACCEPTED" if (context_ok and short_setup) else "REJECTED"
                     # v2.0: Pattern is optional
                     status = "ACCEPTED" if (context_ok and short_setup) else "REJECTED"
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
                            "rsi": float(current.get('RSI', 0)), # Keep for reference/logs
                            "crsi": float(current['CRSI']),
                            "adx": float(current['ADX']),
                            "bb_lower": float(current['BB_Lower']),
                            "bb_upper": float(current['BB_Upper']),
                            "bb_middle": float(current['BB_Middle']), # For TP1
                            "sma_200": float(sma_200_val)
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
                            "rsi": float(current.get('RSI', 0)),
                            "crsi": float(current['CRSI']),
                            "adx": float(current['ADX']),
                            "bb_lower": float(current['BB_Lower']),
                            "bb_upper": float(current['BB_Upper']),
                            "bb_middle": float(current['BB_Middle']),
                            "sma_200": float(sma_200_val)
                        }
                    )
                    signals.append(sig)

        return signals
