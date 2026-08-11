#!/usr/bin/env python3
"""WHYFXPG 质量门禁：一键运行所有质量检查。

用法：
    python scripts/quality_gate.py
    python scripts/quality_gate.py --skip-tests    # 仅运行 linter 和 type checker

退出码：
    0 = 全部通过
    1 = 任意一项失败
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def find_python() -> str:
    """查找项目根目录的 Python 解释器（优先 venv）。"""
    venv_python = ROOT / ".venv" / "Scripts" / "python.exe"
    if venv_python.exists():
        return str(venv_python)
    return sys.executable


def run(name: str, cmd: list[str], cwd: Path = ROOT) -> bool:
    """运行单个命令，返回是否成功。"""
    print(f"\n{'='*60}")
    print(f"  {name}")
    print(f"{'='*60}")
    print(f"  $ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(cwd))
    return result.returncode == 0


def main() -> int:
    args = sys.argv[1:]
    skip_tests = "--skip-tests" in args
    if skip_tests:
        args.remove("--skip-tests")

    print("=" * 60)
    print("  WHYFXPG 质量门禁")
    print("=" * 60)

    checks = []

    python = find_python()

    # 1. pytest（如果没跳过）— 测试位于 whyfxpg/tests/（根目录的 test_*.py 为过时 UI 孤儿脚本，不纳入）
    if not skip_tests:
        checks.append(("1. pytest (whyfxpg/tests/)", [python, "-m", "pytest", "whyfxpg/tests/", "-v", "--tb=short"]))

    # 2. ruff check — whyfxpg/
    checks.append(("2. ruff check (whyfxpg/)", [python, "-m", "ruff", "check", "whyfxpg/"]))

    # 3. ruff check — whyfxpg_api/（如果存在）
    api_path = ROOT / "whyfxpg_api"
    if api_path.exists():
        checks.append(("2b. ruff check (whyfxpg_api/)", [python, "-m", "ruff", "check", "whyfxpg_api/"]))

    # 4. mypy — whyfxpg/
    checks.append(("3. mypy (whyfxpg/)", [python, "-m", "mypy", "whyfxpg/"]))

    # 5. mypy — whyfxpg_api/（如果存在）
    if api_path.exists():
        checks.append(("3b. mypy (whyfxpg_api/)", [python, "-m", "mypy", "whyfxpg_api/"]))

    results = []
    for name, cmd in checks:
        ok = run(name, cmd)
        results.append((name, ok))

    # 汇总
    print(f"\n{'='*60}")
    print("  汇总")
    print(f"{'='*60}")
    all_ok = True
    for name, ok in results:
        status = "✅ PASS" if ok else "❌ FAIL"
        print(f"  {status}  {name}")
        if not ok:
            all_ok = False

    if all_ok:
        print("\n✅ 全部质量门禁通过")
        return 0
    else:
        print("\n❌ 质量门禁失败 — 请修复上述问题后再 commit")
        return 1


if __name__ == "__main__":
    sys.exit(main())
