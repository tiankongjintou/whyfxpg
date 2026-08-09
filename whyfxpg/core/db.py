"""
数据库 Schema 初始化模块 (M0)

功能：
- 创建系统所需的所有数据库表
- 提供数据库连接工具
- 不依赖其他业务模块，只被其他模块调用

输入：无
输出：SQLite 数据库文件 whyfxpg.db
"""

import sqlite3
from pathlib import Path
from typing import Optional

from whyfxpg.migrations import MigrationRunner

# 默认数据库路径
DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "whyfxpg.db"


def get_db_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """创建并返回一个 sqlite3 连接，启用 row_factory 与 busy_timeout。"""
    path = db_path or str(DEFAULT_DB_PATH)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=10000")
    return conn


def init_db(db_path: Optional[str] = None) -> None:
    """
    初始化数据库 schema（兼容 shim）。

    内部使用 MigrationRunner 执行版本化迁移，并启用 WAL 与 busy_timeout。
    新代码建议直接使用 `MigrationRunner(conn).run()`。
    """
    path = Path(db_path) if db_path else DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = get_db_connection(str(path))
    try:
        # 非内存数据库启用 WAL，提高并发读写性能
        if str(path) != ":memory:":
            conn.execute("PRAGMA journal_mode=WAL")
        MigrationRunner(conn).run()
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
    print(f"数据库初始化完成：{DEFAULT_DB_PATH}")
