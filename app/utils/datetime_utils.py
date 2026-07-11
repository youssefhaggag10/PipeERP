from datetime import datetime, timezone
from zoneinfo import ZoneInfo


EGYPT_TIMEZONE = ZoneInfo("Africa/Cairo")


def format_egypt_datetime(value: object) -> str:
    """Convert SQLite UTC timestamps to Egypt local time for display."""
    text = str(value or "").strip()
    if not text:
        return ""

    parsed: datetime | None = None
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            parsed