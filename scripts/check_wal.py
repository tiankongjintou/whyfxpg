#!/usr/bin/env python3
"""检查 whyfxpg.db 是否启用 WAL 模式。

用法：
    python scripts/check_wal.py
    python scripts/check_wal.py --db-path /path/to/whyfxpg.db

退出码：
    0 - journal_mode = wal
    1 - 未启用 WAL 或发生错误
"""

import argparse
import sqlite3
import sys
from pathlib import Path

# 支持从项目根目录直接运行
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from whyfxpg.core.db import DEFAULT_DB_PATH


def check_wal(db_path: Path) -> int:
    if not db_path.exists():
        print(f"ERROR: 数据库不存在: {db_path}")
        return 1

    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode")
        journal_mode = cursor.fetchone()[0]
        cursor.execute("PRAGMA synchronous")
        synchronous = cursor.fetchone()[0]
        cursor.execute("PRAGMA wal_autocheckpoint")
        wal_autocheckpoint = cursor.fetchone()[0]
        cursor.execute("PRAGMA busy_timeout")
        busy_timeout = cursor.fetchone()[0]
        conn.close()
    except Exception as e:  # noqa: BLE001 — 外部调用/配置解析兜底,刻意吞异常
        print(f"ERROR: 读取数据库失败: {e}")
        return 1

    print(f"数据库: {db_path}")
    print(f"  journal_mode      : {journal_mode}")
    print(f"  synchronous       : {synchronous}")
    print(f"  wal_autocheckpoint: {wal_autocheckpoint}")
    print(f"  busy_timeout      : {busy_timeout} ms")

    if journal_mode.lower() != "wal":
        print(f"ERROR: 未启用 WAL 模式 (当前为 {journal_mode})")
        return 1

    print("OK: WAL 模式已启用")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="检查 SQLite WAL 模式")
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB_PATH,
        help="数据库路径（默认 whyfxpg/data/whyfxpg.db）",
    )
    args = parser.parse_args()
    sys.exit(check_wal(args.db_path))
