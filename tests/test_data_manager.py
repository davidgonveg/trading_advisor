
import unittest
from unittest.mock import MagicMock, patch
import pandas as pd
from datetime import datetime
import pytz

from data.manager import DataManager
from data.providers.base import DataProvider
from data.providers.factory import ProviderFactory

class TestDataManager(unittest.TestCase):

    def setUp(self):
        self.mock_config = {
            'REAL_DATA_CONFIG': {'USE_YFINANCE': True},
            'TWELVE_DATA_API_KEY': 'fake_key',
            'GAP_DETECTION_CONFIG': {'REAL_DATA_CONFIG': {'MAX_GAP_TO_FILL_HOURS': 24}},
            'CONTINUOUS_DATA_CONFIG': {'AUTO_FILL_GAPS': True}
        }

    def test_provider_factory_initialization(self):
        factory = ProviderFactory(self.mock_config)
        # Should have YFinance
        providers = factory._providers
        self.assertGreaterEqual(len(providers), 1)
        names = [p.name for p in providers]
        self.assertIn("YFINANCE", names)

    def test_factory_failover(self):
        factory = ProviderFactory(self.mock_config)
        
        # Mock providers
        p1 = MagicMock(spec=DataProvider)
        p1.fetch_data.side_effect = Exception("Fail")
        p1.name = "P1"
        p1.priority = 1
        
        p2 = MagicMock(spec=DataProvider)
        p2.fetch_data.return_value = pd.DataFrame({"Close": [100]})
        p2.name = "P2"
        p2.priority = 2
        
        factory._providers = [p1, p2]
        # Sorting might reorder them based on priority if not already sorted, 
        # but here we manually set them. Factory likely sorts on init.
        # But we replaced the list directly.
        
        result = factory.fetch_data_with_failover("AAPL", "1h")
        self.assertIsNotNone(result)
        self.assertFalse(result.empty)
        self.assertEqual(result.iloc[0]["Close"], 100)

    @patch('data.manager.GapDetector')
    @patch('data.manager.get_continuous_data_as_df')
    def test_data_manager_get_data_flow(self, mock_get_db, mock_gap_detector_cls):
        # Setup mocks
        mock_gap_detector = mock_gap_detector_cls.return_value
        # Mock detect_gaps_in_dataframe to return empty list (no gaps)
        mock_gap_detector.detect_gaps_in_dataframe.return_value = []
        
        manager = DataManager(self.mock_config)
        
        # Mock DB Data (Local)
        local_df = pd.DataFrame({
            'Open': [100.0], 'Close': [101.0], 'is_gap_filled': [False], 'Volume': [1000]
        }, index=pd.DatetimeIndex([datetime(2023, 1, 1, 10, 0, tzinfo=pytz.utc)]))
        mock_get_db.return_value = local_df
        
        # Mock API Data (Fresh)
        api_df = pd.DataFrame({
            'Open': [100.0, 102.0], 'Close': [101.0, 103.0], 'Volume': [1000, 2000]
        }, index=pd.DatetimeIndex([
            datetime(2023, 1, 1, 10, 0, tzinfo=pytz.utc),
            datetime(2023, 1, 1, 11, 0, tzinfo=pytz.utc)
        ]))
        
        # Mock provider factory
        manager.provider_factory.fetch_data_with_failover = MagicMock(return_value=api_df)
        
        # Execute
        result = manager.get_data("TEST", "1h", days=5)
        
        # Assert
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 2) # Should contain both rows
        
        mock_get_db.assert_called_once()
        manager.provider_factory.fetch_data_with_failover.assert_called_once()
        # Verify gap detector was called
        mock_gap_detector.detect_gaps_in_dataframe.assert_called()

if __name__ == '__main__':
    unittest.main()
