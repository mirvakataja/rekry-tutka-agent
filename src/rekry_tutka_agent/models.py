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
    link_prefix: str | None = None


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
class StoredDocument:
    """Document loaded from the database for downstream analysis."""

    id: int
    title: str
    content: str
    source_url: str
    content_hash: str


@dataclass(frozen=True)
class KeywordAnalysis:
    """LLM-produced keywords for one stored document."""

    document_id: int
    keywords: tuple[str, ...]
    model: str
    prompt_version: str
    content_hash: str


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


@dataclass(frozen=True)
class KeywordAnalysisResult:
    """Summary of one keyword analysis run."""

    documents_checked: int
    analyzed_count: int
    skipped_count: int
    error_count: int


@dataclass(frozen=True)
class KeywordReportLink:
    """One linked source example in a keyword trend report."""

    title: str
    source_url: str
    source_name: str


@dataclass(frozen=True)
class KeywordReportRow:
    """One row in a weekly keyword trend report."""

    keyword: str
    count: int
    occurrence_links: tuple[KeywordReportLink, ...]
