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

    parsed = _parse_date(normalized)
    if parsed is None:
        return normalized

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc).isoformat()


def _parse_date(value: str) -> datetime | None:
    try:
        return parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        pass

    iso_value = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(iso_value)
    except ValueError:
        pass

    for date_format in COMMON_DATE_FORMATS:
        try:
            return datetime.strptime(value, date_format)
        except ValueError:
            continue

    return None
