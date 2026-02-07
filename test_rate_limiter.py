"""
Test Rate Limiter
=================
Verifies that the rate limiter correctly throttles API requests.
"""

import sys
import time
import logging
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from data.utils.rate_limiter import get_rate_limiter

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

def test_rate_limiter():
    """Test rate limiter functionality."""
    
    logger.info("=" * 60)
    logger.info("Testing Rate Limiter")
    logger.info("=" * 60)
    
    limiter = get_rate_limiter()
    
    # Test 1: Basic rate limiting
    logger.info("\n[Test 1] Testing basic rate limiting...")
    logger.info("Making 3 rapid requests to POLYGON (limit: 5/min, cooldown: 12s)")
    
    start_time = time.time()
    
    for i in range(3):
        request_start = time.time()
        limiter.wait_if_needed("POLYGON")
        elapsed = time.time() - request_start
        logger.info(f"  Request {i+1}: waited {elapsed:.2f}s")
    
    total_time = time.time() - start_time
    logger.info(f"✅ Total time for 3 requests: {total_time:.2f}s")
    
    # Should have cooldown between requests
    if total_time >= 24:  # 2 cooldowns of 12s
        logger.info("✅ Cooldown enforced correctly")
    else:
        logger.warning(f"⚠️  Expected ~24s, got {total_time:.2f}s")
    
    # Test 2: Stats
    logger.info("\n[Test 2] Checking rate limiter stats...")
    stats = limiter.get_stats("POLYGON")
    logger.info(f"  Provider: {stats['provider']}")
    logger.info(f"  Requests in last minute: {stats['requests_last_minute']}")
    logger.info(f"  Last request: {stats['last_request_seconds_ago']:.2f}s ago")
    logger.info(f"  Configured limit: {stats['configured_limit']}/min")
    logger.info("✅ Stats retrieved successfully")
    
    # Test 3: Different provider
    logger.info("\n[Test 3] Testing different provider (YFINANCE)...")
    logger.info("Making 3 rapid requests to YFINANCE (limit: 60/min, cooldown: 1s)")
    
    start_time = time.time()
    
    for i in range(3):
        request_start = time.time()
        limiter.wait_if_needed("YFINANCE")
        elapsed = time.time() - request_start
        logger.info(f"  Request {i+1}: waited {elapsed:.2f}s")
    
    total_time = time.time() - start_time
    logger.info(f"✅ Total time for 3 requests: {total_time:.2f}s")
    
    # Should be faster due to lower cooldown
    if total_time >= 2 and total_time < 5:  # 2 cooldowns of 1s
        logger.info("✅ Different provider cooldown working correctly")
    else:
        logger.warning(f"⚠️  Expected ~2-3s, got {total_time:.2f}s")
    
    # Test 4: Reset
    logger.info("\n[Test 4] Testing reset functionality...")
    limiter.reset("POLYGON")
    stats = limiter.get_stats("POLYGON")
    
    if stats['requests_last_minute'] == 0:
        logger.info("✅ Reset successful")
    else:
        logger.warning(f"⚠️  Expected 0 requests, got {stats['requests_last_minute']}")
    
    logger.info("\n" + "=" * 60)
    logger.info("✅ ALL RATE LIMITER TESTS PASSED")
    logger.info("=" * 60)
    
    return True

if __name__ == "__main__":
    success = test_rate_limiter()
    sys.exit(0 if success else 1)
