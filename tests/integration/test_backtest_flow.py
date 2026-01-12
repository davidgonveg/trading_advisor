
import unittest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging

# Ensure root is in path
import sys
import os
from pathlib import Path
root_path = str(Path(__file__).resolve().parent.parent.parent)
if root_path not in sys.path:
    sys.path.insert(0, root_path)

from backtesting.engine import BacktestEngine
from backtesting.account import Account
from analysis.signal import SignalType
from config.settings import STRATEGY_CONFIG

# Configure logging to see engine output during tests
logging.basicConfig(level=logging.INFO)

class TestBacktestFlow(unittest.TestCase):
    def setUp(self):
        self.engine = BacktestEngine(initial_capital=10000.0)
        self.symbol = "TEST_SYM"
        
        # Create Synthetic Data
        # We need enough history for SMA50 (50 hours? No, 50 days for SMA50 daily)
        # But our scanner logic calculates keys.
        # Let's mock the keys directly expected by Scanner.
        
        # Generate 100 hourly candles
        dates = pd.date_range(start="2025-01-01", periods=100, freq="1h")
        self.df = pd.DataFrame(index=dates)
        
        # Base Price
        self.df['Open'] = 100.0
        self.df['High'] = 101.0
        self.df['Low'] = 99.0
        self.df['Close'] = 100.0
        self.df['Volume'] = 10000.0
        
        # Add Indicators expected by Scanner
        self.df['RSI'] = 50.0
        self.df['ADX'] = 20.0 # Good (ranging)
        self.df['BB_Lower'] = 90.0
        self.df['BB_Upper'] = 110.0
        self.df['VWAP'] = 105.0 # Price < VWAP (Good for Long)
        self.df['SMA_50'] = 90.0 # Price > SMA50 (Good for Long)
        self.df['Volume_SMA_20'] = 5000.0 # Volume > SMA (Good)
        self.df['ATR'] = 1.0
        
        # Default Pattern cols
        self.df['CDLHAMMER'] = 0
        self.df['CDLSHOOTINGSTAR'] = 0
        
        # Inject Daily Data (Mock)
        self.df_daily = pd.DataFrame(index=dates.normalize().unique())
        self.df_daily['Close'] = 100.0
        self.df_daily['SMA_50'] = 90.0
        
    def test_long_entry_execution(self):
        """
        Simulate a perfect LONG setup and verify trade execution.
        """
        from unittest.mock import patch

        # Inject Signal at Index 50
        idx = 50
        
        # 1. Setup Indicators for Long
        self.df.iloc[idx, self.df.columns.get_loc('RSI')] = 30.0 # Oversold
        self.df.iloc[idx-1, self.df.columns.get_loc('RSI')] = 20.0 # Turn Up
        
        self.df.iloc[idx, self.df.columns.get_loc('Close')] = 89.0 # Below BB Lower (90)
        self.df.iloc[idx, self.df.columns.get_loc('BB_Lower')] = 90.0 
        
        self.df.iloc[idx, self.df.columns.get_loc('SMA_50')] = 80.0 # Price > SMA50 (Trend Up)
        self.df.iloc[idx, self.df.columns.get_loc('VWAP')] = 100.0 # Price < VWAP
        
        # Volume
        self.df.iloc[idx, self.df.columns.get_loc('Volume')] = 10000.0
        self.df.iloc[idx, self.df.columns.get_loc('Volume_SMA_20')] = 5000.0
        
        # Indicators update for this row
        self.df.iloc[idx, self.df.columns.get_loc('RSI')] = 30.0
        self.df.iloc[idx, self.df.columns.get_loc('BB_Lower')] = 90.0 # Close 89.2 < 90
        self.df.iloc[idx, self.df.columns.get_loc('SMA_50')] = 80.0
        
        # 3. Load into Engine
        self.engine.market_data = {self.symbol: self.df}
        self.engine.daily_data = {self.symbol: self.df_daily}
        
        # Mock detect_patterns to FORCE success
        # The real detect_patterns overwrites pattern columns. 
        # We want to just set pat_hammer=100 at idx 50.
        def mock_detect(df):
            # Pass through but set hammer at idx 50
            if 'pat_hammer' not in df.columns:
                df['pat_hammer'] = 0
            df.iloc[idx, df.columns.get_loc('pat_hammer')] = 100
            
            # Ensure other cols exist
            if 'pat_shooting_star' not in df.columns: df['pat_shooting_star'] = 0
            if 'pat_engulfing' not in df.columns: df['pat_engulfing'] = 0
            if 'pat_doji' not in df.columns: df['pat_doji'] = 0
            
            return df

        with patch('analysis.patterns.PatternRecognizer.detect_patterns', side_effect=mock_detect):
            # 4. Run
            report = self.engine.run()
        
        # 5. Assertions
        if report is None:
             self.fail("Engine returned None (No trades/signals generated)")
             
        # Should have found signal and entered trade
        trades = report['trades']
        positions = report['positions']
        
        print(f"Trades: {len(trades)}")
        print(f"Open Positions: {len(positions)}")
        
        # Verify success
        # Either we have an open position or closed trade
        self.assertTrue(len(trades) > 0 or len(positions) > 0, "No trades executed for perfect setup")

if __name__ == '__main__':
    unittest.main()
