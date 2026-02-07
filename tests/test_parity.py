import unittest
import pandas as pd
import numpy as np
import logging
from analysis.scanner import Scanner
from backtesting.strategies.vwap_bounce import VWAPBounce
from analysis.signal import SignalType

# Setup Logger
logging.basicConfig(level=logging.ERROR)

from config.settings import STRATEGY_CONFIG

class TestParity(unittest.TestCase):
    def setUp(self):
        self.scanner = Scanner()
        self.strategy = VWAPBounce()
        self.strategy.setup(STRATEGY_CONFIG)
        
        # Create Data
        index = pd.date_range("2024-01-01", periods=50, freq="h")
        self.df = pd.DataFrame({
            'Open': [100.0] * 50,
            'High': [102.0] * 50,
            'Low': [98.0] * 50,
            'Close': [100.0] * 50,
            'Volume': [1000.0] * 50,
        }, index=index)
        
        # Add required indicators
        self.df['VWAP'] = 100.0
        self.df['EMA_200'] = 90.0 # Uptrend
        self.df['Volume_SMA_20'] = 500.0 # Valid volume
        self.df['ATR'] = 1.0
        self.df['RSI'] = 50.0
        
    def test_long_signal_parity(self):
        # Construct a LONG Signal Candle
        # Rule: Low <= VWAP and Close > VWAP
        # Wick Bull: Lower Wick > 2 * Body
        # Let VWAP = 100.0
        # Open=101, Close=101.5 (Body=0.5)
        # Low=99.0 (Lower Wick = 101-99 = 2.0). 2.0 > 2 * 0.5 (1.0) -> Valid pattern
        # Low (99) <= VWAP (100) -> Valid Bounce
        # Close (101.5) > VWAP (100) -> Valid Bounce
        # Close (101.5) > EMA (90) -> Valid Trend
        
        idx = 45
        timestamp = self.df.index[idx]
        
        df_test = self.df.copy()
        
        df_test.loc[timestamp, 'Open'] = 101.0
        df_test.loc[timestamp, 'Close'] = 101.5
        df_test.loc[timestamp, 'Low'] = 99.0
        df_test.loc[timestamp, 'High'] = 102.0
        df_test.loc[timestamp, 'Volume'] = 2000.0
        
        # 1. Run Scanner
        # Scanner calls detect_patterns internally
        scanner_signals = self.scanner.find_signals("TEST", df_test.copy())
        
        long_sigs = [s for s in scanner_signals if s.type == SignalType.LONG and s.timestamp == timestamp]
        self.assertEqual(len(long_sigs), 1, f"Scanner failed to find LONG signal. Signals: {len(scanner_signals)}")
        
        # 2. Run Strategy (Backtest)
        self.strategy.symbol = "TEST"
        self.strategy._precompute_indicators(df_test.copy()) 
        
        # Pass history up to idx
        history = df_test.iloc[:idx+1]
        portfolio_ctx = {"positions": {}, "total_equity": 10000}
        
        strat_signal = self.strategy.on_bar(history, portfolio_ctx)
        
        self.assertIsNotNone(strat_signal)
        # SignalSide.BUY vs SignalType.LONG. Map them?
        # SignalSide.BUY value is 'BUY' usually.
        self.assertEqual(strat_signal.side.value, "BUY", f"Strategy failed to find BUY signal. Got {strat_signal.side}")
        
        print(f"\n[SUCCESS] Parity Confirmed for LONG Signal at {timestamp}")

if __name__ == '__main__':
    unittest.main()
