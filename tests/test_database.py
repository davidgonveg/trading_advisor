import pytest
import sqlite3
import os
from unittest.mock import patch, MagicMock
from datetime import datetime
import json

# Import functions to test
from database.connection import (
    initialize_database, 
    save_signal_data, 
    save_gap_report, 
    get_connection,
    save_indicators_data
)

class TestDatabaseFunctions:
    
    @pytest.fixture
    def mock_db_path(self, tmp_path):
        """Set up a temporary DB path and patch it in the module"""
        db_path = tmp_path / "test_trading.db"
        with patch('database.connection.DB_PATH', str(db_path)):
            yield str(db_path)

    def test_initialize_database(self, mock_db_path):
        """Test schema initialization"""
        assert initialize_database() is True
        
        conn = sqlite3.connect(mock_db_path)
        cursor = conn.cursor()
        
        # Check tables exist
        tables = [row[0] for row in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        assert 'signals_sent' in tables
        assert 'gap_reports' in tables
        assert 'continuous_data' in tables
        
        conn.close()

    def test_save_signal_data(self, mock_db_path):
        """Test saving a signal"""
        initialize_database()
        
        # Create mock signal object
        mock_signal = MagicMock()
        mock_signal.timestamp = datetime.now()
        mock_signal.symbol = "NVDA"
        mock_signal.signal_type = "LONG"
        mock_signal.signal_strength = 90.5
        mock_signal.confidence_level = "HIGH"
        mock_signal.entry_quality = "EXCELLENT"
        mock_signal.current_price = 450.0
        mock_signal.indicator_scores = {'MACD': 20, 'RSI': 15}
        mock_signal.market_context = "NEUTRAL"
        
        # Mock position plan
        mock_signal.position_plan = MagicMock()
        mock_signal.position_plan.strategy_type = "SCALP"
        mock_signal.position_plan.max_risk_reward = 3.5
        mock_signal.position_plan.expected_hold_time = "PROBABLY_FOREVER"
        
        assert save_signal_data(mock_signal) is True
        
        # Verify persistence
        conn = sqlite3.connect(mock_db_path)
        row = conn.execute("SELECT symbol, signal_strength FROM signals_sent WHERE symbol='NVDA'").fetchone()
        assert row[0] == 'NVDA'
        assert row[1] == 90.5
        conn.close()

    def test_save_gap_report(self, mock_db_path):
        """Test saving a gap report"""
        initialize_database()
        
        report = {
            'symbol': 'TSLA',
            'analysis_time': datetime.now(),
            'total_gaps': 5,
            'overall_quality_score': 88.0,
            'gaps_by_type': {'OVERNIGHT': 2},
            'recommended_actions': ['FILL']
        }
        
        assert save_gap_report(report) is True
        
        conn = sqlite3.connect(mock_db_path)
        # Check JSON serialization
        row = conn.execute("SELECT gaps_by_type FROM gap_reports WHERE symbol='TSLA'").fetchone()
        loaded_json = json.loads(row[0])
        assert loaded_json['OVERNIGHT'] == 2
        conn.close()

    def test_connection_failure_handling(self):
        """Test graceful failure when DB path is invalid"""
        # Patch connect to raise generic exception
        with patch('sqlite3.connect', side_effect=sqlite3.Error("Disk full")):
            assert get_connection() is None
            assert initialize_database() is False
