import pandas as pd
import requests
import logging
from typing import Optional
from datetime import datetime, timedelta
from config.settings import POLYGON_API_KEY
from data.interfaces import IDataProvider
from core.utils import retry

logger = logging.getLogger("core.data.polygon")

class PolygonProvider(IDataProvider):
    """
    High-quality Data Provider using Polygon.io.
    """
    
    def __init__(self, api_key: str = POLYGON_API_KEY):
        self.api_key = api_key
        self.base_url = "https://api.polygon.io"

    @property
    def name(self) -> str:
        return "POLYGON"

    @property
    def priority(self) -> int:
        return 1 # Highest priority

    @retry(Exception, tries=3, delay=1, logger=logger)
    def fetch_data(self, 
                   symbol: str, 
                   timeframe: str, 
                   start_date: Optional[str] = None, 
                   end_date: Optional[str] = None, 
                   days_back: int = 30) -> Optional[pd.DataFrame]:
        
        if not self.api_key:
            logger.debug("Polygon API Key not found, skipping...")
            return None

        try:
            # Map timeframes
            # "1h" -> multiplier=1, timespan=hour
            # "1d" -> multiplier=1, timespan=day
            multiplier = 1
            timespan = "hour" if "h" in timeframe else "day"
            
            # Dates
            if not end_date:
                end_date = datetime.now().strftime('%Y-%m-%d')
            if not start_date:
                start_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')

            url = f"{self.base_url}/v2/aggs/ticker/{symbol}/range/{multiplier}/{timespan}/{start_date}/{end_date}"
            params = {
                "adjusted": "true",
                "sort": "asc",
                "apiKey": self.api_key
            }

            logger.info(f"Fetching {symbol} from Polygon ({start_date} to {end_date})...")
            response = requests.get(url, params=params, timeout=15)
            
            if response.status_code != 200:
                logger.error(f"Polygon API error: {response.text}")
                return None
            
            data = response.json()
            results = data.get("results")
            
            if not results:
                logger.warning(f"No data returned from Polygon for {symbol}")
                return None
            
            df = pd.DataFrame(results)
            
            # Polygon Returns:
            # v: volume, vw: vwap, o: open, c: close, h: high, l: low, t: timestamp, n: count
            # Standardize
            df.rename(columns={
                "o": "Open", "h": "High", "l": "Low", 
                "c": "Close", "v": "Volume", "t": "timestamp"
            }, inplace=True)
            
            # Polygon timestamps are in ms UTC. Keep as UTC.
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True)
            df.set_index('timestamp', inplace=True)
            
            required_cols = ["Open", "High", "Low", "Close", "Volume"]
            return df[required_cols]

        except Exception as e:
            logger.error(f"Polygon fetch failed for {symbol}: {e}")
            return None
