import unittest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from analysis.indicators import TechnicalIndicators

class TestTechnicalIndicators(unittest.TestCase):
    def setUp(self):
        self.ti = TechnicalIndicators()
        
    def create_intraday_data(self):
        # Create 2 days of intraday data (1H candles)
        # Day 1: 9:30 - 16:00 (7 hours -> 7 candles)
        # Day 2: 9:30 - 16:00 (7 hours -> 7 candles)
        
        times = []
        base_date = datetime(2023, 1, 1, 9, 30)
        
        # Day 1
        for i in range(7):
            times.append(base_date + timedelta(hours=i))
            
        # Day 2
        base_date_2 = datetime(2023, 1, 2, 9, 30)
        for i in range(7):
            times.append(base_date_2 + timedelta(hours=i))
            
        df = pd.DataFrame(index=times)
        df['High'] = 105.0
        df['Low'] = 95.0
        df['Close'] = 100.0
        # Varied volume to make VWAP != Simple Average
        df['Volume'] = [1000 * (i+1) for i in range(14)]
        
        # Typical Price = (105+95+100)/3 = 100.0
        # VWAP should be weighted average of 100.0
        # If Price is constant (100), VWAP should be 100 regardless of volume.
        
        return df

    def test_vwap_reset_daily(self):
        """Test that VWAP resets at the beginning of a new day."""
        df = self.create_intraday_data()
        
        # Modify prices to verify calculation
        # Day 1: Price 100.
        # Day 2: Price 200.
        
        # First 7 rows are Day 1 (indices 0-6)
        # Next 7 rows are Day 2 (indices 7-13)
        
        df.iloc[7:, df.columns.get_loc('High')] = 205.0
        df.iloc[7:, df.columns.get_loc('Low')] = 195.0
        df.iloc[7:, df.columns.get_loc('Close')] = 200.0
        
        # Verify Day 1 VWAP
        # Typical Price = 100.
        # VWAP should be exactly 100 for all Day 1.
        
        res = self.ti.vwap(df)
        
        self.assertTrue(all(res.iloc[0:7] == 100.0))
        
        # Verify Day 2 VWAP
        # Day 2 starts at index 7.
        # It should ignore Day 1 data.
        # Typical Price = 200.
        # VWAP should be exactly 200 for all Day 2.
        
        self.assertTrue(all(res.iloc[7:] == 200.0))
        
    def test_vwap_calculation_accuracy(self):
        """Test numeric accuracy of VWAP within a single day."""
        # 3 candles same day
        times = [datetime(2023,1,1,10), datetime(2023,1,1,11), datetime(2023,1,1,12)]
        df = pd.DataFrame(index=times)
        
        # Candle 1: TP=100, Vol=100 -> PV=10000
        # Candle 2: TP=110, Vol=200 -> PV=22000
        # Candle 3: TP=105, Vol=100 -> PV=10500
        
        df['High'] = [100, 110, 105] # Simplified, assuming H=L=C=TP for easy math
        df['Low'] = [100, 110, 105]
        df['Close'] = [100, 110, 105]
        df['Volume'] = [100, 200, 100]
        
        vwap = self.ti.vwap(df)
        
        # Expected 1: 10000 / 100 = 100.0
        self.assertAlmostEqual(vwap.iloc[0], 100.0)
        
        # Expected 2: (10000 + 22000) / (100 + 200) = 32000 / 300 = 106.666...
        self.assertAlmostEqual(vwap.iloc[1], 106.66666666)
        
        # Expected 3: (32000 + 10500) / (300 + 100) = 42500 / 400 = 106.25
        self.assertAlmostEqual(vwap.iloc[2], 106.25)

if __name__ == '__main__':
    unittest.main()
