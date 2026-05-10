from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SourceConfig:
    """Configuration for one web source."""

    name: str
    url: str
    type: str = "feed"
    enabled: bool = True
    tags: tuple[str, ...] = ()
    fetch_content: bool = True


@dataclass(frozen=True)
class CollectedItem:
    """Normalized document collected from a web source."""

    source_name: str
    title: str
    source_url: str
    content: str
    publication_date: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class IngestionResult:
    """Summary of one agent run."""

    run_id: str
    sources_checked: int
    items_seen: int
    inserted_count: int
    updated_count: int
    unchanged_count: int
    error_count: int
