from __future__ import annotations

import argparse
import json
import logging
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .agent import TalentAcquisitionAgent
from .config import load_sources
from .db import DocumentStore
from .llm import LLMError, OpenAICompatibleChatModel, analyze_stored_documents, summarize_weekly_trends
from .reports import (
    DEFAULT_BLOCKED_KEYWORDS,
    build_weekly_keyword_report,
    format_keyword_report_html,
    format_keyword_report_html_fragment,
    format_keyword_report_table,
    format_trend_summary_html,
    format_trend_summary_table,
)
from .scheduler import run_scheduler_loop

DEFAULT_DATABASE = Path("data/rekry_tutka.db")
DEFAULT_SOURCES = Path("config/sources.json")


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    if args.command == "init-db":
        with DocumentStore(args.database) as store:
            store.initialize()
        print(json.dumps({"database": str(args.database), "status": "initialized"}, indent=2))
        return 0

    if args.command == "run":
        if args.max_article_age_days is not None and args.max_article_age_days < 1:
            parser.error("--max-article-age-days must be at least 1")

        sources = load_sources(args.sources)
        agent = TalentAcquisitionAgent(
            sources=sources,
            database_path=args.database,
            max_items_per_source=args.limit,
            fetch_linked_content=not args.no_fetch_linked_content,
            max_article_age_days=args.max_article_age_days,
        )
        result = agent.run()
        print(json.dumps(asdict(result), indent=2, sort_keys=True))
        return 0

    if args.command == "cleanup-old-documents":
        cutoff = _parse_cutoff_date(args.before_date)
        with DocumentStore(args.database) as store:
            store.initialize()
            deleted_count = store.delete_documents_published_before(cutoff)
        print(
            json.dumps(
                {
                    "database": str(args.database),
                    "before_date": cutoff.date().isoformat(),
                    "deleted_count": deleted_count,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    if args.command == "analyze-keywords":
        if args.max_keywords < 1 or args.max_keywords > 5:
            parser.error("--max-keywords must be between 1 and 5")

        try:
            chat_model = OpenAICompatibleChatModel.from_environment(
                model=args.model,
                base_url=args.base_url,
                api_key_env=args.api_key_env,
            )
            result = analyze_stored_documents(
                database_path=args.database,
                chat_model=chat_model,
                limit=args.limit,
                force=args.force,
                max_keywords=args.max_keywords,
                content_char_limit=args.content_chars,
                output_language=args.output_language,
            )
        except LLMError as exc:
            parser.exit(1, f"rekry-tutka-agent: LLM analysis failed: {exc}\n")

        print(json.dumps(asdict(result), indent=2, sort_keys=True))
        return 0

    if args.command == "weekly-keyword-report":
        if args.days < 1:
            parser.error("--days must be at least 1")
        if args.top < 1:
            parser.error("--top must be at least 1")
        if args.links < 1:
            parser.error("--links must be at least 1")

        blocked_keywords = tuple(args.blocked_keyword)
        if not args.no_default_blocked_keywords:
            blocked_keywords = (*DEFAULT_BLOCKED_KEYWORDS, *blocked_keywords)

        rows = build_weekly_keyword_report(
            database_path=str(args.database),
            days=args.days,
            top_n=args.top,
            links_per_keyword=args.links,
            blocked_keywords=blocked_keywords,
        )
        if args.format == "html":
            print(format_keyword_report_html(rows))
        elif args.format == "html-fragment":
            print(format_keyword_report_html_fragment(rows))
        else:
            print(format_keyword_report_table(rows))
        return 0

    if args.command == "weekly-trend-summary":
        if args.days < 1:
            parser.error("--days must be at least 1")
        if args.bullets < 1:
            parser.error("--bullets must be at least 1")

        try:
            chat_model = OpenAICompatibleChatModel.from_environment(
                model=args.model,
                base_url=args.base_url,
                api_key_env=args.api_key_env,
            )
            trends = summarize_weekly_trends(
                database_path=str(args.database),
                chat_model=chat_model,
                days=args.days,
                max_bullets=args.bullets,
                output_language=args.output_language,
                focus_area=args.focus_area,
            )
        except LLMError as exc:
            parser.exit(1, f"rekry-tutka-agent: weekly trend summary failed: {exc}\n")

        if args.format == "html":
            print(format_trend_summary_html(trends, title=args.title))
        else:
            print(format_trend_summary_table(trends))
        return 0

    if args.command == "schedule":
        if args.max_keywords < 1 or args.max_keywords > 5:
            parser.error("--max-keywords must be between 1 and 5")
        if args.ingestion_interval_hours < 1:
            parser.error("--ingestion-interval-hours must be at least 1")
        if args.weekly_interval_days < 1:
            parser.error("--weekly-interval-days must be at least 1")
        if args.check_interval_seconds < 1:
            parser.error("--check-interval-seconds must be at least 1")

        try:
            result = run_scheduler_loop(
                database_path=str(args.database),
                sources_path=str(args.sources),
                ingestion_interval_hours=args.ingestion_interval_hours,
                weekly_interval_days=args.weekly_interval_days,
                check_interval_seconds=args.check_interval_seconds,
                once=args.once,
                ingestion_limit=args.limit,
                fetch_linked_content=not args.no_fetch_linked_content,
                chat_model_factory=lambda: OpenAICompatibleChatModel.from_environment(
                    model=args.model,
                    base_url=args.base_url,
                    api_key_env=args.api_key_env,
                ),
                max_keywords=args.max_keywords,
                content_char_limit=args.content_chars,
                output_language=args.output_language,
            )
        except LLMError as exc:
            parser.exit(1, f"rekry-tutka-agent: scheduled LLM analysis failed: {exc}\n")

        print(json.dumps(asdict(result), indent=2, sort_keys=True))
        return 0

    parser.error(f"Unsupported command: {args.command}")
    return 2


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rekry-tutka-agent",
        description="Collect talent acquisition trends and discussions into SQLite.",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable informational logging.")

    subparsers = parser.add_subparsers(dest="command", required=True)

    init_db = subparsers.add_parser("init-db", help="Create or update the SQLite schema.")
    init_db.add_argument("--database", type=Path, default=DEFAULT_DATABASE, help="SQLite database path.")

    run = subparsers.add_parser("run", help="Fetch configured sources and store collected documents.")
    run.add_argument("--sources", type=Path, default=DEFAULT_SOURCES, help="JSON file containing web sources.")
    run.add_argument("--database", type=Path, default=DEFAULT_DATABASE, help="SQLite database path.")
    run.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of feed items to process per source.",
    )
    run.add_argument(
        "--no-fetch-linked-content",
        action="store_true",
        help="Store feed content only instead of fetching each original link.",
    )
    run.add_argument(
        "--max-article-age-days",
        type=int,
        default=365,
        help="Skip documents with a parseable publication date older than this many days.",
    )

    cleanup = subparsers.add_parser(
        "cleanup-old-documents",
        help="Delete stored documents published before a cutoff date.",
    )
    cleanup.add_argument("--database", type=Path, default=DEFAULT_DATABASE, help="SQLite database path.")
    cleanup.add_argument(
        "--before-date",
        default="2025-01-01",
        help="Delete documents with publication dates before this date, in YYYY-MM-DD format.",
    )

    analyze = subparsers.add_parser(
        "analyze-keywords",
        help="Use an LLM to extract up to five keywords for stored documents.",
    )
    analyze.add_argument("--database", type=Path, default=DEFAULT_DATABASE, help="SQLite database path.")
    analyze.add_argument("--limit", type=int, default=None, help="Maximum number of documents to analyze.")
    analyze.add_argument("--force", action="store_true", help="Re-analyze documents even when content is unchanged.")
    analyze.add_argument(
        "--max-keywords",
        type=int,
        default=5,
        help="Maximum number of keywords to store per document. Must be between 1 and 5.",
    )
    analyze.add_argument(
        "--content-chars",
        type=int,
        default=8_000,
        help="Maximum number of content characters sent to the LLM per document.",
    )
    analyze.add_argument(
        "--output-language",
        default="Finnish",
        help="Preferred keyword language for the LLM response.",
    )
    analyze.add_argument(
        "--model",
        default=None,
        help="LLM model name. Defaults to REKRY_TUTKA_LLM_MODEL or gpt-4o-mini.",
    )
    analyze.add_argument(
        "--base-url",
        default=None,
        help="OpenAI-compatible API base URL. Defaults to OPENAI_BASE_URL or https://api.openai.com/v1.",
    )
    analyze.add_argument(
        "--api-key-env",
        default="OPENAI_API_KEY",
        help="Environment variable that contains the LLM API key.",
    )

    report = subparsers.add_parser(
        "weekly-keyword-report",
        help="Print a top keyword table for documents discovered during the last week.",
    )
    report.add_argument("--database", type=Path, default=DEFAULT_DATABASE, help="SQLite database path.")
    report.add_argument("--days", type=int, default=7, help="Window size in days.")
    report.add_argument("--top", type=int, default=10, help="Number of top keywords to print.")
    report.add_argument("--links", type=int, default=5, help="Number of occurrence links per keyword.")
    report.add_argument(
        "--blocked-keyword",
        action="append",
        default=[],
        help="Additional keyword to exclude from the report. Can be provided multiple times.",
    )
    report.add_argument(
        "--no-default-blocked-keywords",
        action="store_true",
        help=(
            "Do not exclude the default generic recruitment terms: "
            "rekrytointi, talent acquisition, recruiting, recruitment."
        ),
    )
    report.add_argument(
        "--format",
        choices=("markdown", "html", "html-fragment"),
        default="markdown",
        help="Output format for the report.",
    )

    trend_summary = subparsers.add_parser(
        "weekly-trend-summary",
        help="Use an LLM to summarize emerging weekly talent acquisition trends.",
    )
    trend_summary.add_argument("--database", type=Path, default=DEFAULT_DATABASE, help="SQLite database path.")
    trend_summary.add_argument("--days", type=int, default=7, help="Window size in days.")
    trend_summary.add_argument("--bullets", type=int, default=5, help="Number of trend bullet points to print.")
    trend_summary.add_argument(
        "--output-language",
        default="Finnish",
        help="Preferred language for the trend summary.",
    )
    trend_summary.add_argument(
        "--focus-area",
        default="talent acquisition",
        help="Trend focus area for the LLM prompt.",
    )
    trend_summary.add_argument(
        "--title",
        default="Nousevat talent acquisition -trendit",
        help="HTML section heading used with --format html.",
    )
    trend_summary.add_argument(
        "--format",
        choices=("markdown", "html"),
        default="markdown",
        help="Output format for the trend summary.",
    )
    trend_summary.add_argument(
        "--model",
        default=None,
        help="LLM model name. Defaults to REKRY_TUTKA_LLM_MODEL or gpt-4o-mini.",
    )
    trend_summary.add_argument(
        "--base-url",
        default=None,
        help="OpenAI-compatible API base URL. Defaults to OPENAI_BASE_URL or https://api.openai.com/v1.",
    )
    trend_summary.add_argument(
        "--api-key-env",
        default="OPENAI_API_KEY",
        help="Environment variable that contains the LLM API key.",
    )

    schedule = subparsers.add_parser(
        "schedule",
        help="Run due daily ingestion and weekly keyword analysis/report tasks.",
    )
    schedule.add_argument("--sources", type=Path, default=DEFAULT_SOURCES, help="JSON file containing web sources.")
    schedule.add_argument("--database", type=Path, default=DEFAULT_DATABASE, help="SQLite database path.")
    schedule.add_argument("--limit", type=int, default=None, help="Maximum feed items to process per source.")
    schedule.add_argument(
        "--no-fetch-linked-content",
        action="store_true",
        help="Store feed content only instead of fetching each original link.",
    )
    schedule.add_argument(
        "--ingestion-interval-hours",
        type=int,
        default=24,
        help="Minimum interval between ingestion runs.",
    )
    schedule.add_argument(
        "--weekly-interval-days",
        type=int,
        default=7,
        help="Minimum interval between keyword report runs.",
    )
    schedule.add_argument(
        "--check-interval-seconds",
        type=int,
        default=3600,
        help="How often the scheduler checks for due tasks.",
    )
    schedule.add_argument("--once", action="store_true", help="Run due tasks once and exit.")
    schedule.add_argument(
        "--max-keywords",
        type=int,
        default=5,
        help="Maximum number of keywords to store per document. Must be between 1 and 5.",
    )
    schedule.add_argument(
        "--content-chars",
        type=int,
        default=8_000,
        help="Maximum number of content characters sent to the LLM per document.",
    )
    schedule.add_argument(
        "--output-language",
        default="Finnish",
        help="Preferred keyword language for the LLM response.",
    )
    schedule.add_argument(
        "--model",
        default=None,
        help="LLM model name. Defaults to REKRY_TUTKA_LLM_MODEL or gpt-4o-mini.",
    )
    schedule.add_argument(
        "--base-url",
        default=None,
        help="OpenAI-compatible API base URL. Defaults to OPENAI_BASE_URL or https://api.openai.com/v1.",
    )
    schedule.add_argument(
        "--api-key-env",
        default="OPENAI_API_KEY",
        help="Environment variable that contains the LLM API key.",
    )

    return parser


def _parse_cutoff_date(value: str) -> datetime:
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise SystemExit(f"rekry-tutka-agent: --before-date must use YYYY-MM-DD format: {value}\n") from exc
    return parsed.replace(tzinfo=timezone.utc)


if __name__ == "__main__":
    raise SystemExit(main())
