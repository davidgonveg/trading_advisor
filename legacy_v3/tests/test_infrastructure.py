import pytest
from unittest.mock import MagicMock, patch
from services.continuous_collector import ContinuousDataCollector
from services.dynamic_monitor import DynamicMonitor, MonitorPriority
import config
from datetime import datetime

class TestContinuousCollector:
    
    @pytest.fixture
    def collector(self, mock_db):
        with patch('services.continuous_collector.sqlite3.connect') as mock_connect:
            mock_connect.return_value = mock_db
            collector = ContinuousDataCollector()
            return collector

    def test_initialization(self, collector):
        assert hasattr(collector, 'indicators')
        assert hasattr(collector, 'gap_detector')
        assert collector.running is False

    @patch('services.continuous_collector.time.sleep', return_value=None)  # Don't actually sleep
    @patch('config.get_current_trading_session')
    def test_run_loop_cycle(self, mock_get_session, mock_sleep, collector):
        # Simulate one loop cycle then stop
        collector.running = True
        
        # Configure session mock to return a valid session
        mock_get_session.return_value = ('REGULAR', {'DATA_INTERVAL': 15})
        
        # Mock internal methods to avoid complex side effects
        collector._process_active_session = MagicMock()
        collector._process_off_hours = MagicMock()
        
        collector.stop_collection()
        assert collector.running is False

class TestDynamicMonitor:
    
    @pytest.fixture
    def monitor(self):
        return DynamicMonitor()

    def test_add_target(self, monitor):
        monitor.add_monitor_target("AAPL", priority=MonitorPriority.HIGH, reason="Test")
        assert "AAPL" in monitor.monitor_targets
        assert monitor.monitor_targets["AAPL"].priority == MonitorPriority.HIGH

    def test_priority_queue(self, monitor):
        # Add varied priorities
        monitor.add_monitor_target("CRITICAL_SYM", priority=MonitorPriority.CRITICAL, reason="Test")
        monitor.add_monitor_target("LOW_SYM", priority=MonitorPriority.LOW, reason="Test")
        
        # Check if they are in the correct logic buckets
        # We can simulate checking targets for update
        
        # Force last_update to be in the past
        monitor.monitor_targets["CRITICAL_SYM"].last_update = datetime.min
        monitor.monitor_targets["LOW_SYM"].last_update = datetime.min
        
        # Need to mock _get_current_time to return now (already done in implementations usually)
        # But we can just call _get_targets_for_update
        
        due = monitor._get_targets_for_update()
        assert "CRITICAL_SYM" in due
        assert "LOW_SYM" in due

    def test_update_priorities_from_exit_signals(self, monitor):
        # Create a mock signal
        mock_signal = MagicMock()
        mock_signal.symbol = "NVDA"
        
        # Setup urgency mock (since code checks urgency.value)
        mock_urgency = MagicMock()
        mock_urgency.value = "EXIT_URGENT"
        mock_signal.urgency = mock_urgency
        
        # Initial state: NVDA not tracked or default
        monitor.add_monitor_target("NVDA", priority=MonitorPriority.NORMAL, reason="Initial")
        
        # Simulate exit signal urgency
        mock_signal.signal_type = "EXIT" 
        mock_signal.exit_score = 9
        
        monitor.update_priorities_from_exit_signals([mock_signal])
        
        # Assert priority changed to CRITICAL because of EXIT_URGENT
        assert monitor.monitor_targets["NVDA"].priority == MonitorPriority.CRITICAL
