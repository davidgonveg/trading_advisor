import unittest
import pandas as pd
import numpy as np
from analysis.patterns import PatternRecognizer

class TestPatterns(unittest.TestCase):
    def setUp(self):
        self.recognizer = PatternRecognizer()

    def create_candle(self, open, high, low, close):
        return pd.DataFrame({
            'Open': [open],
            'High': [high],
            'Low': [low],
            'Close': [close]
        })

    def test_hammer_detection(self):
        # Hammer: Small body, long lower wick to avg body ratio
        # Body: 2 (102-100). Lower wick: 5 (100-95). Upper: 0.
        # Lower > 2*Body (5 > 4). True.
        df = self.create_candle(100.0, 102.5, 90.0, 102.0)
        # Need rolling avg logic? PatternRecognizer uses rolling(10).mean()
        # So we need > 10 rows to establish avg? 
        # Or we mock the rolling part? 
        # The code: avg_body = body.rolling(10).mean() 
        # If len < 10, result is NaN.
        
        # Let's create a dataframe with 100 rows to satisfy any lookback requirements
        # Create a DOWNTREND for Hammer (Bullish Reversal)
        # Price drops from 200 to 100
        opens = [200.0 - i for i in range(100)] 
        closes = [200.0 - i - 2.0 for i in range(100)] # Body = 2.0
        highs = [200.0 - i + 0.5 for i in range(100)]
        lows = [200.0 - i - 2.5 for i in range(100)]
        
        # Last candle is Hammer
        # Body 1 (100-101)
        # Lower wick needs to be > 2 (so < 98)
        # Upper wick small
        opens[-1] = 100.0
        closes[-1] = 101.0
        highs[-1] = 101.1
        lows[-1] = 95.0 # Lower wick = 5. Body = 1.
        
        df = pd.DataFrame({
            'Open': opens,
            'High': highs,
            'Low': lows,
            'Close': closes
        })
        
        res = self.recognizer.detect_patterns(df)
        last_row = res.iloc[-1]
        
        # Check 'pat_hammer' > 0
        self.assertGreater(last_row['pat_hammer'], 0)

    def test_shooting_star(self):
        # Shooting Star: Long Upper Wick
        # Needs UPTREND context with decent body size
        opens = [100.0 + i for i in range(100)]
        closes = [100.0 + i + 2.0 for i in range(100)] # Body = 2.0
        highs = [100.0 + i + 2.5 for i in range(100)]
        lows = [100.0 + i - 0.5 for i in range(100)]
        
        # Trend ends at i=99: Close = 100+99+2 = 201.0
        # Shooting Star should appear after this.
        # Let's Gap Up slightly to 202.0
        opens[-1] = 202.0
        closes[-1] = 203.0 # Body 1.0 (Small)
        highs[-1] = 212.0 # Upper Wick 9.0 (Long)
        lows[-1] = 201.9 # Small/No lower wick
        
        df = pd.DataFrame({
            'Open': opens, 'High': highs, 'Low': lows, 'Close': closes
        })
        
        res = self.recognizer.detect_patterns(df)
        last_row = res.iloc[-1]
        
        # Star usually negative or positive depending on implementation
        # Our custom impl sets -100
        # If TA-Lib is present, it sets -100
        # Check != 0
        # Check != 0
        self.assertNotEqual(last_row['pat_shooting_star'], 0)

    def test_pure_wick_rejection(self):
        # Test strict 2x body rule from strategy
        
        # Case 1: Bullish Rejection
        # Body = 2. Lower Wick = 5 (> 4). Upper Wick = 5 (Large, but ignored by this specific pattern).
        # Open 100, Close 102. High 107. Low 95.
        # Body 2. Upper 5. Lower 5.
        df1 = self.create_candle(100.0, 107.0, 95.0, 102.0)
        res1 = self.recognizer.detect_patterns(df1)
        
        # Should be detected as Bull Rejection (Lower > 2*Body)
        self.assertEqual(res1.iloc[-1]['pat_wick_bull'], 100)
        # Should also be detected as Bear Rejection (Upper > 2*Body) because both wicks are long
        self.assertEqual(res1.iloc[-1]['pat_wick_bear'], -100)
        
        # Check helper
        # Helper prioritizes? No, it returns 1 if bull > 0, -1 if bear < 0.
        # If both present... logic is: if bull > 0 return 1.
        self.assertEqual(self.recognizer.check_wick_reversal(res1.iloc[-1]), 1)
        
        # Case 2: Only Bearish
        # Body 2. Upper 5. Lower 1.
        # Open 100, Close 102. High 107. Low 99.
        df2 = self.create_candle(100.0, 107.0, 99.0, 102.0)
        res2 = self.recognizer.detect_patterns(df2)
        
        self.assertEqual(res2.iloc[-1]['pat_wick_bear'], -100)
        self.assertEqual(res2.iloc[-1]['pat_wick_bull'], 0)
        self.assertEqual(self.recognizer.check_wick_reversal(res2.iloc[-1]), -1)

    # ... existing tests ...

if __name__ == '__main__':
    unittest.main()
