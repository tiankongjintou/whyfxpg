"""Architecture health check for the WHYfxpg seam refactor (T21).

This script verifies the concrete refactor targets completed in this task:

- ``core/stores.py`` has been removed; stores live under ``adapters/`` and
  ``services/``.
- ``core/llm_client.py`` has been removed; LLM access goes through the
  ``LLMPort`` adapter.
- ``adapters/multimodal.py`` exists and is free of imports from
  ``whyfxpg.core.llm_client``.
- ``services/causal_service.py`` exists and exposes the causal UI seam.
- ``webui/screens/causal.py`` imports only from ``whyfxpg.services`` (plus
  stdlib/third-party/webui helpers).

It also prints warnings for other screens that still reach into ``core`` or
``adapters`` directly so the remaining architectural debt is visible.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WHYFXPG_ROOT = PROJECT_ROOT / "whyfxpg"

_failed = False
_warnings = 0


def fail(message: str) -> None:
    global _failed
    _failed = True
    print(f"FAIL: {message}")


def warn(message: str) -> None:
    global _warnings
    _warnings += 1
    print(f"WARN: {message}")


def ok(message: str) -> None:
    print(f"OK:   {message}")


def module_imports(path: Path) -> set[str]:
    """Return all top-level `from whyfxpg.X import ...` targets in a file."""
    imports: set[str] = set()
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as e:
        fail(f"{path}: syntax error: {e}")
        return imports

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.startswith("whyfxpg."):
                imports.add(node.module)
    return imports


def main() -> int:
    # 1. legacy core/stores.py must not exist
    legacy_stores = WHYFXPG_ROOT / "core" / "stores.py"
    if legacy_stores.exists():
        fail(f"legacy core/stores.py still exists: {legacy_stores}")
    else:
        ok("core/stores.py removed")

    # 2. legacy core/llm_client.py must not exist
    legacy_llm_client = WHYFXPG_ROOT / "core" / "llm_client.py"
    if legacy_llm_client.exists():
        fail(f"legacy core/llm_client.py still exists: {legacy_llm_client}")
    else:
        ok("core/llm_client.py removed")

    # 3. adapters/multimodal.py exists and does not import legacy llm_client
    multimodal = WHYFXPG_ROOT / "adapters" / "multimodal.py"
    if not multimodal.exists():
        fail("adapters/multimodal.py missing")
    else:
        text = multimodal.read_text(encoding="utf-8")
        if "llm_client" in text or "get_llm_client" in text:
            fail("adapters/multimodal.py still references legacy llm_client")
        else:
            ok("adapters/multimodal.py present and decoupled from llm_client")

    # 4. services/causal_service.py exists
    causal_service = WHYFXPG_ROOT / "services" / "causal_service.py"
    if not causal_service.exists():
        fail("services/causal_service.py missing")
    else:
        ok("services/causal_service.py present")

    # 5. causal screen imports only from whyfxpg.services (or webui helpers)
    causal_screen = WHYFXPG_ROOT / "webui" / "screens" / "causal.py"
    bad = {
        imp
        for imp in module_imports(causal_screen)
        if not imp.startswith(("whyfxpg.services", "whyfxpg.webui"))
    }
    if bad:
        fail(f"causal.py imports outside services: {sorted(bad)}")
    else:
        ok("webui/screens/causal.py only imports from whyfxpg.services")

    # 6. adapters/reports must not import core.db directly
    reports_dir = WHYFXPG_ROOT / "adapters" / "reports"
    for report_file in reports_dir.rglob("*.py"):
        if report_file.name.startswith("__"):
            continue
        text = report_file.read_text(encoding="utf-8")
        if "get_db_connection" in text or "from whyfxpg.core.db" in text:
            fail(f"adapters/reports/{report_file.name} imports get_db_connection directly")
    if not _failed:
        ok("adapters/reports/ does not import get_db_connection directly")

    # 7. adapters/ and services/ are non-empty package directories
    for pkg in (WHYFXPG_ROOT / "adapters", WHYFXPG_ROOT / "services"):
        py_files = [f for f in pkg.rglob("*.py") if not f.name.startswith("__")]
        if py_files:
            ok(f"{pkg.name}/ contains {len(py_files)} module(s)")
        else:
            fail(f"{pkg.name}/ has no modules")

    # 8. informational warnings for remaining screens that still import core/adapters
    screens_dir = WHYFXPG_ROOT / "webui" / "screens"
    for screen in screens_dir.rglob("*.py"):
        if screen.name.startswith("__"):
            continue
        imports = module_imports(screen)
        bad_core = {imp for imp in imports if imp.startswith(("whyfxpg.core", "whyfxpg.adapters"))}
        if bad_core:
            warn(
                f"{screen.relative_to(PROJECT_ROOT)} still imports core/adapters: "
                f"{sorted(bad_core)}"
            )

    print()
    if _failed:
        print("Architecture check failed.")
        return 1
    if _warnings:
        print(f"Architecture check passed with {_warnings} warning(s).")
    else:
        print("Architecture check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
