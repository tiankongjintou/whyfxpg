#!/usr/bin/env python3
"""一键运行 WHYfxpg 测试套件并输出覆盖率。

用法：
    python scripts/run_tests.py
    python scripts/run_tests.py --no-cov
    python scripts/run_tests.py -- -k store

所有未知参数会透传给 pytest。
"""

import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    args = sys.argv[1:]
    no_cov = "--no-cov" in args
    if no_cov:
        args.remove("--no-cov")

    pytest_args = [sys.executable, "-m", "pytest", "-q", "--tb=short"]
    if not no_cov:
        cov_available = importlib.util.find_spec("pytest_cov") is not None
        if not cov_available:
            print(
                "ERROR: pytest-cov is required for the default test run. "
                "Install it with: .venv\\Scripts\\python -m pip install pytest-cov\n"
                "Or run with --no-cov to skip coverage."
            )
            return 1
        pytest_args.extend([
            "--cov=whyfxpg",
            "--cov-report=term-missing",
            "--cov-report=html:htmlcov",
        ])
    pytest_args.extend(args)

    print(f"运行: {' '.join(pytest_args)}")
    return subprocess.call(pytest_args, cwd=str(ROOT))


if __name__ == "__main__":
    sys.exit(main())
