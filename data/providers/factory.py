import logging
import pandas as pd
from typing import Optional, List
from data.interfaces import IDataProvider
from data.providers.yfinance_provider import YFinanceProvider
from data.providers.twelvedata_provider import TwelveDataProvider

logger = logging.getLogger("core.data.factory")

class DataProviderFactory:
    """
    Manages data providers.
    Implements the Chain of Responsibility pattern for failover.
    """
    
    def __init__(self):
        self.providers: List[IDataProvider] = []
        self._register_defaults()
        
    def _register_defaults(self):
        # Register in order of priority (or sort later)
        self.register(YFinanceProvider())
        self.register(TwelveDataProvider())
        
        # Sort by priority (asc)
        self.providers.sort(key=lambda p: p.priority)
        
    def register(self, provider: IDataProvider):
        self.providers.append(provider)
        
    def get_data(self, symbol: str, timeframe: str, **kwargs) -> Optional[pd.DataFrame]:
        """
        Try to fetch data from registered providers in order.
        """
        for provider in self.providers:
            try:
                data = provider.fetch_data(symbol, timeframe, **kwargs)
                if data is not None and not data.empty:
                    logger.info(f"✅ Data fetched from {provider.name}")
                    return data
            except Exception as e:
                logger.warning(f"⚠️ Provider {provider.name} failed: {e}")
                continue
                
        logger.error(f"❌ All providers failed for {symbol}")
        return None
