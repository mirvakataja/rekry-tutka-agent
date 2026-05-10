from __future__ import annotations

from xml.etree import ElementTree

from .date_utils import normalize_date
from .html_extract import clean_text, html_fragment_to_text
from .models import CollectedItem, SourceConfig


TITLE_FIELDS = {"title"}
LINK_FIELDS = {"link", "guid", "id"}
DATE_FIELDS = {"pubdate", "published", "updated", "date", "issued", "modified"}
CONTENT_FIELDS = {"encoded", "content", "summary", "description", "subtitle"}


def parse_feed(xml_text: str, source: SourceConfig) -> list[CollectedItem]:
    """Parse RSS or Atom XML into normalized collection items."""

    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError as exc:
        raise ValueError(f"Could not parse feed from {source.name}: {exc}") from exc

    entries = _find_feed_entries(root)
    items: list[CollectedItem] = []
    for entry in entries:
        title = clean_text(_child_text(entry, TITLE_FIELDS))
        url = _entry_link(entry)
        content = html_fragment_to_text(_child_text(entry, CONTENT_FIELDS))
        publication_date = normalize_date(_child_text(entry, DATE_FIELDS))

        if not title or not url:
            continue

        items.append(
            CollectedItem(
                source_name=source.name,
                title=title,
                source_url=url,
                content=content,
                publication_date=publication_date,
                metadata={"source_tags": list(source.tags), "source_type": source.type},
            )
        )

    return items


def _find_feed_entries(root: ElementTree.Element) -> list[ElementTree.Element]:
    entries: list[ElementTree.Element] = []
    for element in root.iter():
        local = _local_name(element.tag)
        if local in {"item", "entry"}:
            entries.append(element)
    return entries


def _entry_link(entry: ElementTree.Element) -> str | None:
    for child in entry:
        local = _local_name(child.tag)
        if local != "link":
            continue

        href = child.attrib.get("href")
        rel = child.attrib.get("rel", "alternate")
        if href and rel in {"alternate", "self", ""}:
            return href.strip()

        if child.text and child.text.strip():
            return child.text.strip()

    return clean_text(_child_text(entry, LINK_FIELDS)) or None


def _child_text(entry: ElementTree.Element, names: set[str]) -> str | None:
    for child in entry:
        local = _local_name(child.tag)
        if local in names:
            text = "".join(child.itertext()).strip()
            if text:
                return text
    return None


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1].lower()
    if ":" in tag:
        return tag.rsplit(":", 1)[1].lower()
    return tag.lower()
