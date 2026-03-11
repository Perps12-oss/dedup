"""Tests for engine/media_types.py."""

from __future__ import annotations

import pytest
from dedup.engine.media_types import (
    get_extensions_for_category,
    get_category_label,
    list_categories,
    is_image_extension,
    CATEGORY_ALL,
    CATEGORY_IMAGES,
)


def test_get_extensions_all_returns_none():
    assert get_extensions_for_category(None) is None
    assert get_extensions_for_category("all") is None
    assert get_extensions_for_category("  ALL  ") is None


def test_get_extensions_images():
    exts = get_extensions_for_category("images")
    assert exts is not None
    assert "jpg" in exts
    assert "png" in exts
    assert "jpeg" in exts


def test_get_extensions_unknown_returns_none():
    assert get_extensions_for_category("unknown") is None


def test_get_category_label():
    assert get_category_label("all") == "All Files"
    assert get_category_label("images") == "Images"


def test_list_categories():
    cats = list_categories()
    assert CATEGORY_ALL in cats
    assert CATEGORY_IMAGES in cats
    assert cats[0] == CATEGORY_ALL


def test_is_image_extension():
    assert is_image_extension(".jpg") is True
    assert is_image_extension("png") is True
    assert is_image_extension(".txt") is False
