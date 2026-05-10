from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_USER_AGENT = (
    "rekry-tutka-agent/0.1 "
    "(talent-acquisition-research; respectful feed and article ingestion)"
)


class FetchError(RuntimeError):
    """Raised when a source cannot be fetched."""


class TextFetcher(Protocol):
    def fetch_text(self, url: str) -> str:
        """Fetch a URL and return decoded text."""


@dataclass(frozen=True)
class HttpFetcher:
    timeout_seconds: float = 20
    max_bytes: int = 2_500_000
    user_agent: str = DEFAULT_USER_AGENT

    def fetch_text(self, url: str) -> str:
        request = Request(
            url,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "application/rss+xml, application/atom+xml, text/html, */*;q=0.8",
            },
        )

        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                body = response.read(self.max_bytes + 1)
                if len(body) > self.max_bytes:
                    raise FetchError(f"Response from {url} exceeded {self.max_bytes} bytes")

                content_type = response.headers.get("content-type", "")
                charset = response.headers.get_content_charset() or _charset_from_content_type(content_type)
                return body.decode(charset or "utf-8", errors="replace")
        except HTTPError as exc:
            raise FetchError(f"HTTP {exc.code} while fetching {url}") from exc
        except URLError as exc:
            raise FetchError(f"Could not fetch {url}: {exc.reason}") from exc
        except TimeoutError as exc:
            raise FetchError(f"Timed out fetching {url}") from exc


def _charset_from_content_type(content_type: str) -> str | None:
    for part in content_type.split(";"):
        key, _, value = part.strip().partition("=")
        if key.lower() == "charset" and value:
            return value.strip()
    return None
