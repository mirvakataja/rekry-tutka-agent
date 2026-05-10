from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import logging
from pathlib import Path
from uuid import uuid4

from .date_utils import parse_date
from .db import DocumentStore
from .fetchers import FetchError, HttpFetcher, TextFetcher
from .html_extract import extract_html, extract_links
from .models import CollectedItem, IngestionResult, SourceConfig
from .parsers import parse_feed

LOGGER = logging.getLogger(__name__)


class TalentAcquisitionAgent:
    """Collect talent acquisition content from configured web sources."""

    def __init__(
        self,
        *,
        sources: list[SourceConfig],
        database_path: str | Path,
        fetcher: TextFetcher | None = None,
        max_items_per_source: int | None = None,
        fetch_linked_content: bool = True,
        max_article_age_days: int | None = 365,
        now: datetime | None = None,
    ) -> None:
        self.sources = sources
        self.database_path = database_path
        self.fetcher = fetcher or HttpFetcher()
        self.max_items_per_source = max_items_per_source
        self.fetch_linked_content = fetch_linked_content
        self.max_article_age_days = max_article_age_days
        self.now = _coerce_utc(now or datetime.now(timezone.utc))

    def run(self) -> IngestionResult:
        run_id = str(uuid4())
        enabled_sources = [source for source in self.sources if source.enabled]
        items_seen = 0
        inserted_count = 0
        updated_count = 0
        unchanged_count = 0
        error_count = 0

        with DocumentStore(self.database_path) as store:
            store.initialize()
            store.begin_run(run_id, len(enabled_sources))

            for source in enabled_sources:
                try:
                    items = self._collect_source(source)
                except (FetchError, ValueError) as exc:
                    error_count += 1
                    LOGGER.warning("Skipping source %s: %s", source.name, exc)
                    continue

                for item in items:
                    items_seen += 1
                    if self._is_too_old(item):
                        LOGGER.info("Skipping %s because it is older than the configured age limit", item.source_url)
                        continue

                    enriched = item
                    if self.fetch_linked_content and source.fetch_content:
                        try:
                            enriched = self._enrich_from_link(item)
                        except FetchError as exc:
                            error_count += 1
                            LOGGER.info("Using feed content for %s after fetch error: %s", item.source_url, exc)

                    if not enriched.content:
                        LOGGER.info("Skipping %s because it did not contain readable content", enriched.source_url)
                        continue

                    if self._is_too_old(enriched):
                        LOGGER.info("Skipping %s because it is older than the configured age limit", enriched.source_url)
                        continue

                    status = store.upsert_item(enriched)
                    if status == "inserted":
                        inserted_count += 1
                    elif status == "updated":
                        updated_count += 1
                    else:
                        unchanged_count += 1

            final_status = "completed_with_errors" if error_count else "completed"
            store.finish_run(
                run_id,
                status=final_status,
                items_seen=items_seen,
                inserted_count=inserted_count,
                updated_count=updated_count,
                unchanged_count=unchanged_count,
                error_count=error_count,
            )

        return IngestionResult(
            run_id=run_id,
            sources_checked=len(enabled_sources),
            items_seen=items_seen,
            inserted_count=inserted_count,
            updated_count=updated_count,
            unchanged_count=unchanged_count,
            error_count=error_count,
        )

    def _collect_source(self, source: SourceConfig) -> list[CollectedItem]:
        if source.type == "html_listing":
            return self._collect_html_listing(source)

        if source.type != "feed":
            raise ValueError(f"Unsupported source type: {source.type}")

        feed_text = self.fetcher.fetch_text(source.url)
        items = parse_feed(feed_text, source)
        if self.max_items_per_source is not None:
            return items[: self.max_items_per_source]
        return items

    def _collect_html_listing(self, source: SourceConfig) -> list[CollectedItem]:
        listing_html = self.fetcher.fetch_text(source.url)
        links = extract_links(listing_html, base_url=source.url, path_prefix=source.link_prefix)
        if self.max_items_per_source is not None:
            links = links[: self.max_items_per_source]

        items: list[CollectedItem] = []
        for link in links:
            article_html = self.fetcher.fetch_text(link)
            extracted = extract_html(article_html)
            if not extracted.title:
                continue

            items.append(
                CollectedItem(
                    source_name=source.name,
                    title=extracted.title,
                    source_url=link,
                    content=extracted.content,
                    publication_date=extracted.publication_date,
                    metadata={"source_tags": list(source.tags), "source_type": source.type},
                )
            )

        return items

    def _enrich_from_link(self, item: CollectedItem) -> CollectedItem:
        html = self.fetcher.fetch_text(item.source_url)
        extracted = extract_html(html)
        content = extracted.content or item.content
        publication_date = item.publication_date or extracted.publication_date
        metadata = {
            **item.metadata,
            "linked_content_fetched": True,
        }
        if extracted.title and extracted.title != item.title:
            metadata["linked_page_title"] = extracted.title

        return replace(
            item,
            content=content,
            publication_date=publication_date,
            metadata=metadata,
        )

    def _is_too_old(self, item: CollectedItem) -> bool:
        if self.max_article_age_days is None or not item.publication_date:
            return False

        publication_date = parse_date(item.publication_date)
        if publication_date is None:
            return False

        cutoff = self.now - timedelta(days=self.max_article_age_days)
        return publication_date < cutoff


def _coerce_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
