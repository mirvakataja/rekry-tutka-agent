from __future__ import annotations

import argparse
import json
import logging
from dataclasses import asdict
from pathlib import Path

from .agent import TalentAcquisitionAgent
from .config import load_sources
from .db import DocumentStore

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

    return parser


if __name__ == "__main__":
    raise SystemExit(main())
