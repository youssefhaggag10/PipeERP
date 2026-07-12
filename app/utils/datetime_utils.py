from datetime import UTC, datetime
from zoneinfo import ZoneInfo

EGYPT_TIMEZONE = ZoneInfo("Africa/Cairo")


def format_egypt_datetime(value: object) -> str:
    """Convert SQLite UTC timestamps to Egypt local time for display."""
    text = str(value or "").strip()
    if not text:
        return ""

    parsed: datetime | None = None
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
            try:
                parsed = datetime.strptime(text, pattern)
                break
            except ValueError:
                continue

    if parsed is None:
        return text
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(EGYPT_TIMEZONE).strftime("%Y-%m-%d %I:%M:%S %p")
