import pandas as pd
import logging
from datetime import datetime
from typing import List, Optional

from config.settings import STRATEGY_CONFIG
from analysis.signal import Signal, SignalType, SignalStatus
from analysis.patterns import PatternRecognizer
from analysis.logic import check_vwap_bounce

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

        # Detect patterns first (adds pat_wick_bull, etc.)
        df = self.pattern_recognizer.detect_patterns(df_hourly)
        
        # Decision Logger
        decision_logger = logging.getLogger("scanner_decisions")

        # Determine Loop Range
        if scan_latest:
            start_idx = len(df) - 1
            if start_idx < 0: return signals
        else:
            start_idx = 0
            
        for i in range(start_idx, len(df)):
            row = df.iloc[i]
            ts = df.index[i]
            
            # Data Integrity Check
            try:
                if pd.isna(row['Volume']) or pd.isna(row['VWAP']) or pd.isna(row['Close']):
                    continue
            except KeyError:
                continue
            except ValueError:
                # Log critical data errors but don't crash scan
                logger.error(f"Data Error at {ts} for {symbol}")
                continue
                    
            # USE SHARED LOGIC
            # This ensures parity with Backtesting (vwap_bounce.py)
            signal_type = check_vwap_bounce(row, self.cfg)
            
            if signal_type:
                # Common Metadata for Signal
                vwap_val = row.get('VWAP')
                ema_200 = row.get('EMA_200', 0)
                vol_sma = row.get('Volume_SMA_20', 0)
                atr_val = row.get('ATR', 0)
                
                sig = Signal(
                    symbol=symbol,
                    timestamp=ts,
                    type=signal_type,
                    price=float(row['Close']),
                    atr_value=float(atr_val),
                    metadata={
                        "vwap": float(vwap_val) if vwap_val else 0.0,
                        "ema_200": float(ema_200) if ema_200 else 0.0,
                        "vol": float(row['Volume']),
                        "vol_sma": float(vol_sma),
                        "pat_score": 100 if signal_type == SignalType.LONG else -100
                    }
                )
                signals.append(sig)
                logger.info(f"SIGNAL FOUND: {signal_type.value} {symbol} @ {row['Close']} (VWAP Bounce)")
                decision_logger.info(f"{ts} | {symbol} | {signal_type.value} -> ACCEPTED via Shared Logic")
            else:
                # Optional: Log debug for rejected rows if needed, but keeping it clean for now.
                # decision_logger.debug(f"{ts} | {symbol} | NO SIGNAL")
                pass

        return signals
