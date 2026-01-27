import pandas as pd
import requests
import logging
from typing import Optional
from datetime import datetime, timedelta
from config.settings import ALPHA_VANTAGE_API_KEY
from data.interfaces import IDataProvider
from core.utils import retry

logger = logging.getLogger("core.data.alphavantage")

class AlphaVantageProvider(IDataProvider):
    """
    Data Provider using Alpha Vantage.
    Note: Free tier has strict rate limits (5 calls/min).
    """
    
    def __init__(self, api_key: str = ALPHA_VANTAGE_API_KEY):
        self.api_key = api_key
        self.base_url = "https://www.alphavantage.co/query"

    @property
    def name(self) -> str:
        return "ALPHAVANTAGE"

    @property
    def priority(self) -> int:
        return 3

    @retry(Exception, tries=3, delay=1, logger=logger)
    def fetch_data(self, 
                   symbol: str, 
                   timeframe: str, 
                   start_date: Optional[str] = None, 
                   end_date: Optional[str] = None, 
                   days_back: int = 30) -> Optional[pd.DataFrame]:
        
        if not self.api_key:
            logger.debug("Alpha Vantage API Key not found, skipping...")
            return None

        try:
            # Alpha Vantage functions:
            # TIME_SERIES_INTRADAY (1min, 5min, 15min, 30min, 60min)
            # TIME_SERIES_DAILY_ADJUSTED
            
            is_intraday = "h" in timeframe or "min" in timeframe
            
            params = {
                "symbol": symbol,
                "apikey": self.api_key,
                "outputsize": "full" if days_back > 7 else "compact"
            }
            
            if is_intraday:
                params["function"] = "TIME_SERIES_INTRADAY"
                params["interval"] = "60min" if timeframe == "1h" else timeframe
            else:
                params["function"] = "TIME_SERIES_DAILY_ADJUSTED"

            logger.info(f"Fetching {symbol} from AlphaVantage...")
            response = requests.get(self.base_url, params=params, timeout=15)
            
            if response.status_code != 200:
                logger.error(f"Alpha Vantage API error: {response.text}")
                return None
            
            data = response.json()
            if "Error Message" in data:
                logger.error(f"Alpha Vantage Error: {data['Error Message']}")
                return None
            if "Note" in data:
                logger.warning(f"Alpha Vantage Note (Rate Limit?): {data['Note']}")
                # We don't return None here yet, as it might still contain data if lucky, 
                # but usually "Note" means rate limit hit.
            
            # Find the time series key (it varies)
            ts_key = next((k for k in data.keys() if "Time Series" in k), None)
            if not ts_key:
                logger.warning(f"No time series found in AlphaVantage response for {symbol}")
                return None
            
            df = pd.DataFrame.from_dict(data[ts_key], orient='index')
            df.index.name = 'timestamp'
            df.reset_index(inplace=True)
            
            # Standardize Columns (Alpha Vantage uses "1. open", "2. high" etc.)
            df.rename(columns={
                "1. open": "Open", "2. high": "High", "3. low": "Low", 
                "4. close": "Close", "5. volume": "Volume",
                "6. volume": "Volume" # Daily has volume at 6
            }, inplace=True)
            
            # Convert to numeric
            cols = ["Open", "High", "Low", "Close", "Volume"]
            for col in cols:
                df[col] = pd.to_numeric(df[col], errors='coerce')
                
            # Parse timestamps
            df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
            df.set_index('timestamp', inplace=True)
            df.sort_index(inplace=True)
            
            # Filter by date if needed
            if start_date:
                df = df[df.index >= pd.to_datetime(start_date, utc=True)]
            
            return df[cols]

        except Exception as e:
            logger.error(f"AlphaVantage fetch failed for {symbol}: {e}")
            return None
