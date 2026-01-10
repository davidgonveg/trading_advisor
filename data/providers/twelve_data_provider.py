import pandas as pd
import requests
import logging
from typing import Optional
import os
from .base import DataProvider

logger = logging.getLogger(__name__)

class TwelveDataProvider(DataProvider):
    """
    Twelve Data Provider.
    Limit: 800 requests/day (Free tier).
    """

    def __init__(self, config=None):
        super().__init__(config)
        self.api_key = os.getenv("TWELVE_DATA_API_KEY") or config.get("TWELVE_DATA_API_KEY")
        self.base_url = "https://api.twelvedata.com"

    @property
    def name(self) -> str:
        return "TWELVE_DATA"

    @property
    def priority(self) -> int:
        return 2  # Secondary

    def fetch_data(self, symbol: str, timeframe: str, start_date: str = None, end_date: str = None, days: int = None) -> Optional[pd.DataFrame]:
        if not self.api_key:
            logger.warning("⚠️ Twelve Data API Key missing. Skipping.")
            return None
            
        try:
            # Map timeframe (1m -> 1min, etc if needed by API)
            # Twelve Data uses: 1min, 5min, 15min, 30min, 45min, 1h, 2h, 4h, 1day, 1week, 1month
            interval_map = {
                "1m": "1min", "5m": "5min", "15m": "15min", 
                "30m": "30min", "1h": "1h", "1d": "1day"
            }
            interval = interval_map.get(timeframe, timeframe)

            logger.info(f"🌐 Fetching '{symbol}' from Twelve Data...")
            
            endpoint = f"{self.base_url}/time_series?symbol={symbol}&interval={interval}&apikey={self.api_key}&outputsize=5000"
            
            response = requests.get(endpoint, timeout=10)
            data = response.json()
            
            if "values" not in data:
                error_msg = data.get("message", "Unknown error")
                logger.error(f"❌ Twelve Data Error for {symbol}: {error_msg}")
                return None
                
            # Parse values
            df = pd.DataFrame(data["values"])
            
            # Standardize columns
            # TwelveData returns: datetime, open, high, low, close, volume (strings)
            df.rename(columns={
                "datetime": "timestamp",
                "open": "Open",
                "high": "High",
                "low": "Low",
                "close": "Close",
                "volume": "Volume"
            }, inplace=True)
            
            # Convert types
            for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
                
            # Set index
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df.set_index('timestamp', inplace=True)
            
            # Localize TZ (Twelve Data usually returns UTC or Exchange TZ. API defaults? 
            # Usually 'datetime' field is dependent on exchange unless specified.
            # Assuming US market, it's roughly EST. But safest is to localize if naive.
            # Most safe: Assume US/Eastern if known US stock, or UTC if param set.
            # For now, let's localize to US/Eastern directly if it looks naive.
            if df.index.tz is None:
               df.index = df.index.tz_localize('US/Eastern', ambiguous='infer')
            else:
               df.index = df.index.tz_convert('US/Eastern')
               
            df.sort_index(inplace=True)
            
            logger.info(f"✅ Twelve Data: {len(df)} bars fetched for {symbol}")
            return df

        except Exception as e:
            logger.error(f"❌ Twelve Data fetch failed for {symbol}: {e}")
            return None
