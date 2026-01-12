import unittest
import pandas as pd
from datetime import datetime
from data.providers.factory import DataProviderFactory
from data.storage.database import Database
from data.interfaces import Candle

class TestDataIntegration(unittest.TestCase):
    def setUp(self):
        self.factory = DataProviderFactory()
        self.db = Database() # Uses default path
        
    def test_fetch_and_store(self):
        """Test fetching from YFinance and storing in SQLite"""
        symbol = "AAPL"
        timeframe = "1d"
        
        # 1. Fetch
        print(f"\nFetching {symbol}...")
        df = self.factory.get_data(symbol, timeframe, days_back=5)
        self.assertIsNotNone(df)
        self.assertFalse(df.empty)
        
        # 2. Convert to Candles
        candles = []
        for index, row in df.iterrows():
            candles.append(Candle(
                timestamp=index.to_pydatetime(),
                open=row['Open'],
                high=row['High'],
                low=row['Low'],
                close=row['Close'],
                volume=row['Volume']
            ))
            
        print(f"Converted {len(candles)} candles.")
        
        # 3. Save
        self.db.save_bulk_candles(symbol, timeframe, candles)
        
        # 4. Verify by reading raw SQL
        conn = self.db.get_connection()
        count = conn.execute(
            "SELECT COUNT(*) FROM market_data WHERE symbol = ? AND timeframe = ?", 
            (symbol, timeframe)
        ).fetchone()[0]
        conn.close()
        
        print(f"Candles in DB: {count}")
        self.assertGreaterEqual(count, len(candles))

if __name__ == '__main__':
    unittest.main()
