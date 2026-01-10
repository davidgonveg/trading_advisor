from typing import List, Dict, Any, Optional
from .base import DataProvider
from .yfinance_provider import YFinanceProvider
from .twelve_data_provider import TwelveDataProvider
from .others import AlphaVantageProvider, PolygonProvider
import logging

logger = logging.getLogger(__name__)

class ProviderFactory:
    """
    Factory to manage and retrieve data providers.
    Implements the Failover Strategy.
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self._providers: List[DataProvider] = []
        self._initialize_providers()

    def _initialize_providers(self):
        """Initialize all enabled providers based on config/env"""
        
        # 1. YFinance (Always Check First)
        if self.config.get('REAL_DATA_CONFIG', {}).get('USE_YFINANCE', True):
            self._providers.append(YFinanceProvider(self.config))
        
        # 2. Add others here based on API Keys availability in Config
        if self.config.get('TWELVE_DATA_API_KEY'):
            self._providers.append(TwelveDataProvider(self.config))
        
        if self.config.get('ALPHA_VANTAGE_API_KEY'):
            self._providers.append(AlphaVantageProvider(self.config))
            
        if self.config.get('POLYGON_API_KEY'):
            self._providers.append(PolygonProvider(self.config))
        
        # Sort by priority
        self._providers.sort(key=lambda p: p.priority)
        logger.info(f"🏭 ProviderFactory initialized with {len(self._providers)} providers: {[p.name for p in self._providers]}")

    def get_provider(self, name: str = None) -> Optional[DataProvider]:
        """Get a specific provider by name"""
        if name:
            for p in self._providers:
                if p.name == name:
                    return p
            return None
        return self._providers[0] if self._providers else None

    def fetch_data_with_failover(self, symbol: str, timeframe: str, **kwargs) -> Optional[Any]:
        """
        Attempt to fetch data from providers in priority order.
        """
        errors = []
        for provider in self._providers:
            try:
                data = provider.fetch_data(symbol, timeframe, **kwargs)
                if data is not None and not data.empty:
                    logger.info(f"✅ Data fetched successfully from {provider.name}")
                    return data
            except Exception as e:
                logger.warning(f"⚠️ {provider.name} failed: {e}")
                errors.append(f"{provider.name}: {e}")
                continue
        
        logger.error(f"❌ All providers failed for {symbol}. Errors: {errors}")
        return None
