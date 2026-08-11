"""Tests for whyfxpg.webui.screens page split."""

import os
import sys
from pathlib import Path
from types import ModuleType

import pytest

# Make sure project root is importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Streamlit is imported transitively by page modules; keep it headless in tests.
os.environ.setdefault("STREAMLIT_SERVER_HEADLESS", "true")
os.environ.setdefault("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")
os.environ.setdefault("STREAMLIT_GLOBAL_DEVELOPMENTMODE", "false")

from whyfxpg.webui.screens import PAGES

EXPECTED_PAGES = [
    "📊 风险总览",
    "🖥️ 风险态势大屏",
    "📋 风险事件",
    "✅ 人工复核",
    "🔔 预警中心",
    "🔔 通知中心",
    "📄 报告中心",
    "🔗 因果知识图谱",
    "🌐 数据源监控",
    "⚙️ 数据源管理",
    "⚙️ 预警规则管理",
    "⚙️ 风险模型管理",
    "⚙️ 风险维度管理",
    "⚙️ 分类法管理",
]


def test_pages_order_and_count():
    assert list(PAGES.keys()) == EXPECTED_PAGES
    assert len(PAGES) == 14


@pytest.mark.parametrize("label", EXPECTED_PAGES)
def test_pages_render_callable(label):
    render = PAGES[label]
    assert callable(render)
    assert render.__name__ == "render"


def test_screen_modules_are_importable():
    from whyfxpg.webui.screens import (
        alerts,
        bigscreen,
        causal,
        notifications,
        overview,
        reports,
        review,
        risk_events,
        sources,
    )

    modules = [
        alerts,
        bigscreen,
        causal,
        notifications,
        overview,
        reports,
        review,
        risk_events,
        sources,
    ]
    for mod in modules:
        assert isinstance(mod, ModuleType)
        assert hasattr(mod, "render")
        assert callable(mod.render)


def test_app_entrypoint_compiles():
    """app.py should remain syntactically valid after the navigation-only refactor."""
    import py_compile

    app_path = PROJECT_ROOT / "whyfxpg" / "webui" / "app.py"
    py_compile.compile(str(app_path), doraise=True)
    source = app_path.read_text(encoding="utf-8")
    assert "from whyfxpg.webui.screens import PAGES" in source
    assert "PAGES[page]" in source or "render_page = PAGES[page]" in source


def test_screens_do_not_import_db_connection():
    """页面层只负责渲染，不直接持有数据库连接。"""
    from whyfxpg.webui.screens import (
        alerts,
        bigscreen,
        causal,
        notifications,
        overview,
        reports,
        review,
        risk_events,
        sources,
    )

    modules = [alerts, bigscreen, causal, notifications, overview, reports, review, risk_events, sources]
    for mod in modules:
        source = Path(mod.__file__).read_text(encoding="utf-8")
        assert "get_db_connection" not in source, f"{mod.__name__} still imports get_db_connection"


import ast as _ast


def test_screens_only_import_services_or_webui():
    """页面层只依赖 services 和 webui 内部模块，不直接接触 core/adapters。"""
    screens_dir = PROJECT_ROOT / "whyfxpg" / "webui" / "screens"
    for path in screens_dir.rglob("*.py"):
        if path.name.startswith("__"):
            continue
        tree = _ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in _ast.walk(tree):
            if not isinstance(node, _ast.ImportFrom) or not node.module:
                continue
            mod = node.module
            if mod.startswith(("whyfxpg.core", "whyfxpg.adapters")):
                raise AssertionError(f"{path.relative_to(PROJECT_ROOT)} imports {mod}")
            if mod.startswith("whyfxpg.") and not mod.startswith(
                ("whyfxpg.services", "whyfxpg.webui")
            ):
                raise AssertionError(f"{path.relative_to(PROJECT_ROOT)} imports {mod}")
