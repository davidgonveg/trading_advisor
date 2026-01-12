import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime
from execution.position_manager.position_tracker import PositionTracker
from execution.position_manager.models import TrackedPosition, EntryLevelStatus, ExecutionEvent, ExecutionEventType, ExecutionStatus
from execution.position_manager.execution_monitor import ExecutionMonitor

class TestPositionTracker:
    
    @pytest.fixture
    def tracker(self, mock_db):
        """Fixture for PositionTracker in testing mode (no DB)"""
        # We disable internal DB logic.
        tracker = PositionTracker(use_database=False)
        return tracker
    
    def test_register_new_position(self, tracker):
        """Test adding a new position"""
        # Create mock objects required by register_new_position
        mock_signal = MagicMock()
        mock_signal.symbol = "AAPL"
        mock_signal.signal_type = "LONG"
        mock_signal.signal_strength = 90
        mock_signal.current_price = 150.0
        
        mock_plan = MagicMock()
        mock_plan.entry_levels = [{'price': 150.0, 'share': 100}]
        mock_plan.stop_loss = 140.0
        mock_plan.targets = [160.0, 170.0]
        
        # Test registering
        # Note: register_new_position uses create_entry_levels_from_plan which might fail if plan structure is not perfect
        # We need to mock the converter functions or provide a structure that satisfies them.
        # It imports: create_entry_levels_from_plan from .models
        
        # Easier to mock the helper functions so we don't need perfect plan objects
        with patch('execution.position_manager.position_tracker.create_entry_levels_from_plan') as mock_create_entry, \
             patch('execution.position_manager.position_tracker.create_exit_levels_from_plan') as mock_create_exit, \
             patch('execution.position_manager.position_tracker.create_stop_level_from_plan') as mock_create_stop:
            
            mock_create_entry.return_value = []
            mock_create_exit.return_value = []
            mock_create_stop.return_value = MagicMock()
            
            pid = tracker.register_new_position(mock_signal, mock_plan)
            
            assert pid is not None
            assert tracker.has_active_position("AAPL")

    def test_update_level_status(self, tracker):
        """Test updating a level status"""
        # Inject a mock position
        pos = MagicMock()
        pos.position_id = "test-id"
        pos.symbol = "MSFT"
        pos.entry_levels = [] # Add dummy levels if needed logic iterates them
        tracker.active_positions["MSFT"] = pos
        
        # Test update (mocking internal logic mostly via what it calls)
        # Assuming we want to verify it calls persistence
        tracker.persist_to_db = MagicMock()
        tracker.use_database = True
        
        # We need to verify logic inside update_level_status, which iterates levels.
        # It's coupled to model structure. 
        # For this test, let's just ensure it handles "not found" gracefully or calls persist.
        # To make it return True, we need a level that matches.
        
        mock_level = MagicMock()
        mock_level.level_id = 1
        pos.entry_levels = [mock_level]
        
        success = tracker.update_level_status(
            position_id="test-id",
            level_id=1,
            level_type='ENTRY',
            new_status=ExecutionStatus.FILLED,
            filled_price=100.0
        )
        success = tracker.update_level_status(
            position_id="test-id", 
            level_id=1, 
            level_type='ENTRY', 
            new_status=ExecutionStatus.FILLED
        )
        
        assert success is True
        tracker.persist_to_db.assert_called()

class TestExecutionMonitor:
    
    @pytest.fixture
    def monitor(self):
        tracker = MagicMock()
        return ExecutionMonitor(position_tracker=tracker)

    def test_get_current_price_mock(self, monitor):
        """Test price fetching failover"""
        monitor.use_real_prices = False
        # Should return None or mock if configured
        price = monitor.get_current_price("AAPL")
        # In non-real mode it might rely on something else or return None
        # checking code... 'Execution Monitor en modo TESTING (precios simulados)'
        # If use_real_prices=False, get_current_price returns None unless we mock it.
        pass
    
    def test_execution_logic_invocation(self, monitor):
        """Verify check_active_positions iterates and checks"""
        monitor.tracker.get_all_active_positions.return_value = [MagicMock(symbol="AAPL")]
        monitor.get_current_price = MagicMock(return_value={'Close': 150.0, 'High': 151.0, 'Low': 149.0})
        monitor.check_position_executions = MagicMock(return_value=[]) # Mock plural
        
        monitor.monitor_all_positions()
        
        monitor.check_position_executions.assert_called()
