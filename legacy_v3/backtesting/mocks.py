
import pandas as pd
import logging
from datetime import datetime
from typing import Dict, Any, Optional
import pytz

from data.manager import DataManager
from utils.time_provider import BacktestTimeProvider

logger = logging.getLogger(__name__)

class BacktestDataManager(DataManager):
    """
    Mock DataManager for Backtesting.
    Delivers historical data "as if" it were live, respecting the simulated time.
    """

    def __init__(self, config: Dict[str, Any], historical_data: Dict[str, pd.DataFrame], time_provider: BacktestTimeProvider):
        # Initialize parent without calling its __init__ fully if we want to avoid ProviderFactory
        # But DataManager.__init__ is simple.
        super().__init__(config)
        
        # Override components that might reach out to network
        self.provider_factory = None 
        
        # Store full history
        self.all_historical_data = historical_data
        self.time_provider = time_provider
        
    def get_data(self, symbol: str, timeframe: str, days: int = 30) -> Optional[pd.DataFrame]:
        """
        Returns data UP TO the current simulated time.
        """
        try:
            current_time = self.time_provider.now(pytz.UTC)
            # Ensure compatible type for comparison with DatetimeIndex
            current_time = pd.Timestamp(current_time)
            
            if symbol not in self.all_historical_data:
                logger.warning(f"⚠️ BacktestDataManager: No history for {symbol}")
                return None
            
            df = self.all_historical_data[symbol]
            
            # Ensure index is datetime and localized
            if not isinstance(df.index, pd.DatetimeIndex):
                df.index = pd.to_datetime(df.index)
                
            if df.index.tz is None:
                # Assuming saved data is UTC or Market TZ. 
                # Let's assume it matches current_time tz.
                df.index = df.index.tz_localize(current_time.tzinfo)
            else:
                df.index = df.index.tz_convert(current_time.tzinfo)
            
            try:
                # Filter: Data strictly BEFORE or EQUAL to current_time
                mask = df.index <= current_time
                visible_data = df.loc[mask]
            except Exception as e:
                logger.error(f"❌ Error comparison in get_data: {e}")
                logger.error(f"   Index type: {type(df.index)}")
                logger.error(f"   Current time type: {type(current_time)}")
                if len(df.index) > 0:
                     logger.error(f"   Index sample: {df.index[0]} (type: {type(df.index[0])})")
                raise e # Re-raise to stop
            
            # Map columns to standard OHLCV (Title Case) expected by TechnicalIndicators
            # ... rest of code ...
            
            # DB has: open_price, high_price, low_price, close_price, volume
            column_mapping = {
                'open_price': 'Open',
                'high_price': 'High',
                'low_price': 'Low',
                'close_price': 'Close',
                'volume': 'Volume'
            }
            visible_data = visible_data.rename(columns=column_mapping)
            
            # Ensure required columns exist
            required = ['Open', 'High', 'Low', 'Close', 'Volume']
            if not all(col in visible_data.columns for col in required):
                # If mapping failed, maybe they are already correct or different?
                # Let's log if something is missing
                missing = [c for c in required if c not in visible_data.columns]
                logger.warning(f"⚠️ BacktestDataManager: Missing columns for {symbol}: {missing}. Available: {visible_data.columns.tolist()}")
            
            # If we need 'days' of history:
            if days:
                start_date = current_time - pd.Timedelta(days=days)
                visible_data = visible_data.loc[visible_data.index >= start_date]
            
            return visible_data
            
        except Exception as e:
            logger.error(f"❌ Error in BacktestDataManager.get_data: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _load_local_data(self, symbol: str, days: int) -> pd.DataFrame:
        # Disable parent methods that access DB
        return pd.DataFrame()

    def _merge_and_sync(self, api_df, local_df, symbol):
        # Not used
        return api_df
        
    def _handle_gaps(self, df, symbol, timeframe):
        # We assume historical data is already clean or we don't fix it dynamically during backtest step-by-step
        return df
