from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json

from .db import DocumentStore
from .models import KeywordReportRow


@dataclass(frozen=True)
class KeywordOccurrence:
    keyword: str
    title: str
    source_url: str
    discovered_at: str


def build_weekly_keyword_report(
    *,
    database_path: str,
    days: int = 7,
    top_n: int = 10,
    links_per_keyword: int = 3,
    now: datetime | None = None,
) -> list[KeywordReportRow]:
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)

    since = current_time.astimezone(timezone.utc) - timedelta(days=days)
    with DocumentStore(database_path) as store:
        store.initialize()
        rows = store.keyword_analysis_rows_since(since.isoformat())

    counts: Counter[str] = Counter()
    occurrences: dict[str, list[KeywordOccurrence]] = defaultdict(list)
    for row in rows:
        keywords = _load_keywords(row["keywords_json"])
        for keyword in keywords:
            counts[keyword] += 1
            occurrences[keyword].append(
                KeywordOccurrence(
                    keyword=keyword,
                    title=row["title"],
                    source_url=row["source_url"],
                    discovered_at=row["discovered_at"],
                )
            )

    report_rows: list[KeywordReportRow] = []
    for keyword, count in counts.most_common(top_n):
        links = tuple(_format_markdown_link(item.title, item.source_url) for item in occurrences[keyword][:links_per_keyword])
        report_rows.append(KeywordReportRow(keyword=keyword, count=count, occurrence_links=links))

    return report_rows


def format_keyword_report_table(rows: list[KeywordReportRow]) -> str:
    table = [
        "| Avainsana | Esiintymat | Esimerkkilinkit |",
        "| --- | ---: | --- |",
    ]
    for row in rows:
        links = "<br>".join(row.occurrence_links)
        table.append(f"| {row.keyword} | {row.count} | {links} |")

    if len(table) == 2:
        table.append("| Ei tuloksia | 0 | |")

    return "\n".join(table)


def _load_keywords(value: str) -> list[str]:
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        return []

    if not isinstance(payload, list):
        return []

    keywords: list[str] = []
    seen: set[str] = set()
    for item in payload:
        keyword = str(item).strip().lower()
        if not keyword or keyword in seen:
            continue

        seen.add(keyword)
        keywords.append(keyword)

    return keywords


def _format_markdown_link(title: str, url: str) -> str:
    safe_title = title.replace("[", "\\[").replace("]", "\\]").replace("|", "\\|")
    safe_url = url.replace(")", "%29")
    return f"[{safe_title}]({safe_url})"
