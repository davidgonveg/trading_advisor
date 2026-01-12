import unittest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from data.quality.detector import GapDetector, GapType, GapSeverity

class TestGapDetector(unittest.TestCase):
    def setUp(self):
        self.detector = GapDetector()
        
    def test_detect_gap_basic(self):
        """Test detection of a simple gap"""
        # Create contiguous data 9:30 - 11:30
        dates1 = pd.date_range('2024-01-01 09:30', '2024-01-01 11:30', freq='15min')
        # Gap from 11:30 to 13:00 (90 mins > 30 min threshold)
        dates2 = pd.date_range('2024-01-01 13:00', '2024-01-01 15:00', freq='15min')
        
        dates = dates1.union(dates2)
        
        data = pd.DataFrame({
            'Open': 100, 'High': 101, 'Low': 99, 'Close': 100, 'Volume': 1000
        }, index=dates)
        
        gaps = self.detector.detect_gaps(data, "TEST")
        
        self.assertEqual(len(gaps), 1)
        self.assertEqual(gaps[0].duration_minutes, 90.0)
        self.assertEqual(gaps[0].gap_type, GapType.SMALL_GAP)

    def test_no_gaps(self):
        """Test with perfect data"""
        dates = pd.date_range('2024-01-01 09:30', '2024-01-01 16:00', freq='15min')
        data = pd.DataFrame({
            'Open': 100, 'Close': 100
        }, index=dates)
        
        gaps = self.detector.detect_gaps(data, "TEST")
        self.assertEqual(len(gaps), 0)

    def test_quality_analysis(self):
        """Test full quality report"""
        dates = pd.date_range('2024-01-01 09:30', '2024-01-01 16:00', freq='15min')
        data = pd.DataFrame({
            'Open': 100, 'High': 101, 'Low': 99, 'Close': 100, 'Volume': 1000
        }, index=dates)
        
        # Create gap
        data = data.drop(data.index[10:14]) # Drop 4 rows (60 mins)
        
        report = self.detector.analyze_quality(data, "TEST")
        
        self.assertEqual(report.total_gaps, 1)
        self.assertTrue(report.completeness_pct < 100)
        self.assertTrue(report.overall_quality_score < 100)

if __name__ == '__main__':
    unittest.main()
