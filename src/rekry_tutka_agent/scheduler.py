from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import sys
import time
from typing import Callable, TextIO

from .agent import TalentAcquisitionAgent
from .config import load_sources
from .db import DocumentStore
from .llm import ChatModel, OpenAICompatibleChatModel, analyze_stored_documents
from .reports import build_weekly_keyword_report, format_keyword_report_table

DAILY_INGESTION_TASK = "daily-ingestion"
WEEKLY_KEYWORD_REPORT_TASK = "weekly-keyword-report"


@dataclass(frozen=True)
class ScheduledRunResult:
    ingestion_ran: bool
    weekly_analysis_ran: bool
    error_count: int


def run_scheduler_loop(
    *,
    database_path: str,
    sources_path: str,
    ingestion_interval_hours: int = 24,
    weekly_interval_days: int = 7,
    check_interval_seconds: int = 3600,
    once: bool = False,
    ingestion_limit: int | None = None,
    fetch_linked_content: bool = True,
    chat_model: ChatModel | None = None,
    chat_model_factory: Callable[[], ChatModel] | None = None,
    max_keywords: int = 5,
    content_char_limit: int = 8_000,
    output_language: str = "Finnish",
    output: TextIO | None = None,
) -> ScheduledRunResult:
    output = output or sys.stdout
    aggregate = ScheduledRunResult(ingestion_ran=False, weekly_analysis_ran=False, error_count=0)

    while True:
        result = run_due_tasks(
            database_path=database_path,
            sources_path=sources_path,
            ingestion_interval_hours=ingestion_interval_hours,
            weekly_interval_days=weekly_interval_days,
            ingestion_limit=ingestion_limit,
            fetch_linked_content=fetch_linked_content,
            chat_model=chat_model,
            chat_model_factory=chat_model_factory,
            max_keywords=max_keywords,
            content_char_limit=content_char_limit,
            output_language=output_language,
            output=output,
        )
        aggregate = ScheduledRunResult(
            ingestion_ran=aggregate.ingestion_ran or result.ingestion_ran,
            weekly_analysis_ran=aggregate.weekly_analysis_ran or result.weekly_analysis_ran,
            error_count=aggregate.error_count + result.error_count,
        )

        if once:
            return aggregate

        time.sleep(check_interval_seconds)


def run_due_tasks(
    *,
    database_path: str,
    sources_path: str,
    ingestion_interval_hours: int = 24,
    weekly_interval_days: int = 7,
    ingestion_limit: int | None = None,
    fetch_linked_content: bool = True,
    chat_model: ChatModel | None = None,
    chat_model_factory: Callable[[], ChatModel] | None = None,
    max_keywords: int = 5,
    content_char_limit: int = 8_000,
    output_language: str = "Finnish",
    output: TextIO | None = None,
    now: datetime | None = None,
) -> ScheduledRunResult:
    output = output or sys.stdout
    current_time = _coerce_utc(now or datetime.now(timezone.utc))
    ingestion_ran = False
    weekly_analysis_ran = False
    error_count = 0

    with DocumentStore(database_path) as store:
        store.initialize()
        ingestion_due = _task_due(
            store.task_last_finished_at(DAILY_INGESTION_TASK),
            timedelta(hours=ingestion_interval_hours),
            current_time,
        )
        weekly_due = _task_due(
            store.task_last_finished_at(WEEKLY_KEYWORD_REPORT_TASK),
            timedelta(days=weekly_interval_days),
            current_time,
        )

    if ingestion_due:
        ingestion_ran = True
        try:
            _mark_started(database_path, DAILY_INGESTION_TASK)
            sources = load_sources(sources_path)
            result = TalentAcquisitionAgent(
                sources=sources,
                database_path=database_path,
                max_items_per_source=ingestion_limit,
                fetch_linked_content=fetch_linked_content,
            ).run()
            status = "completed_with_errors" if result.error_count else "completed"
            _mark_finished(database_path, DAILY_INGESTION_TASK, status)
        except Exception:
            error_count += 1
            _mark_finished(database_path, DAILY_INGESTION_TASK, "failed")
            raise

    if weekly_due:
        weekly_analysis_ran = True
        try:
            _mark_started(database_path, WEEKLY_KEYWORD_REPORT_TASK)
            model = chat_model or (chat_model_factory() if chat_model_factory else OpenAICompatibleChatModel.from_environment())
            analyze_stored_documents(
                database_path=database_path,
                chat_model=model,
                force=False,
                max_keywords=max_keywords,
                content_char_limit=content_char_limit,
                output_language=output_language,
            )
            report = build_weekly_keyword_report(database_path=database_path, days=weekly_interval_days)
            print(format_keyword_report_table(report), file=output)
            _mark_finished(database_path, WEEKLY_KEYWORD_REPORT_TASK, "completed")
        except Exception:
            error_count += 1
            _mark_finished(database_path, WEEKLY_KEYWORD_REPORT_TASK, "failed")
            raise

    return ScheduledRunResult(
        ingestion_ran=ingestion_ran,
        weekly_analysis_ran=weekly_analysis_ran,
        error_count=error_count,
    )


def _task_due(last_finished_at: str | None, interval: timedelta, now: datetime) -> bool:
    if last_finished_at is None:
        return True

    try:
        last_finished = _coerce_utc(datetime.fromisoformat(last_finished_at))
    except ValueError:
        return True

    return now - last_finished >= interval


def _mark_started(database_path: str, task_name: str) -> None:
    with DocumentStore(database_path) as store:
        store.initialize()
        store.mark_task_started(task_name)


def _mark_finished(database_path: str, task_name: str, status: str) -> None:
    with DocumentStore(database_path) as store:
        store.initialize()
        store.mark_task_finished(task_name, status)


def _coerce_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
