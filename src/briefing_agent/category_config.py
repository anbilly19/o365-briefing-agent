"""Loads categories.yaml and exposes a display map for briefing output.

This decouples user-facing labels from the internal TriageCategory enum,
allowing users to rename categories or map them to Thunderbird tags / IMAP
folders without touching any Python code.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

_DEFAULT_CONFIG_PATH = Path("config/categories.yaml")


@dataclass
class CategoryMeta:
    key: str
    display_name: str
    icon: str
    description: str
    tag: str | None = None
    folder: str | None = None


class CategoryConfig:
    """Provides display metadata for each TriageCategory."""

    def __init__(self, config_path: Path = _DEFAULT_CONFIG_PATH) -> None:
        self._map: dict[str, CategoryMeta] = {}
        self._load(config_path)

    def _load(self, path: Path) -> None:
        if not path.exists():
            return
        data: dict[str, Any] = yaml.safe_load(path.read_text())
        for entry in data.get("categories", []):
            key = entry["key"]
            self._map[key] = CategoryMeta(
                key=key,
                display_name=entry.get("display_name", key),
                icon=entry.get("icon", ""),
                description=entry.get("description", ""),
                tag=entry.get("tag"),
                folder=entry.get("folder"),
            )

    def get(self, key: str) -> CategoryMeta | None:
        return self._map.get(key)

    def display_name(self, key: str) -> str:
        meta = self._map.get(key)
        return meta.display_name if meta else key

    def icon(self, key: str) -> str:
        meta = self._map.get(key)
        return meta.icon if meta else ""

    def all(self) -> list[CategoryMeta]:
        return list(self._map.values())
