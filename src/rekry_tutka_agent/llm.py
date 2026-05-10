from __future__ import annotations

from dataclasses import dataclass
import json
import os
import re
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .models import KeywordAnalysis, KeywordAnalysisResult, StoredDocument
from .db import DocumentStore
from .reports import build_weekly_keyword_report

PROMPT_VERSION = "keyword-topics-v1"
DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_BASE_URL = "https://api.openai.com/v1"


class LLMError(RuntimeError):
    """Raised when keyword analysis cannot be completed."""


class ChatModel(Protocol):
    model: str

    def complete(self, messages: list[dict[str, str]]) -> str:
        """Return the model response text for chat messages."""


@dataclass(frozen=True)
class OpenAICompatibleChatModel:
    """Minimal OpenAI-compatible chat client using only the standard library."""

    api_key: str
    model: str = DEFAULT_MODEL
    base_url: str = DEFAULT_BASE_URL
    timeout_seconds: float = 45

    @classmethod
    def from_environment(
        cls,
        *,
        model: str | None = None,
        base_url: str | None = None,
        api_key_env: str = "OPENAI_API_KEY",
    ) -> "OpenAICompatibleChatModel":
        api_key = os.environ.get(api_key_env)
        if not api_key:
            raise LLMError(f"Missing API key environment variable: {api_key_env}")

        return cls(
            api_key=api_key,
            model=model or os.environ.get("REKRY_TUTKA_LLM_MODEL", DEFAULT_MODEL),
            base_url=(base_url or os.environ.get("OPENAI_BASE_URL", DEFAULT_BASE_URL)).rstrip("/"),
        )

    def complete(self, messages: list[dict[str, str]]) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        request = Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )

        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                response_payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise LLMError(f"LLM API returned HTTP {exc.code}: {body}") from exc
        except (URLError, TimeoutError) as exc:
            raise LLMError(f"Could not reach LLM API: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise LLMError("LLM API returned invalid JSON") from exc

        try:
            return response_payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("LLM API response did not contain message content") from exc


@dataclass(frozen=True)
class KeywordAnalyzer:
    chat_model: ChatModel
    max_keywords: int = 5
    content_char_limit: int = 8_000
    output_language: str = "Finnish"

    def analyze_document(self, document: StoredDocument) -> KeywordAnalysis:
        messages = [
            {
                "role": "system",
                "content": (
                    "You identify what an article or online discussion is about. "
                    "Return only JSON with a 'keywords' array. Keywords must be concise "
                    "topic labels, not full sentences."
                ),
            },
            {
                "role": "user",
                "content": self._build_prompt(document),
            },
        ]
        response_text = self.chat_model.complete(messages)
        keywords = sanitize_keywords(extract_keywords(response_text), max_keywords=self.max_keywords)
        if not keywords:
            raise LLMError(f"LLM returned no usable keywords for document {document.id}")

        return KeywordAnalysis(
            document_id=document.id,
            keywords=tuple(keywords),
            model=self.chat_model.model,
            prompt_version=PROMPT_VERSION,
            content_hash=document.content_hash,
        )

    def _build_prompt(self, document: StoredDocument) -> str:
        content = document.content[: self.content_char_limit]
        return (
            f"Find up to {self.max_keywords} keywords or short topic phrases for this "
            f"talent acquisition article/discussion. Answer in {self.output_language} "
            "when possible. Return JSON exactly like: {\"keywords\": [\"keyword\"]}.\n\n"
            f"Title: {document.title}\n"
            f"Original URL: {document.source_url}\n\n"
            f"Content:\n{content}"
        )


def analyze_stored_documents(
    *,
    database_path: str,
    chat_model: ChatModel,
    limit: int | None = None,
    force: bool = False,
    max_keywords: int = 5,
    content_char_limit: int = 8_000,
    output_language: str = "Finnish",
) -> KeywordAnalysisResult:
    analyzer = KeywordAnalyzer(
        chat_model=chat_model,
        max_keywords=max_keywords,
        content_char_limit=content_char_limit,
        output_language=output_language,
    )
    analyzed_count = 0
    error_count = 0

    with DocumentStore(database_path) as store:
        store.initialize()
        documents = store.documents_for_keyword_analysis(limit=limit, force=force)
        for document in documents:
            try:
                analysis = analyzer.analyze_document(document)
            except LLMError:
                error_count += 1
                continue

            store.save_keyword_analysis(analysis)
            analyzed_count += 1

    return KeywordAnalysisResult(
        documents_checked=len(documents),
        analyzed_count=analyzed_count,
        skipped_count=len(documents) - analyzed_count - error_count,
        error_count=error_count,
    )


def summarize_weekly_trends(
    *,
    database_path: str,
    chat_model: ChatModel,
    days: int = 7,
    max_bullets: int = 5,
    output_language: str = "Finnish",
) -> tuple[str, ...]:
    report_rows = build_weekly_keyword_report(database_path=database_path, days=days, top_n=20, links_per_keyword=3)
    if not report_rows:
        return ("Ei riittavasti uutta dataa nousevien trendien arviointiin.",)

    messages = [
        {
            "role": "system",
            "content": (
                "You analyze talent acquisition signals from weekly keyword data. "
                "Return only JSON with a 'trends' array. Each trend must be one concise bullet-worthy sentence."
            ),
        },
        {
            "role": "user",
            "content": _build_trend_summary_prompt(report_rows, max_bullets=max_bullets, output_language=output_language),
        },
    ]
    response_text = chat_model.complete(messages)
    trends = sanitize_trends(extract_trends(response_text), max_bullets=max_bullets)
    if not trends:
        raise LLMError("LLM returned no usable trend bullets")

    return tuple(trends)


def extract_keywords(response_text: str) -> list[str]:
    payload = _load_json_response(response_text)
    if isinstance(payload, dict):
        raw_keywords = payload.get("keywords", [])
    elif isinstance(payload, list):
        raw_keywords = payload
    else:
        raw_keywords = []

    if not isinstance(raw_keywords, list):
        raise LLMError("LLM response 'keywords' field was not a list")

    return [str(keyword) for keyword in raw_keywords]


def extract_trends(response_text: str) -> list[str]:
    payload = _load_json_response(response_text)
    if isinstance(payload, dict):
        raw_trends = payload.get("trends", [])
    elif isinstance(payload, list):
        raw_trends = payload
    else:
        raw_trends = []

    if not isinstance(raw_trends, list):
        raise LLMError("LLM response 'trends' field was not a list")

    return [str(trend) for trend in raw_trends]


def sanitize_keywords(keywords: list[str], *, max_keywords: int = 5) -> list[str]:
    clean_keywords: list[str] = []
    seen: set[str] = set()
    for keyword in keywords:
        normalized = re.sub(r"\s+", " ", keyword).strip(" .,;:-\n\t").lower()
        if not normalized or normalized in seen:
            continue

        seen.add(normalized)
        clean_keywords.append(normalized[:80])
        if len(clean_keywords) >= max_keywords:
            break

    return clean_keywords


def sanitize_trends(trends: list[str], *, max_bullets: int = 5) -> list[str]:
    clean_trends: list[str] = []
    seen: set[str] = set()
    for trend in trends:
        normalized = re.sub(r"\s+", " ", trend).strip(" -\n\t")
        if not normalized:
            continue

        key = normalized.lower()
        if key in seen:
            continue

        seen.add(key)
        clean_trends.append(normalized[:240])
        if len(clean_trends) >= max_bullets:
            break

    return clean_trends


def _build_trend_summary_prompt(report_rows: object, *, max_bullets: int, output_language: str) -> str:
    lines = []
    for row in report_rows:
        examples = "; ".join(f"{link.title} ({link.source_name})" for link in row.occurrence_links)
        lines.append(f"- {row.keyword}: {row.count} occurrence(s). Examples: {examples}")

    return (
        f"Based on this weekly talent acquisition keyword data, identify {max_bullets} emerging trends. "
        f"Answer in {output_language}. Avoid restating generic keywords. "
        "Return JSON exactly like: {\"trends\": [\"trend sentence\"]}.\n\n"
        + "\n".join(lines)
    )


def _load_json_response(response_text: str) -> Any:
    try:
        return json.loads(response_text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}|\[.*\]", response_text, flags=re.DOTALL)
    if not match:
        raise LLMError("LLM response did not contain JSON")

    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise LLMError("LLM response JSON could not be parsed") from exc
