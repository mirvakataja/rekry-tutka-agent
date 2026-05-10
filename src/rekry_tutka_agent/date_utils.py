from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime


COMMON_DATE_FORMATS = (
    "%Y-%m-%d",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%S%z",
    "%a, %d %b %Y %H:%M:%S %z",
    "%a, %d %b %Y %H:%M:%S %Z",
)


def normalize_date(value: str | None) -> str | None:
    """Return an ISO-8601 timestamp when a feed or page date can be parsed."""

    if not value:
        return None

    normalized = value.strip()
    if not normalized:
        return None

    parsed = parse_date(normalized)
    if parsed is None:
        return normalized

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc).isoformat()


def parse_date(value: str | None) -> datetime | None:
    """Parse a date-like string and return a timezone-aware UTC datetime."""

    if not value:
        return None

    normalized = value.strip()
    if not normalized:
        return None

    try:
        parsed = parsedate_to_datetime(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, IndexError):
        pass

    iso_value = normalized.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(iso_value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        pass

    for date_format in COMMON_DATE_FORMATS:
        try:
            parsed = datetime.strptime(normalized, date_format)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            continue

    return None
