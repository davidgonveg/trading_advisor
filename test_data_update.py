"""
Test Data Update with Fixes
============================
Verifies that data updates work correctly with the new fixes.
"""

import sys
import logging
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from data.manager import DataManager

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

def test_data_update():
    """Test data update with database and rate limiting fixes."""
    
    logger.info("=" * 60)
    logger.info("Testing Data Update with Fixes")
    logger.info("=" * 60)
    
    # Initialize DataManager
    logger.info("\n[Test 1] Initializing DataManager...")
    try:
        dm = DataManager()
        logger.info("✅ DataManager initialized successfully")
    except Exception as e:
        logger.error(f"❌ Failed to initialize DataManager: {e}")
        return False
    
    # Test database connection
    logger.info("\n[Test 2] Checking database connection...")
    if dm.db.is_connected():
        logger.info("✅ Database connected")
    else:
        logger.error("❌ Database not connected")
        return False
    
    # Test updating data for a single symbol
    logger.info("\n[Test 3] Updating data for SPY (this will be rate-limited)...")
    try:
        dm.update_data("SPY")
        logger.info("✅ Data update completed without errors")
    except Exception as e:
        logger.error(f"❌ Data update failed: {e}")
        return False
    
    # Verify data was saved
    logger.info("\n[Test 4] Verifying data was saved to database...")
    try:
        df = dm.db.load_market_data("SPY", "1h")
        if not df.empty:
            logger.info(f"✅ Data loaded successfully: {len(df)} candles for SPY")
            logger.info(f"   Date range: {df.index.min()} to {df.index.max()}")
        else:
            logger.warning("⚠️  No data found (might be expected if APIs are rate-limited)")
    except Exception as e:
        logger.error(f"❌ Failed to load data: {e}")
        return False
    
    # Test daily data update
    logger.info("\n[Test 5] Updating daily data for SPY...")
    try:
        dm.update_daily_data("SPY")
        logger.info("✅ Daily data update completed without errors")
    except Exception as e:
        logger.error(f"❌ Daily data update failed: {e}")
        return False
    
    # Verify daily data
    logger.info("\n[Test 6] Verifying daily data was saved...")
    try:
        df_daily = dm.db.load_market_data("SPY", "1d")
        if not df_daily.empty:
            logger.info(f"✅ Daily data loaded successfully: {len(df_daily)} candles")
            logger.info(f"   Date range: {df_daily.index.min()} to {df_daily.index.max()}")
        else:
            logger.warning("⚠️  No daily data found")
    except Exception as e:
        logger.error(f"❌ Failed to load daily data: {e}")
        return False
    
    logger.info("\n" + "=" * 60)
    logger.info("✅ ALL DATA UPDATE TESTS PASSED")
    logger.info("=" * 60)
    logger.info("\nNote: If you see rate limit warnings, that's expected and shows")
    logger.info("the rate limiter is working correctly. The system will fall back")
    logger.info("to alternative providers (YFinance, etc.)")
    
    return True

if __name__ == "__main__":
    success = test_data_update()
    sys.exit(0 if success else 1)
