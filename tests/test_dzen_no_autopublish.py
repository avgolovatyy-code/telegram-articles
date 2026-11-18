from __future__ import annotations

import ast
from pathlib import Path

from app.dzen import NATIVE_AUTOPUBLISH_FORBIDDEN


def test_native_autopublish_flag_defaults_false(settings):
    assert settings.dzen_native_autopublish_enabled is False
    assert NATIVE_AUTOPUBLISH_FORBIDDEN is True


def test_dzen_package_has_no_browser_automation():
    banned = ("playwright", "Playwright", "chromium.launch", "CDP", "yandexid", "Yandex ID")
    root = Path("app/dzen")
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in banned:
            assert token not in text, f"{token} in {path}"
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "playwright" not in alias.name
            if isinstance(node, ast.ImportFrom) and node.module:
                assert "playwright" not in node.module
