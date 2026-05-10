from __future__ import annotations

from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
import re
from urllib.parse import urldefrag, urljoin, urlparse

from .date_utils import normalize_date


SKIPPED_TAGS = {"script", "style", "noscript", "svg", "canvas", "form"}
BLOCK_TAGS = {
    "article",
    "aside",
    "blockquote",
    "br",
    "dd",
    "div",
    "dl",
    "dt",
    "figcaption",
    "figure",
    "footer",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "header",
    "li",
    "main",
    "nav",
    "ol",
    "p",
    "pre",
    "section",
    "table",
    "td",
    "th",
    "tr",
    "ul",
}
DATE_META_NAMES = {
    "article:published_time",
    "date",
    "datepublished",
    "dc.date",
    "dc.date.issued",
    "pubdate",
    "publishdate",
    "published_time",
}


@dataclass(frozen=True)
class ExtractedHtml:
    title: str | None
    content: str
    publication_date: str | None


class _ReadableHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._in_title = False
        self._title_parts: list[str] = []
        self._body_parts: list[str] = []
        self._publication_date: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attr_map = {name.lower(): (value or "") for name, value in attrs}

        if tag in SKIPPED_TAGS:
            self._skip_depth += 1
            return

        if tag == "title":
            self._in_title = True
        elif tag == "meta":
            self._capture_meta_date(attr_map)
        elif tag == "time" and not self._publication_date:
            datetime_value = attr_map.get("datetime")
            self._publication_date = normalize_date(datetime_value)

        if tag in BLOCK_TAGS:
            self._body_parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in SKIPPED_TAGS and self._skip_depth:
            self._skip_depth -= 1
            return

        if tag == "title":
            self._in_title = False

        if tag in BLOCK_TAGS:
            self._body_parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return

        if self._in_title:
            self._title_parts.append(data)
        else:
            self._body_parts.append(data)

    def _capture_meta_date(self, attr_map: dict[str, str]) -> None:
        if self._publication_date:
            return

        key = (attr_map.get("property") or attr_map.get("name") or "").lower()
        if key in DATE_META_NAMES:
            self._publication_date = normalize_date(attr_map.get("content"))

    @property
    def extracted(self) -> ExtractedHtml:
        title = clean_text(" ".join(self._title_parts)) or None
        content = clean_text(" ".join(self._body_parts))
        return ExtractedHtml(
            title=title,
            content=content,
            publication_date=self._publication_date,
        )


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return

        for name, value in attrs:
            if name.lower() == "href" and value:
                self.hrefs.append(value)
                return


def extract_html(html: str) -> ExtractedHtml:
    parser = _ReadableHtmlParser()
    parser.feed(html)
    extracted = parser.extracted
    publication_date = extracted.publication_date or _extract_json_ld_publication_date(html)
    return ExtractedHtml(
        title=extracted.title,
        content=extracted.content,
        publication_date=publication_date,
    )


def html_fragment_to_text(fragment: str | None) -> str:
    if not fragment:
        return ""

    parser = _ReadableHtmlParser()
    parser.feed(fragment)
    return parser.extracted.content


def extract_links(html: str, *, base_url: str, path_prefix: str | None = None) -> list[str]:
    parser = _LinkParser()
    parser.feed(html)

    links: list[str] = []
    seen: set[str] = set()
    for href in parser.hrefs:
        absolute, _fragment = urldefrag(urljoin(base_url, href))
        if not _matches_path_prefix(absolute, path_prefix):
            continue

        if absolute not in seen:
            seen.add(absolute)
            links.append(absolute)

    return links


def clean_text(value: str | None) -> str:
    if not value:
        return ""

    decoded = unescape(value)
    collapsed = re.sub(r"[ \t\r\f\v]+", " ", decoded)
    collapsed = re.sub(r"\n\s*", "\n", collapsed)
    collapsed = re.sub(r"\n{3,}", "\n\n", collapsed)
    return collapsed.strip()


def _matches_path_prefix(url: str, path_prefix: str | None) -> bool:
    if not path_prefix:
        return True

    parsed = urlparse(url)
    return parsed.path.startswith(path_prefix)


def _extract_json_ld_publication_date(html: str) -> str | None:
    match = re.search(r'"datePublished"\s*:\s*"([^"]+)"', html)
    if not match:
        return None

    return normalize_date(match.group(1))
