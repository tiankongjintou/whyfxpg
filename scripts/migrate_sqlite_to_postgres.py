#!/usr/bin/env python3
"""SQLite → PostgreSQL 数据迁移脚本（P01）。

把 Phase 0 的 SQLite 数据完整迁移到 Phase 1 的 PostgreSQL 多租户 schema。

用法（在项目根目录执行）：:

    python scripts/migrate_sqlite_to_postgres.py [--sqlite path/to/whyfxpg.db]

- ``--sqlite``：源 SQLite 文件路径，默认 ``data/whyfxpg.db``。
- 目标连接串来自环境变量 ``DATABASE_URL``（必须为 ``postgresql://...``），
  与 docker-compose / alembic 约定一致。

流程：
1. 在 PostgreSQL 上执行 ``alembic upgrade head`` —— 创建 accounts、
   risk_events、alert_records（含 account_id 外键）与索引（P01 的 0001 迁移）。
2. 对 SQLite 中其余表（monitor_sources、causal_nodes、pipeline_runs 等）
   自动生成 PostgreSQL 兼容 DDL 并创建。
3. 逐表逐行拷贝数据（accounts/risk_events/alert_records 由 Alembic 建表，
   仅拷贝数据；其余表建表 + 拷贝）。
4. 校验每张表行数一致，输出迁移报告。

幂等性：已在 PG 上的表跳过建表；数据拷贝前清空目标表（TRUNCATE），
可安全重复执行。
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text

from whyfxpg.core.db import is_postgres_url
from whyfxpg.migrations.sqlite_to_pg import (
    ALEMBIC_MANAGED_TABLES,
    generate_pg_ddl,
    list_tables,
    sqlite_table_info,
)


def run_migrations(pg_url: str) -> None:
    """在 PostgreSQL 上执行 Alembic 迁移到 head。"""
    from alembic.config import Config

    from alembic import command

    root = Path(__file__).resolve().parent.parent
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", pg_url)
    command.upgrade(cfg, "head")


def copy_table(
    src: sqlite3.Connection,
    dst_engine: Any,
    table: str,
) -> int:
    """把一张表的数据从 SQLite 拷贝到 PostgreSQL，返回拷贝行数。"""
    rows = src.execute(f'SELECT * FROM "{table}"').fetchall()
    if not rows:
        return 0
    columns = [d[0] for d in src.description]
    placeholders = ", ".join([":" + c for c in columns])
    column_list = ", ".join(f'"{c}"' for c in columns)
    sql = f'INSERT INTO "{table}" ({column_list}) VALUES ({placeholders})'
    with dst_engine.begin() as conn:
        conn.execute(text(f'TRUNCATE TABLE "{table}"'))
        for row in rows:
            conn.execute(text(sql), dict(zip(columns, row)))
    return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="SQLite → PostgreSQL 数据迁移")
    parser.add_argument("--sqlite", default=str(Path("data") / "whyfxpg.db"))
    args = parser.parse_args()

    pg_url = os.environ.get("DATABASE_URL", "")
    if not is_postgres_url(pg_url):
        print("❌ DATABASE_URL 必须为 postgresql:// 连接串", file=sys.stderr)
        return 1

    sqlite_path = Path(args.sqlite)
    if not sqlite_path.exists():
        print(f"❌ SQLite 源文件不存在: {sqlite_path}", file=sys.stderr)
        return 1

    print(f"源: SQLite {sqlite_path}")
    print(f"目标: {pg_url.split('@')[-1]}")

    # 1. Alembic 迁移（创建多租户核心表 + 索引）
    print("\n[1/4] 执行 alembic upgrade head ...")
    run_migrations(pg_url)

    dst_engine = create_engine(pg_url)
    src = sqlite3.connect(str(sqlite_path))
    src.row_factory = sqlite3.Row

    # 2. 其余表自动生成 DDL
    print("\n[2/4] 生成其余表 DDL ...")
    tables = list_tables(src)
    created = 0
    for table in tables:
        if table in ALEMBIC_MANAGED_TABLES:
            continue
        ddl = generate_pg_ddl(table, sqlite_table_info(src, table))
        with dst_engine.begin() as conn:
            conn.execute(text(ddl))
        created += 1
    print(f"  创建/确保 {created} 张表")

    # 3. 数据拷贝
    print("\n[3/4] 拷贝数据 ...")
    report: list[str] = []
    for table in tables:
        copied = copy_table(src, dst_engine, table)
        report.append(f"  {table}: {copied} 行")
        print(f"  {table}: {copied} 行")

    # 4. 行数校验
    print("\n[4/4] 行数校验 ...")
    ok = True
    for table in tables:
        src_count = src.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        with dst_engine.connect() as conn:
            dst_count = conn.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar()
        match = "✅" if src_count == dst_count else "❌"
        if src_count != dst_count:
            ok = False
        print(f"  {match} {table}: SQLite={src_count} PG={dst_count}")

    src.close()
    dst_engine.dispose()
    print("\n" + ("✅ 迁移完成" if ok else "❌ 迁移存在不一致，请检查上述 ❌ 行"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
