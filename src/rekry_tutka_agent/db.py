from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Literal

from .models import CollectedItem, KeywordAnalysis, StoredDocument

UpsertStatus = Literal["inserted", "updated", "unchanged"]


class DocumentStore:
    """SQLite-backed storage for collected articles and discussions."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        if self.database_path.parent != Path("."):
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.database_path)
        self.connection.row_factory = sqlite3.Row

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "DocumentStore":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def initialize(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS ingestion_runs (
                id TEXT PRIMARY KEY,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                status TEXT NOT NULL,
                sources_checked INTEGER NOT NULL DEFAULT 0,
                items_seen INTEGER NOT NULL DEFAULT 0,
                inserted_count INTEGER NOT NULL DEFAULT 0,
                updated_count INTEGER NOT NULL DEFAULT 0,
                unchanged_count INTEGER NOT NULL DEFAULT 0,
                error_count INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_name TEXT NOT NULL,
                title TEXT NOT NULL,
                publication_date TEXT,
                content TEXT NOT NULL,
                source_url TEXT NOT NULL UNIQUE,
                content_hash TEXT NOT NULL,
                discovered_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                raw_metadata TEXT NOT NULL DEFAULT '{}'
            );

            CREATE INDEX IF NOT EXISTS idx_documents_publication_date
                ON documents(publication_date);
            CREATE INDEX IF NOT EXISTS idx_documents_source_name
                ON documents(source_name);

            CREATE TABLE IF NOT EXISTS document_keyword_analysis (
                document_id INTEGER PRIMARY KEY,
                keywords_json TEXT NOT NULL,
                model TEXT NOT NULL,
                prompt_version TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                analyzed_at TEXT NOT NULL,
                FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
            );
            """
        )
        self.connection.commit()

    def begin_run(self, run_id: str, sources_checked: int) -> None:
        self.connection.execute(
            """
            INSERT INTO ingestion_runs (id, started_at, status, sources_checked)
            VALUES (?, ?, 'running', ?)
            """,
            (run_id, _utc_now(), sources_checked),
        )
        self.connection.commit()

    def finish_run(
        self,
        run_id: str,
        *,
        status: str,
        items_seen: int,
        inserted_count: int,
        updated_count: int,
        unchanged_count: int,
        error_count: int,
    ) -> None:
        self.connection.execute(
            """
            UPDATE ingestion_runs
            SET finished_at = ?,
                status = ?,
                items_seen = ?,
                inserted_count = ?,
                updated_count = ?,
                unchanged_count = ?,
                error_count = ?
            WHERE id = ?
            """,
            (
                _utc_now(),
                status,
                items_seen,
                inserted_count,
                updated_count,
                unchanged_count,
                error_count,
                run_id,
            ),
        )
        self.connection.commit()

    def upsert_item(self, item: CollectedItem) -> UpsertStatus:
        content_hash = _content_hash(item)
        existing = self.connection.execute(
            "SELECT content_hash FROM documents WHERE source_url = ?",
            (item.source_url,),
        ).fetchone()

        now = _utc_now()
        metadata = json.dumps(item.metadata, sort_keys=True)
        if existing is None:
            self.connection.execute(
                """
                INSERT INTO documents (
                    source_name,
                    title,
                    publication_date,
                    content,
                    source_url,
                    content_hash,
                    discovered_at,
                    updated_at,
                    raw_metadata
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.source_name,
                    item.title,
                    item.publication_date,
                    item.content,
                    item.source_url,
                    content_hash,
                    now,
                    now,
                    metadata,
                ),
            )
            self.connection.commit()
            return "inserted"

        if existing["content_hash"] == content_hash:
            return "unchanged"

        self.connection.execute(
            """
            UPDATE documents
            SET source_name = ?,
                title = ?,
                publication_date = COALESCE(?, publication_date),
                content = ?,
                content_hash = ?,
                updated_at = ?,
                raw_metadata = ?
            WHERE source_url = ?
            """,
            (
                item.source_name,
                item.title,
                item.publication_date,
                item.content,
                content_hash,
                now,
                metadata,
                item.source_url,
            ),
        )
        self.connection.commit()
        return "updated"

    def documents_for_keyword_analysis(
        self,
        *,
        limit: int | None = None,
        force: bool = False,
    ) -> list[StoredDocument]:
        where_clause = ""
        if not force:
            where_clause = """
            WHERE analysis.document_id IS NULL
               OR analysis.content_hash != documents.content_hash
            """

        limit_clause = ""
        parameters: tuple[int, ...] = ()
        if limit is not None:
            limit_clause = "LIMIT ?"
            parameters = (limit,)

        rows = self.connection.execute(
            f"""
            SELECT
                documents.id,
                documents.title,
                documents.content,
                documents.source_url,
                documents.content_hash
            FROM documents
            LEFT JOIN document_keyword_analysis AS analysis
                ON analysis.document_id = documents.id
            {where_clause}
            ORDER BY documents.id
            {limit_clause}
            """,
            parameters,
        ).fetchall()

        return [
            StoredDocument(
                id=row["id"],
                title=row["title"],
                content=row["content"],
                source_url=row["source_url"],
                content_hash=row["content_hash"],
            )
            for row in rows
        ]

    def save_keyword_analysis(self, analysis: KeywordAnalysis) -> None:
        self.connection.execute(
            """
            INSERT INTO document_keyword_analysis (
                document_id,
                keywords_json,
                model,
                prompt_version,
                content_hash,
                analyzed_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(document_id) DO UPDATE SET
                keywords_json = excluded.keywords_json,
                model = excluded.model,
                prompt_version = excluded.prompt_version,
                content_hash = excluded.content_hash,
                analyzed_at = excluded.analyzed_at
            """,
            (
                analysis.document_id,
                json.dumps(list(analysis.keywords), ensure_ascii=False),
                analysis.model,
                analysis.prompt_version,
                analysis.content_hash,
                _utc_now(),
            ),
        )
        self.connection.commit()


def _content_hash(item: CollectedItem) -> str:
    digest = hashlib.sha256()
    digest.update(item.title.encode("utf-8"))
    digest.update(b"\0")
    digest.update((item.publication_date or "").encode("utf-8"))
    digest.update(b"\0")
    digest.update(item.content.encode("utf-8"))
    return digest.hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
