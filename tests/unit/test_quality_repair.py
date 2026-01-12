import unittest
import pandas as pd
import numpy as np
from data.quality.detector import Gap, GapType, GapSeverity
from data.quality.repair import GapRepair

class TestGapRepair(unittest.TestCase):
    def setUp(self):
        self.repair = GapRepair()
        
    def test_fill_small_gap_interpolation(self):
        """Test filling a small gap with interpolation"""
        # Data: 10, 20, NaN, NaN, 50
        dates = pd.date_range('2024-01-01 10:00', '2024-01-01 11:00', freq='15min')
        data = pd.DataFrame({
            'Close': [10.0, 20.0, 30.0, 40.0, 50.0], # Full ideal
             'Open': [10, 20, 30, 40, 50],
             'High': [10, 20, 30, 40, 50],
             'Low': [10, 20, 30, 40, 50],
             'Volume': [100, 100, 100, 100, 100]
        }, index=dates)
        
        # Create gap by dropping middle rows
        gap_start = dates[1] # 10:15
        gap_end = dates[4]   # 11:00
        # Drop 10:30 and 10:45
        data_gapped = data.drop([dates[2], dates[3]])
        
        gap = Gap(
            symbol="TEST",
            start_time=gap_start,
            end_time=gap_end,
            duration_minutes=45,
            gap_type=GapType.SMALL_GAP,
            severity=GapSeverity.LOW,
            before_price=20.0,
            after_price=50.0,
            price_change_pct=0.0
        )
        
        filled = self.repair.fill_gaps(data_gapped, [gap])
        
        # Check if rows are back
        self.assertEqual(len(filled), 5)
        
        # Check interpolation values
        # 10:30 should be 30.0
        val = filled.loc[dates[2], 'Close']
        self.assertAlmostEqual(val, 30.0)
        
    def test_fill_large_gap_ffill(self):
        """Test filling a large gap with ffill"""
        dates = pd.date_range('2024-01-01 10:00', '2024-01-01 12:00', freq='1h')
        # 10:00, 11:00, 12:00
        data = pd.DataFrame({'Close': [10.0, 20.0, 30.0], 'Open':[10,20,30], 'High':[10,20,30], 'Low':[10,20,30], 'Volume':[1,1,1]}, index=dates)
        
        # Drop 11:00
        data_gapped = data.drop([dates[1]])
        
        gap = Gap(
            symbol="TEST",
            start_time=dates[0],
            end_time=dates[2],
            duration_minutes=120,
            gap_type=GapType.OVERNIGHT_GAP, # Large
            severity=GapSeverity.MEDIUM,
            before_price=10.0,
            after_price=30.0,
            price_change_pct=0.0
        )
        
        filled = self.repair.fill_gaps(data_gapped, [gap])
        
        # Check ffill value at 11:00
        val = filled.loc[dates[1], 'Close']
        self.assertEqual(val, 10.0) # Should be ffilled from 10:00

if __name__ == '__main__':
    unittest.main()
