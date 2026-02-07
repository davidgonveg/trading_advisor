"""
Timing Utilities for Smart Wakeup System
"""
from datetime import datetime, timedelta
import time
import logging

logger = logging.getLogger("core.timing")

def wait_until_minute(target_minute: int):
    """
    Wait until the specified minute of the current or next hour.
    
    Args:
        target_minute: Target minute (0-59) to wake up at
    """
    now = datetime.now()
    target = now.replace(minute=target_minute, second=0, microsecond=0)
    
    # If we've already passed the target minute this hour, wait until next hour
    if now.minute >= target_minute or (now.minute == target_minute and now.second > 5):
        target += timedelta(hours=1)
    
    sleep_seconds = (target - now).total_seconds()
    
    if sleep_seconds > 0:
        logger.info(f"Waiting {sleep_seconds:.0f}s until {target.strftime('%H:%M:%S')}...")
        time.sleep(sleep_seconds)
    else:
        logger.warning(f"Target time {target} already passed, skipping wait")

def wait_until_next_hour(buffer_seconds: int = 10):
    """
    Wait until the top of the next hour plus a buffer.
    
    Args:
        buffer_seconds: Additional seconds to wait after the hour mark
    """
    now = datetime.now()
    next_hour = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    sleep_seconds = (next_hour - now).total_seconds() + buffer_seconds
    
    if sleep_seconds > 0:
        target_time = next_hour + timedelta(seconds=buffer_seconds)
        logger.info(f"Waiting {sleep_seconds:.0f}s until {target_time.strftime('%H:%M:%S')}...")
        time.sleep(sleep_seconds)
    else:
        logger.warning(f"Next hour {next_hour} already passed, skipping wait")

def get_minutes_until_close() -> int:
    """
    Get the number of minutes until the current hour closes.
    
    Returns:
        Minutes remaining in current hour
    """
    now = datetime.now()
    return 60 - now.minute - (1 if now.second > 0 else 0)
