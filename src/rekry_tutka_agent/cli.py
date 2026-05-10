from __future__ import annotations

import argparse
import json
import logging
from dataclasses import asdict
from pathlib import Path

from .agent import TalentAcquisitionAgent
from .config import load_sources
from .db import DocumentStore
from .llm import OpenAICompatibleChatModel, analyze_stored_documents

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
        sources = load_sources(args.sources)
        agent = TalentAcquisitionAgent(
            sources=sources,
            database_path=args.database,
            max_items_per_source=args.limit,
            fetch_linked_content=not args.no_fetch_linked_content,
        )
        result = agent.run()
        print(json.dumps(asdict(result), indent=2, sort_keys=True))
        return 0

    if args.command == "analyze-keywords":
        if args.max_keywords < 1 or args.max_keywords > 5:
            parser.error("--max-keywords must be between 1 and 5")

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

    return parser


if __name__ == "__main__":
    raise SystemExit(main())
