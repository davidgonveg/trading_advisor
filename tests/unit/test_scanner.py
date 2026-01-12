
import unittest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
from analysis.scanner import Scanner

class TestScanner(unittest.TestCase):
    def setUp(self):
        self.scanner = Scanner()
        
    def create_mock_data(self, length=20):
        dates = [datetime.now(timezone.utc) - timedelta(hours=x) for x in range(length)]
        dates.reverse()
        
        df = pd.DataFrame(index=dates)
        df['Open'] = 100.0
        df['High'] = 105.0
        df['Low'] = 95.0
        df['Close'] = 100.0
        df['Volume'] = 1000
        
        # Add Indicators
        df['RSI'] = 50.0
        df['BB_Lower'] = 90.0
        df['BB_Upper'] = 110.0
        df['BB_Middle'] = 100.0
        df['ADX'] = 15.0 # Ranging
        df['SMA_50'] = 105.0 # Downtrend context
        df['VWAP'] = 102.0
        df['ATR'] = 2.0
        df['Volume_SMA_20'] = 500
        
        return df

    def test_long_signal_logic(self):
        # Create data where last row meets LONG criteria
        # RSI < 35, Turned Up
        # Close <= BB_Lower
        # Close < VWAP
        # Close > SMA_50 (Trend Filter) -- Wait, SMA50 needs to be < Price for Long?
        # Strategy: "Precio > SMA(50) en gráfico DIARIO" -> UPTREND
        
        df = self.create_mock_data(20)
        
        # Setup Trend
        df['SMA_50'] = 80.0 # Price (89.5) > SMA (80) -> Bullish Trend
        
        # Setup Prev Row (Index -2)
        # RSI Low but down
        df.iloc[-2, df.columns.get_loc('RSI')] = 30.0
        
        # Setup Curr Row (Index -1)
        # RSI Low but UP
        df.iloc[-1, df.columns.get_loc('RSI')] = 32.0 # < 35 and > 30 (Turn Up)
        
        # BB Touch
        df.iloc[-1, df.columns.get_loc('Close')] = 89.0 # Below Low BB ?
        df.iloc[-1, df.columns.get_loc('BB_Lower')] = 90.0
        
        # VWAP
        df.iloc[-1, df.columns.get_loc('VWAP')] = 95.0 # Price < VWAP
        
        # Patterns
        # Let's force pattern recognizer to say YES
        # We can mock the pattern_recognizer or craft the candle
        # Crafting Hammer:
        # Open 89, Close 89.5 (Small Body)
        # Low 85 (Long wick)
        # High 89.6
        df.iloc[-1, df.columns.get_loc('Open')] = 89.0
        df.iloc[-1, df.columns.get_loc('Close')] = 89.5
        df.iloc[-1, df.columns.get_loc('Low')] = 80.0
        df.iloc[-1, df.columns.get_loc('High')] = 89.6
        
        # Run Scanner
        signals = self.scanner.find_signals(df, "MOCK")
        
        # Should find 1 signal
        self.assertTrue(len(signals) >= 1)
        self.assertEqual(signals[-1].type.value, "LONG")

if __name__ == "__main__":
    unittest.main()
