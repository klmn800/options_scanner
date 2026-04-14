    #!/usr/bin/env python3
"""
Timezone Utilities (timezone_utils.py)
------------------------------------
Centralized timezone handling for consistent Eastern Time timestamps.
Handles EST/EDT automatically.
Located in: options_scanner\tools
"""

from datetime import datetime, timezone, timedelta
from typing import Optional

# Time simulation support for testing
_SIMULATED_TIME = None  # Format: (hour, minute) or None for real time
_SIMULATED_TIME_START = None  # time.time() when simulation was activated
_SIMULATED_TTL = None  # TTL in seconds, or None for no expiry

def set_simulated_time(hour: int, minute: int, ttl_hours: float = None):
    """Set simulated time for testing purposes (e.g., testing scheduled triggers)

    Args:
        hour: Hour in 24-hour format (0-23)
        minute: Minute (0-59)
        ttl_hours: Auto-expire after this many hours (None = never expire)

    Example:
        set_simulated_time(6, 35)           # Simulate 6:35 AM, no expiry
        set_simulated_time(17, 0, ttl_hours=4)  # Simulate 5:00 PM, expire after 4h
    """
    import time as _time
    global _SIMULATED_TIME, _SIMULATED_TIME_START, _SIMULATED_TTL
    _SIMULATED_TIME = (hour, minute)
    _SIMULATED_TIME_START = _time.time()
    _SIMULATED_TTL = ttl_hours * 3600 if ttl_hours is not None else None

def clear_simulated_time():
    """Clear simulated time and return to real time"""
    global _SIMULATED_TIME, _SIMULATED_TIME_START, _SIMULATED_TTL
    _SIMULATED_TIME = None
    _SIMULATED_TIME_START = None
    _SIMULATED_TTL = None

def get_eastern_timezone():
    """Get proper Eastern timezone that handles EST/EDT automatically"""
    try:
        # Python 3.9+ has zoneinfo built-in
        import zoneinfo
        return zoneinfo.ZoneInfo("America/New_York")
    except ImportError:
        try:
            # Fallback to pytz if available
            import pytz
            return pytz.timezone('America/New_York')
        except ImportError:
            # Last resort: hardcode EST (will be wrong during EDT)
            print("WARNING: Using hardcoded EST - will be wrong during daylight saving time")
            return timezone(timedelta(hours=-5))

def now_eastern() -> datetime:
    """Get current time in Eastern timezone (EST/EDT aware)

    Returns simulated time if set via set_simulated_time(), otherwise returns real time.
    """
    current_time = datetime.now(get_eastern_timezone())

    # Apply simulated time if set (with TTL expiry check)
    if _SIMULATED_TIME is not None:
        if _SIMULATED_TTL is not None and _SIMULATED_TIME_START is not None:
            import time as _time
            if _time.time() - _SIMULATED_TIME_START >= _SIMULATED_TTL:
                clear_simulated_time()
                return current_time
        hour, minute = _SIMULATED_TIME
        current_time = current_time.replace(hour=hour, minute=minute, second=0, microsecond=0)

    return current_time

def eastern_isoformat() -> str:
    """Get Eastern timestamp in ISO format for database storage"""
    return now_eastern().strftime('%Y-%m-%d %H:%M:%S')  # → "2025-06-28 17:34:18"

def eastern_timestamp_string() -> str:
    """Get Eastern timestamp string for session IDs and filenames"""
    return now_eastern().strftime("%Y%m%d_%H%M%S")

def eastern_date_string() -> str:
    """Get Eastern date string for trade_date fields"""
    return now_eastern().strftime("%Y-%m-%d")


