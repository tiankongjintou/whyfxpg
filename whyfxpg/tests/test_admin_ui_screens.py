"""Tests for admin UI screens."""

from pathlib import Path

import pytest

from whyfxpg.webui.screens import PAGES

ADMIN_SCREEN_DIR = Path(__file__).resolve().parent.parent.parent / "webui" / "screens" / "admin"


@pytest.mark.parametrize("module_path", sorted(ADMIN_SCREEN_DIR.glob("*.py")))
def test_admin_screen_no_direct_db_access(module_path):
    code = module_path.read_text(encoding="utf-8")
    assert "get_db_connection" not in code, f"{module_path.name} imports get_db_connection"
    assert "open(" not in code or "with open(" not in code, f"{module_path.name} uses open()"


def test_admin_pages_registered():
    labels = [label for label in PAGES if label.startswith("⚙️")]
    assert len(labels) >= 5
