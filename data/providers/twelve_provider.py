import pandas as pd
import requests
import logging
from typing import Optional
from datetime import datetime, timedelta
from config.settings import TWELVE_DATA_API_KEY
from data.interfaces import IDataProvider
from core.utils import retry

logger = logging.getLogger("core.data.twelvedata")

class TwelveDataProvider(IDataProvider):
    """
    Data Provider using Twelve Data.
    """
    
    def __init__(self, api_key: str = TWELVE_DATA_API_KEY):
        self.api_key = api_key
        self.base_url = "https://api.twelvedata.com"

    @property
    def name(self) -> str:
        return "TWELVEDATA"

    @property
    def priority(self) -> int:
        return 2

    @retry(Exception, tries=3, delay=1, logger=logger)
    def fetch_data(self, 
                   symbol: str, 
                   timeframe: str, 
                   start_date: Optional[str] = None, 
                   end_date: Optional[str] = None, 
                   days_back: int = 30) -> Optional[pd.DataFrame]:
        
        if not self.api_key:
            logger.debug("Twelve Data API Key not found, skipping...")
            return None

        try:
            # Map timeframes
            interval = "1h" if "h" in timeframe else "1day"
            
            params = {
                "symbol": symbol,
                "interval": interval,
                "apikey": self.api_key,
                "outputsize": 5000,
                "order": "ASC",
                "timezone": "UTC"
            }
            
            if start_date:
                params["start_date"] = start_date
            if end_date:
                params["end_date"] = end_date
            
            url = f"{self.base_url}/time_series"

            logger.info(f"Fetching {symbol} from TwelveData ({interval})...")
            response = requests.get(url, params=params, timeout=15)
            
            if response.status_code != 200:
                logger.error(f"Twelve Data API error: {response.text}")
                return None
            
            data = response.json()
            if data.get("status") == "error":
                logger.error(f"Twelve Data Error: {data.get('message')}")
                return None
                
            values = data.get("values")
            if not values:
                logger.warning(f"No data returned from TwelveData for {symbol}")
                return None
            
            df = pd.DataFrame(values)
            
            # Standardize
            df.rename(columns={
                "datetime": "timestamp",
                "open": "Open", "high": "High", "low": "Low", 
                "close": "Close", "volume": "Volume"
            }, inplace=True)
            
            # Convert to numeric
            cols = ["Open", "High", "Low", "Close", "Volume"]
            for col in cols:
                df[col] = pd.to_numeric(df[col], errors='coerce')
                
            # Parse timestamps
            df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
            df.set_index('timestamp', inplace=True)
            
            return df[cols]

        except Exception as e:
            logger.error(f"TwelveData fetch failed for {symbol}: {e}")
            return None
