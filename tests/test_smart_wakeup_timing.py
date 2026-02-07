"""
Test Smart Wakeup Timing Functions
"""
import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from core.timing import wait_until_minute, wait_until_next_hour, get_minutes_until_close


class TestSmartWakeupTiming(unittest.TestCase):
    
    @patch('core.timing.time.sleep')
    @patch('core.timing.datetime')
    def test_wait_until_minute_future(self, mock_datetime, mock_sleep):
        """Test waiting until a future minute in the current hour"""
        # Current time: 10:30:00
        current_time = datetime(2026, 2, 5, 10, 30, 0)
        mock_datetime.now.return_value = current_time
        
        # Target: minute 55 (should wait 25 minutes)
        wait_until_minute(55)
        
        # Should sleep for 25 * 60 = 1500 seconds
        mock_sleep.assert_called_once()
        sleep_seconds = mock_sleep.call_args[0][0]
        self.assertAlmostEqual(sleep_seconds, 1500, delta=1)
    
    @patch('core.timing.time.sleep')
    @patch('core.timing.datetime')
    def test_wait_until_minute_past(self, mock_datetime, mock_sleep):
        """Test waiting until a minute that's already passed (next hour)"""
        # Current time: 10:58:00
        current_time = datetime(2026, 2, 5, 10, 58, 0)
        mock_datetime.now.return_value = current_time
        
        # Target: minute 55 (already passed, should wait until 11:55)
        wait_until_minute(55)
        
        # Should sleep for ~57 minutes
        mock_sleep.assert_called_once()
        sleep_seconds = mock_sleep.call_args[0][0]
        self.assertAlmostEqual(sleep_seconds, 57 * 60, delta=5)
    
    @patch('core.timing.time.sleep')
    @patch('core.timing.datetime')
    def test_wait_until_next_hour(self, mock_datetime, mock_sleep):
        """Test waiting until the next hour with buffer"""
        # Current time: 10:45:30
        current_time = datetime(2026, 2, 5, 10, 45, 30)
        mock_datetime.now.return_value = current_time
        
        # Should wait until 11:00:10 (14 min 30 sec + 10 sec buffer)
        wait_until_next_hour(buffer_seconds=10)
        
        # Should sleep for ~880 seconds (14:30 + 10)
        mock_sleep.assert_called_once()
        sleep_seconds = mock_sleep.call_args[0][0]
        self.assertAlmostEqual(sleep_seconds, 880, delta=1)
    
    @patch('core.timing.datetime')
    def test_get_minutes_until_close(self, mock_datetime):
        """Test calculating minutes until hour close"""
        # Current time: 10:45:30
        current_time = datetime(2026, 2, 5, 10, 45, 30)
        mock_datetime.now.return_value = current_time
        
        minutes_left = get_minutes_until_close()
        
        # Should be 14 minutes (60 - 45 - 1 for seconds > 0)
        self.assertEqual(minutes_left, 14)
    
    @patch('core.timing.datetime')
    def test_get_minutes_until_close_exact_minute(self, mock_datetime):
        """Test calculating minutes when exactly on the minute"""
        # Current time: 10:45:00
        current_time = datetime(2026, 2, 5, 10, 45, 0)
        mock_datetime.now.return_value = current_time
        
        minutes_left = get_minutes_until_close()
        
        # Should be 15 minutes (60 - 45)
        self.assertEqual(minutes_left, 15)


if __name__ == '__main__':
    unittest.main()
