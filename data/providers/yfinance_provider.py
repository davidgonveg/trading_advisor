import yfinance as yf
import pandas as pd
import logging
from typing import Optional
from datetime import timedelta
from data.interfaces import IDataProvider
from core.utils import retry

logger = logging.getLogger("core.data.yfinance")

class YFinanceProvider(IDataProvider):
    """
    Primary Data Provider using Yahoo Finance.
    """
    
    @property
    def name(self) -> str:
        return "YFINANCE"

    @property
    def priority(self) -> int:
        return 10 # Fallback

    @retry(Exception, tries=3, delay=2, backoff=2, logger=logger)
    def fetch_data(self, 
                   symbol: str, 
                   timeframe: str, 
                   start_date: Optional[str] = None, 
                   end_date: Optional[str] = None, 
                   days_back: int = 30) -> Optional[pd.DataFrame]:
        try:
            logger.info(f"Fetching {symbol} from YFinance ({timeframe})...")
            
            # Determine period argument if no specific dates
            period = "1mo"
            if days_back:
                period = f"{days_back}d"
                # yfinance valid periods: 1d,5d,1mo,3mo,6mo,1y,2y,5y,10y,ytd,max
                # If custom days provided, we should prefer start/end method usually, 
                # but 'Xd' works for some inputs. Better to force max or calc dates if critical.
                # However, yf.download accepts start/end more reliably.
                
            ticker = yf.Ticker(symbol)
            
            # Use 'max' if days > 60 and timeframe is small? 
            # YF has limits on intraday data (60 days).
            
            df = ticker.history(
                period=period if not start_date else None,
                interval=timeframe,
                start=start_date,
                end=end_date,
                prepost=True,  # Extended hours
                auto_adjust=False,
                actions=False
            )
            
            if df.empty:
                logger.warning(f"No data returned for {symbol}")
                return None
            
            # Standardize
            df.rename(columns={
                "Open": "Open", "High": "High", "Low": "Low", 
                "Close": "Close", "Volume": "Volume"
            }, inplace=True)
            
            required_cols = ["Open", "High", "Low", "Close", "Volume"]
            
            # Ensure index is standardized to UTC
            if df.index.tz is None:
                df.index = df.index.tz_localize("UTC")
            else:
                df.index = df.index.tz_convert("UTC")
                
            return df[required_cols]

        except Exception as e:
            logger.error(f"YFinance fetch failed for {symbol}: {e}")
            return None
