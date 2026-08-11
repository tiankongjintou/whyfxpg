"""
一次性辅助脚本：为生产数据库启用 WAL 模式。

用法：
    .venv/Scripts/python scripts/enable_wal.py

作用：
    - 使用 MigrationRunner 创建/迁移 schema
    - 设置 SQLite journal_mode=WAL
    - 设置 busy_timeout=10000
    - 不会删除或覆盖已有数据，仅创建缺失的表和索引

注意：
    运行前请确保没有其它进程正在写入 whyfxpg/data/whyfxpg.db，
    否则切换 journal mode 可能失败。
"""

import sqlite3

from whyfxpg.core.db import DEFAULT_DB_PATH, get_db_connection
from whyfxpg.migrations import MigrationRunner

if __name__ == "__main__":
    conn = get_db_connection(str(DEFAULT_DB_PATH))
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=10000")
        MigrationRunner(conn).run()
        conn.commit()
    finally:
        conn.close()
    print("WAL 已启用：", DEFAULT_DB_PATH)
