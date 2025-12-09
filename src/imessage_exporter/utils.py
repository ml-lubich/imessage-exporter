import datetime
from typing import Optional

# Constants
COCOA_EPOCH = datetime.datetime(2001, 1, 1, 0, 0, 0)

def cocoa_to_datetime(nanoseconds: Optional[int]) -> Optional[datetime.datetime]:
    """Convert Cocoa timestamp (nanoseconds since 2001-01-01) to datetime."""
    if nanoseconds is None:
        return None
    try:
        seconds = nanoseconds / 1_000_000_000
        return COCOA_EPOCH + datetime.timedelta(seconds=seconds)
    except Exception:
        return None
