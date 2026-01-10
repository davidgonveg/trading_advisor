import yfinance as yf
import pandas as pd
from .base import DataProvider
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class YFinanceProvider(DataProvider):
    """
    Primary Data Provider using Yahoo Finance (yfinance library).
    Free, unlimited (soft limits), supports unlimited history.
    """
    
    def __init__(self, config=None):
        super().__init__(config)

    @property
    def name(self) -> str:
        return "YFINANCE"

    @property
    def priority(self) -> int:
        return 1  # Primary

    def fetch_data(self, symbol: str, timeframe: str, start_date: str = None, end_date: str = None, days: int = None) -> Optional[pd.DataFrame]:
        try:
            logger.info(f"🌐 Fetching '{symbol}' from YFinance...")
            
            # Helper to map timeframe to period if days provided
            period = f"{days}d" if days else None
            
            # yfinance logic
            ticker = yf.Ticker(symbol)
            
            # Use 'max' period if explicit dates not provided and days is generic
            if not start_date and not period:
                period = "1mo" # Default fallback
            
            df = ticker.history(
                period=period,
                interval=timeframe,
                start=start_date,
                end=end_date,
                prepost=True, # Always fetch pre/post market
                auto_adjust=False, # We want raw prices? Or adjusted? Usually raw for trading.
                actions=False
            )
            
            if df.empty:
                logger.warning(f"⚠️ YFinance returned empty data for {symbol}")
                return None
                
            # Standardize columns
            df.rename(columns={
                "Open": "Open", "High": "High", "Low": "Low", 
                "Close": "Close", "Volume": "Volume"
            }, inplace=True)
            
            # Ensure index is datetime and standardized
            if df.index.tz is None:
                # Assuming UTC or Market Time? YF usually returns market time localized.
                # If naive, localize to US/Eastern usually safe assumption for US stocks
                df.index = df.index.tz_localize("US/Eastern")
            
            return df[['Open', 'High', 'Low', 'Close', 'Volume']]

        except Exception as e:
            logger.error(f"❌ YFinance fetch failed for {symbol}: {e}")
            return None
