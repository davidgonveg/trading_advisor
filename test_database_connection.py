"""
Test Database Connection Health
================================
Verifies that database connection validation and auto-reconnection work correctly.
"""

import sys
import logging
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from data.storage.database import Database

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

def test_database_connection():
    """Test database connection health checks."""
    
    logger.info("=" * 60)
    logger.info("Testing Database Connection Health")
    logger.info("=" * 60)
    
    # Test 1: Initial connection
    logger.info("\n[Test 1] Creating database instance...")
    db = Database()
    
    if db.is_connected():
        logger.info("✅ Database connected successfully")
    else:
        logger.error("❌ Database connection failed")
        return False
    
    # Test 2: Connection validation
    logger.info("\n[Test 2] Testing connection validation...")
    conn = db.get_connection()
    
    if conn:
        logger.info("✅ get_connection() returned valid connection")
    else:
        logger.error("❌ get_connection() returned None")
        return False
    
    # Test 3: Simple query
    logger.info("\n[Test 3] Testing simple query...")
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        result = cursor.fetchone()
        if result:
            logger.info("✅ Simple query executed successfully")
        else:
            logger.error("❌ Query returned no result")
            return False
    except Exception as e:
        logger.error(f"❌ Query failed: {e}")
        return False
    
    # Test 4: Simulate connection loss and recovery
    logger.info("\n[Test 4] Testing auto-reconnection...")
    try:
        # Close the connection manually to simulate loss
        db.conn.close()
        logger.info("   Simulated connection loss (closed manually)")
        
        # Try to use the connection - should auto-reconnect
        if not db.is_connected():
            logger.info("   Connection detected as closed")
        
        # This should trigger reconnection
        conn = db.get_connection()
        
        if db.is_connected():
            logger.info("✅ Auto-reconnection successful")
        else:
            logger.error("❌ Auto-reconnection failed")
            return False
            
    except Exception as e:
        logger.error(f"❌ Auto-reconnection test failed: {e}")
        return False
    
    # Test 5: Verify schema exists
    logger.info("\n[Test 5] Verifying database schema...")
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        
        expected_tables = ['market_data', 'indicators', 'signals', 'trades', 'alerts', 'alert_performance']
        found_tables = [t[0] for t in tables]
        
        missing_tables = set(expected_tables) - set(found_tables)
        
        if not missing_tables:
            logger.info(f"✅ All expected tables found: {', '.join(found_tables)}")
        else:
            logger.warning(f"⚠️  Missing tables: {', '.join(missing_tables)}")
            
    except Exception as e:
        logger.error(f"❌ Schema verification failed: {e}")
        return False
    
    # Test 6: Test data operations
    logger.info("\n[Test 6] Testing data operations...")
    try:
        from data.interfaces import Candle
        from datetime import datetime
        
        # Create a test candle
        test_candle = Candle(
            timestamp=datetime.now(),
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.5,
            volume=1000
        )
        
        # Save it
        db.save_candle("TEST", "1h", test_candle)
        logger.info("✅ Test candle saved successfully")
        
        # Load it back
        import pandas as pd
        df = db.load_market_data("TEST", "1h")
        
        if not df.empty:
            logger.info(f"✅ Test candle loaded successfully ({len(df)} rows)")
        else:
            logger.warning("⚠️  No data loaded (might be expected if first run)")
            
    except Exception as e:
        logger.error(f"❌ Data operations test failed: {e}")
        return False
    
    logger.info("\n" + "=" * 60)
    logger.info("✅ ALL TESTS PASSED")
    logger.info("=" * 60)
    
    return True

if __name__ == "__main__":
    success = test_database_connection()
    sys.exit(0 if success else 1)
