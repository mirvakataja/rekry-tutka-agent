from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html import escape
import json
from urllib.parse import quote

from .db import DocumentStore
from .models import KeywordReportLink, KeywordReportRow

DEFAULT_BLOCKED_KEYWORDS = (
    "rekrytointi",
    "talent acquisition",
    "recruiting",
    "recruitment",
)


@dataclass(frozen=True)
class KeywordOccurrence:
    keyword: str
    source_name: str
    title: str
    source_url: str
    discovered_at: str


def build_weekly_keyword_report(
    *,
    database_path: str,
    days: int = 7,
    top_n: int = 10,
    links_per_keyword: int = 5,
    blocked_keywords: tuple[str, ...] = DEFAULT_BLOCKED_KEYWORDS,
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
    blocked = {_normalize_keyword(keyword) for keyword in blocked_keywords}
    for row in rows:
        keywords = _load_keywords(row["keywords_json"])
        for keyword in keywords:
            if keyword in blocked:
                continue

            counts[keyword] += 1
            occurrences[keyword].append(
                KeywordOccurrence(
                    keyword=keyword,
                    source_name=row["source_name"],
                    title=row["title"],
                    source_url=row["source_url"],
                    discovered_at=row["discovered_at"],
                )
            )

    report_rows: list[KeywordReportRow] = []
    for keyword, count in counts.most_common(top_n):
        links = tuple(
            KeywordReportLink(
                title=item.title,
                source_url=item.source_url,
                source_name=item.source_name,
            )
            for item in occurrences[keyword][:links_per_keyword]
        )
        report_rows.append(KeywordReportRow(keyword=keyword, count=count, occurrence_links=links))

    return report_rows


def format_keyword_report_table(rows: list[KeywordReportRow]) -> str:
    table = [
        "| Avainsana | Esiintymat | Esimerkkilinkit |",
        "| --- | ---: | --- |",
    ]
    for row in rows:
        links = "<br>".join(_format_markdown_link(link) for link in row.occurrence_links)
        table.append(f"| {row.keyword} | {row.count} | {links} |")

    if len(table) == 2:
        table.append("| Ei tuloksia | 0 | |")

    return "\n".join(table)


def format_keyword_report_html(rows: list[KeywordReportRow]) -> str:
    return "\n".join(
        [
            "<!doctype html>",
            "<html>",
            "<head>",
            '  <meta charset="utf-8">',
            "  <style>",
            "    body { font-family: Arial, sans-serif; color: #1f2933; }",
            "    table { border-collapse: collapse; width: 100%; }",
            "    th, td { border: 1px solid #d9e2ec; padding: 8px 10px; vertical-align: top; }",
            "    th { background: #f0f4f8; text-align: left; }",
            "    ul { margin: 0; padding-left: 18px; }",
            "    a { color: #0b5fff; text-decoration: none; }",
            "    a:hover { text-decoration: underline; }",
            "  </style>",
            "</head>",
            "<body>",
            format_keyword_report_html_fragment(rows),
            "</body>",
            "</html>",
        ]
    )


def format_keyword_report_html_fragment(rows: list[KeywordReportRow]) -> str:
    table_rows = []
    if rows:
        for row in rows:
            links = "".join(
                f"<li>{_format_html_link(link)}</li>"
                for link in row.occurrence_links
            )
            table_rows.append(
                "<tr>"
                f"<td>{escape(row.keyword)}</td>"
                f"<td style=\"text-align: right;\">{row.count}</td>"
                f"<td><ul>{links}</ul></td>"
                "</tr>"
            )
    else:
        table_rows.append("<tr><td>Ei tuloksia</td><td style=\"text-align: right;\">0</td><td></td></tr>")

    return "\n".join(
        [
            "<section>",
            "  <h2>Rekry-tutka: viikon top 10 avainsanat</h2>",
            "  <table>",
            "    <thead>",
            "      <tr><th>Avainsana</th><th>Esiintymat</th><th>Esimerkkiesiintymat</th></tr>",
            "    </thead>",
            "    <tbody>",
            *[f"      {row}" for row in table_rows],
            "    </tbody>",
            "  </table>",
            "</section>",
        ]
    )


def format_trend_summary_table(trends: tuple[str, ...] | list[str]) -> str:
    if not trends:
        return "Ei trendikoostetta."

    return "\n".join(f"- {trend}" for trend in trends)


def format_trend_summary_html(trends: tuple[str, ...] | list[str]) -> str:
    items = "".join(f"<li>{escape(trend)}</li>" for trend in trends)
    if not items:
        items = "<li>Ei trendikoostetta.</li>"

    return "\n".join(
        [
            "<section>",
            "  <h2>Nousevat talent acquisition -trendit</h2>",
            f"  <ul>{items}</ul>",
            "</section>",
        ]
    )


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
        keyword = _normalize_keyword(str(item))
        if not keyword or keyword in seen:
            continue

        seen.add(keyword)
        keywords.append(keyword)

    return keywords


def _normalize_keyword(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _format_markdown_link(link: KeywordReportLink) -> str:
    safe_title = _link_label(link).replace("[", "\\[").replace("]", "\\]").replace("|", "\\|")
    safe_url = link.source_url.replace(")", "%29")
    return f"[{safe_title}]({safe_url})"


def _format_html_link(link: KeywordReportLink) -> str:
    label = escape(_link_label(link))
    url = escape(quote(link.source_url, safe="/:#?&=%@+~!$,;'()*[]"))
    return f'<a href="{url}">{label}</a>'


def _link_label(link: KeywordReportLink) -> str:
    if link.source_name:
        return f"{link.title} ({link.source_name})"
    return link.title
