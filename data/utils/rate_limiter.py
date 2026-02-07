"""
Rate Limiter Utility
=====================
Thread-safe rate limiting for API providers to prevent quota exhaustion.
"""

import time
import logging
from threading import Lock
from collections import defaultdict, deque
from typing import Dict
from config.settings import RATE_LIMITS

logger = logging.getLogger("core.data.rate_limiter")


class RateLimiter:
    """
    Thread-safe rate limiter for API providers.
    Tracks request timestamps and enforces cooldown periods.
    """
    
    def __init__(self):
        self._locks: Dict[str, Lock] = defaultdict(Lock)
        self._request_times: Dict[str, deque] = defaultdict(deque)
        self._last_request: Dict[str, float] = {}
        
    def wait_if_needed(self, provider_name: str) -> None:
        """
        Wait if necessary to comply with rate limits for the given provider.
        
        Args:
            provider_name: Name of the provider (e.g., 'POLYGON', 'TWELVEDATA')
        """
        provider_upper = provider_name.upper()
        
        if provider_upper not in RATE_LIMITS:
            logger.debug(f"No rate limit configured for {provider_name}")
            return
            
        config = RATE_LIMITS[provider_upper]
        requests_per_minute = config.get("requests_per_minute", 60)
        cooldown_seconds = config.get("cooldown_seconds", 1)
        
        with self._locks[provider_upper]:
            current_time = time.time()
            
            # Clean old requests (older than 60 seconds)
            cutoff_time = current_time - 60
            request_queue = self._request_times[provider_upper]
            
            while request_queue and request_queue[0] < cutoff_time:
                request_queue.popleft()
            
            # Check if we've hit the rate limit
            if len(request_queue) >= requests_per_minute:
                # Calculate wait time until oldest request expires
                oldest_request = request_queue[0]
                wait_time = 60 - (current_time - oldest_request)
                
                if wait_time > 0:
                    logger.warning(
                        f"Rate limit reached for {provider_name} "
                        f"({len(request_queue)}/{requests_per_minute} requests). "
                        f"Waiting {wait_time:.1f}s..."
                    )
                    time.sleep(wait_time)
                    current_time = time.time()
            
            # Enforce minimum cooldown between requests
            last_req = self._last_request.get(provider_upper, 0)
            time_since_last = current_time - last_req
            
            if time_since_last < cooldown_seconds:
                wait_time = cooldown_seconds - time_since_last
                logger.debug(f"Cooldown wait for {provider_name}: {wait_time:.1f}s")
                time.sleep(wait_time)
                current_time = time.time()
            
            # Record this request
            self._request_times[provider_upper].append(current_time)
            self._last_request[provider_upper] = current_time
            
            logger.debug(
                f"Rate limiter: {provider_name} - "
                f"{len(self._request_times[provider_upper])} requests in last 60s"
            )
    
    def reset(self, provider_name: str = None) -> None:
        """
        Reset rate limiter for a specific provider or all providers.
        
        Args:
            provider_name: Provider to reset, or None to reset all
        """
        if provider_name:
            provider_upper = provider_name.upper()
            with self._locks[provider_upper]:
                self._request_times[provider_upper].clear()
                self._last_request.pop(provider_upper, None)
                logger.info(f"Rate limiter reset for {provider_name}")
        else:
            for provider in list(self._locks.keys()):
                with self._locks[provider]:
                    self._request_times[provider].clear()
                    self._last_request.pop(provider, None)
            logger.info("Rate limiter reset for all providers")
    
    def get_stats(self, provider_name: str) -> Dict:
        """
        Get current rate limit statistics for a provider.
        
        Args:
            provider_name: Provider name
            
        Returns:
            Dictionary with stats (requests_last_minute, last_request_time, etc.)
        """
        provider_upper = provider_name.upper()
        
        with self._locks[provider_upper]:
            current_time = time.time()
            cutoff_time = current_time - 60
            
            # Clean old requests
            request_queue = self._request_times[provider_upper]
            while request_queue and request_queue[0] < cutoff_time:
                request_queue.popleft()
            
            last_req = self._last_request.get(provider_upper, 0)
            
            return {
                "provider": provider_name,
                "requests_last_minute": len(request_queue),
                "last_request_seconds_ago": current_time - last_req if last_req else None,
                "configured_limit": RATE_LIMITS.get(provider_upper, {}).get("requests_per_minute", "N/A")
            }


# Global singleton instance
_rate_limiter = RateLimiter()


def get_rate_limiter() -> RateLimiter:
    """Get the global rate limiter instance."""
    return _rate_limiter
