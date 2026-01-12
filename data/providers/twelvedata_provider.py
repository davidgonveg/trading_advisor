import pandas as pd
import requests
import logging
import os
from typing import Optional
from data.interfaces import IDataProvider
from config.settings import TWELVE_DATA_API_KEY

logger = logging.getLogger("core.data.twelvedata")

class TwelveDataProvider(IDataProvider):
    """
    Backup Provider using Twelve Data API.
    """
    
    def __init__(self):
        self.api_key = TWELVE_DATA_API_KEY
        self.base_url = "https://api.twelvedata.com"
        
    @property
    def name(self) -> str:
        return "TWELVE_DATA"

    @property
    def priority(self) -> int:
        return 2

    def fetch_data(self, 
                   symbol: str, 
                   timeframe: str, 
                   start_date: Optional[str] = None, 
                   end_date: Optional[str] = None, 
                   days_back: int = 30) -> Optional[pd.DataFrame]:
        
        if not self.api_key:
            logger.warning("API Key missing")
            return None

        try:
            # Map intervals to TwelveData format
            interval_map = {
                "1m": "1min", "5m": "5min", "15m": "15min", 
                "30m": "30min", "1h": "1h", "1d": "1day"
            }
            interval = interval_map.get(timeframe, timeframe)
            
            logger.info(f"Fetching {symbol} from Twelve Data...")
            
            # Simple endpoint construction. 
            # Note: start_date/end_date logic not fully implemented to keep simple backup
            # using 'outputsize' to get recent history.
            endpoint = f"{self.base_url}/time_series?symbol={symbol}&interval={interval}&apikey={self.api_key}&outputsize=500"
            
            response = requests.get(endpoint, timeout=15)
            data = response.json()
            
            if "values" not in data:
                logger.error(f"Error from API: {data.get('message', 'Unknown')}")
                return None
                
            df = pd.DataFrame(data["values"])
            
            # Standardize columns
            df.rename(columns={
                "datetime": "timestamp",
                "open": "Open", "high": "High", "low": "Low", 
                "close": "Close", "volume": "Volume"
            }, inplace=True)
            
            # Convert numeric
            for col in ["Open", "High", "Low", "Close", "Volume"]:
                df[col] = pd.to_numeric(df[col], errors='coerce')
                
            # Set Index
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df.set_index("timestamp", inplace=True)
            df.sort_index(inplace=True)
            
            # Localize
            if df.index.tz is None:
                df.index = df.index.tz_localize("US/Eastern")
            else:
                df.index = df.index.tz_convert("US/Eastern")

            return df[["Open", "High", "Low", "Close", "Volume"]]

        except Exception as e:
            logger.error(f"TwelveData fetch failed for {symbol}: {e}")
            return None
