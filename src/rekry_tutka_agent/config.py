from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import SourceConfig


def load_sources(path: str | Path) -> list[SourceConfig]:
    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    raw_sources = payload.get("sources") if isinstance(payload, dict) else payload
    if not isinstance(raw_sources, list):
        raise ValueError(f"{config_path} must contain a list or an object with a 'sources' list")

    sources = [_source_from_mapping(item, config_path) for item in raw_sources]
    if not sources:
        raise ValueError(f"{config_path} did not contain any sources")

    return sources


def _source_from_mapping(item: Any, config_path: Path) -> SourceConfig:
    if not isinstance(item, dict):
        raise ValueError(f"Each source in {config_path} must be an object")

    try:
        name = str(item["name"]).strip()
        url = str(item["url"]).strip()
    except KeyError as exc:
        raise ValueError(f"Source in {config_path} is missing required key: {exc.args[0]}") from exc

    if not name or not url:
        raise ValueError(f"Sources in {config_path} require non-empty name and url values")

    source_type = str(item.get("type", "feed")).strip().lower()
    if source_type != "feed":
        raise ValueError(f"Unsupported source type '{source_type}' for {name}; only 'feed' is supported")

    tags = item.get("tags", [])
    if not isinstance(tags, list):
        raise ValueError(f"tags for {name} must be a list")

    return SourceConfig(
        name=name,
        url=url,
        type=source_type,
        enabled=bool(item.get("enabled", True)),
        tags=tuple(str(tag) for tag in tags),
        fetch_content=bool(item.get("fetch_content", True)),
    )
