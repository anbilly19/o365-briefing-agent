"""Tests for category_config.py."""

from pathlib import Path

import pytest
import yaml

from briefing_agent.category_config import CategoryConfig, CategoryMeta


@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    data = {
        "categories": [
            {
                "key": "needs_reply",
                "display_name": "Reply needed",
                "icon": "\u2709\ufe0f",
                "description": "A real person is waiting for your response.",
                "tag": None,
                "folder": None,
            },
            {
                "key": "fyi",
                "display_name": "FYI",
                "icon": "\u2139\ufe0f",
                "description": "Info only.",
                "tag": "info-tag",
                "folder": "FYI",
            },
        ]
    }
    p = tmp_path / "categories.yaml"
    p.write_text(yaml.dump(data))
    return p


@pytest.fixture
def cfg(config_file: Path) -> CategoryConfig:
    return CategoryConfig(config_path=config_file)


def test_get_returns_meta(cfg: CategoryConfig) -> None:
    meta = cfg.get("needs_reply")
    assert isinstance(meta, CategoryMeta)
    assert meta.display_name == "Reply needed"


def test_display_name(cfg: CategoryConfig) -> None:
    assert cfg.display_name("fyi") == "FYI"


def test_icon(cfg: CategoryConfig) -> None:
    assert cfg.icon("needs_reply") == "\u2709\ufe0f"


def test_tag_and_folder(cfg: CategoryConfig) -> None:
    meta = cfg.get("fyi")
    assert meta.tag == "info-tag"
    assert meta.folder == "FYI"


def test_unknown_key_returns_none(cfg: CategoryConfig) -> None:
    assert cfg.get("nonexistent") is None


def test_display_name_fallback(cfg: CategoryConfig) -> None:
    assert cfg.display_name("nonexistent") == "nonexistent"


def test_icon_fallback(cfg: CategoryConfig) -> None:
    assert cfg.icon("nonexistent") == ""


def test_all_returns_both(cfg: CategoryConfig) -> None:
    keys = {m.key for m in cfg.all()}
    assert keys == {"needs_reply", "fyi"}


def test_missing_config_file(tmp_path: Path) -> None:
    cfg = CategoryConfig(config_path=tmp_path / "missing.yaml")
    assert cfg.all() == []
    assert cfg.display_name("needs_reply") == "needs_reply"  # fallback to key
