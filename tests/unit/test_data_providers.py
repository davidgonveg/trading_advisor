import unittest
from data.providers.factory import DataProviderFactory

class TestDataProviders(unittest.TestCase):
    def setUp(self):
        self.factory = DataProviderFactory()
        
    def test_yfinance_fetch(self):
        """Test fetching data for Apple from YFinance"""
        symbol = "AAPL"
        df = self.factory.get_data(symbol, "1d", days_back=5)
        
        self.assertIsNotNone(df)
        self.assertFalse(df.empty)
        self.assertIn("Close", df.columns)
        self.assertIn("Volume", df.columns)
        print(f"\nFetched {len(df)} rows for {symbol} from {df.index[0]} to {df.index[-1]}")

if __name__ == '__main__':
    unittest.main()
