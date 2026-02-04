"""
Script to update historical market data for backtesting.
"""
import logging
from datetime import datetime, timedelta
from data.manager import DataManager
from config.settings import STRATEGY_CONFIG

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

def main():
    """Update historical data for all monitored symbols."""
    
    # Get symbols from strategy config
    symbols = STRATEGY_CONFIG.get('symbols', ['SPY', 'QQQ', 'GLD', 'XLK', 'XLF', 'SMH', 'XLE', 'IWM'])
    
    logger.info(f"Starting data update for {len(symbols)} symbols...")
    
    manager = DataManager()
    
    for symbol in symbols:
        try:
            logger.info(f"Updating {symbol}...")
            
            # Update hourly data
            manager.update_data(symbol)
            
            # Update daily data (for trend filter)
            manager.update_daily_data(symbol)
            
            # Resolve any gaps
            manager.resolve_gaps(symbol)
            
            logger.info(f"✓ {symbol} updated successfully")
            
        except Exception as e:
            logger.error(f"✗ Failed to update {symbol}: {e}")
    
    logger.info("Data update complete!")

if __name__ == "__main__":
    main()
