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
            

        # Decision Logger
        decision_logger = logging.getLogger("scanner_decisions")

        # Determine Loop Range
        # If scanning latest, we only check the last row.
        # We start at 0 for the first row, but need to ensure 'prev' logic is handled if used.
        # For this strategy, we only need the current row.
        if scan_latest:
            start_idx = len(df) - 1
            if start_idx < 0: # No rows to scan
                return signals
        else:
            start_idx = 0
            
        for i in range(start_idx, len(df)):
            row = df.iloc[i]
            ts = df.index[i] # Get timestamp from index
            try:
                # SKIP if any required indicator is NaN
                # For VWAP Bounce, we need Volume, VWAP, Low, High, Close, ATR
                if pd.isna(row['Volume']) or pd.isna(row['VWAP']) or pd.isna(row['Low']) or pd.isna(row['High']) or pd.isna(row['Close']):
                    continue
            except KeyError as e:
                logger.warning(f"Missing column in scanner data for {symbol} at {ts}: {e}")
                continue
            except ValueError:
                logger.error(f"CRASH IN ROW CHECK at {ts}")
                logger.error(f"Row Index: {row.index}")
                logger.error(f"Volume: {row['Volume']} Type: {type(row['Volume'])}")
                logger.error(f"VWAP: {row['VWAP']} Type: {type(row['VWAP'])}")
                raise
                    
            # VWAP BOUNCE STRATEGY LOGIC
            
            # 1. Volume Filter
            vol_sma = row.get('Volume_SMA_20', 0)
            if row['Volume'] <= vol_sma:
                decision_logger.debug(f"{ts} | {symbol} | REJECTED: Volume ({row['Volume']:.2f}) <= Vol_SMA_20 ({vol_sma:.2f})")
                continue
                
            vwap_val = row.get('VWAP')
            if not vwap_val: # Should be caught by pd.isna check, but good to double check
                decision_logger.debug(f"{ts} | {symbol} | REJECTED: VWAP not available")
                continue

            ema_200 = row.get('EMA_200')
            if not ema_200 or pd.isna(ema_200):
                 # Fail safe: if enough data, we should have it. If not, maybe skip?
                 # Assuming "Smart Hunter" strictly requires it.
                 # If we are early in history, we might skip.
                 decision_logger.debug(f"{ts} | {symbol} | REJECTED: EMA_200 not available")
                 continue

            # 2. LONG Setup
            # Bounce: Low <= VWAP and Close > VWAP
            bounce_long = (row['Low'] <= vwap_val) and (row['Close'] > vwap_val)
            # Wick: Lower Wick > 2 * Body (pat_wick_bull > 0)
            # Note: detect_patterns adds 'pat_wick_bull'
            wick_bull = row.get('pat_wick_bull', 0) > 0
            # Trend: Close > EMA 200
            trend_long = row['Close'] > ema_200
            
            if bounce_long and wick_bull and trend_long:
                logger.info(f"SIGNAL FOUND: LONG {symbol} @ {row['Close']} (VWAP Bounce + EMA200)")
                sig = Signal(
                    symbol=symbol,
                    timestamp=ts,
                    type=SignalType.LONG,
                    price=float(row['Close']),
                    atr_value=float(row.get('ATR', 0)), # Needed for Sizing
                    metadata={
                        "vwap": float(vwap_val),
                        "ema_200": float(ema_200),
                        "vol": float(row['Volume']),
                        "vol_sma": float(vol_sma),
                        "pat_score": 100
                    }
                )
                signals.append(sig)
                decision_logger.info(f"{ts} | {symbol} | LONG | VWAP Bounce: {bounce_long} | Wick Bull: {wick_bull} | Trend: {trend_long} -> ACCEPTED")
                continue

            # 3. SHORT Setup
            # Bounce: High >= VWAP and Close < VWAP
            bounce_short = (row['High'] >= vwap_val) and (row['Close'] < vwap_val)
            # Wick: Upper Wick > 2 * Body (pat_wick_bear < 0)
            wick_bear = row.get('pat_wick_bear', 0) < 0
            # Trend: Close < EMA 200
            trend_short = row['Close'] < ema_200
            
            if bounce_short and wick_bear and trend_short:
                logger.info(f"SIGNAL FOUND: SHORT {symbol} @ {row['Close']} (VWAP Bounce + EMA200)")
                sig = Signal(
                    symbol=symbol,
                    timestamp=ts,
                    type=SignalType.SHORT,
                    price=float(row['Close']),
                    atr_value=float(row.get('ATR', 0)),
                    metadata={
                        "vwap": float(vwap_val),
                        "ema_200": float(ema_200),
                        "vol": float(row['Volume']),
                        "vol_sma": float(vol_sma),
                        "pat_score": -100
                    }
                )
                signals.append(sig)
                decision_logger.info(f"{ts} | {symbol} | SHORT | VWAP Bounce: {bounce_short} | Wick Bear: {wick_bear} | Trend: {trend_short} -> ACCEPTED")
                continue
            
            # If no signal, log rejection for debugging
            decision_logger.debug(f"{ts} | {symbol} | REJECTED. C:{row['Close']:.2f}, V:{vwap_val:.2f}, E200:{ema_200:.2f}. LB:{bounce_long}, SB:{bounce_short}, T:{trend_long if row['Close'] > ema_200 else 'Bear'}")


        return signals

