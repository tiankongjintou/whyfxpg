import sqlite3
from pathlib import Path

import pytest

from whyfxpg.migrations.runner import MigrationRunner


@pytest.fixture
def tmp_migrations(tmp_path: Path) -> Path:
    """提供一个干净的临时迁移目录，仅含 001 业务表。"""
    d = tmp_path / "migrations"
    d.mkdir()
    (d / "001_baseline.sql").write_text(
        "CREATE TABLE IF NOT EXISTS t1 (id INTEGER PRIMARY KEY);", encoding="utf-8"
    )
    (d / "002_add_column.py").write_text(
        """import sqlite3

def run(conn: sqlite3.Connection) -> None:
    cur = conn.execute("PRAGMA table_info(t1)")
    cols = {row[1] for row in cur.fetchall()}
    if "name" not in cols:
        conn.execute("ALTER TABLE t1 ADD COLUMN name TEXT")
""",
        encoding="utf-8",
    )
    (d / "003_index.sql").write_text(
        "CREATE INDEX IF NOT EXISTS idx_t1_name ON t1(name);", encoding="utf-8"
    )
    return d


@pytest.fixture
def conn() -> sqlite3.Connection:
    return sqlite3.connect(":memory:")


def test_migration_runner_applies_all_on_fresh_db(conn: sqlite3.Connection, tmp_migrations: Path) -> None:
    runner = MigrationRunner(conn, migrations_dir=tmp_migrations)
    applied = runner.run()
    assert applied == ["001", "002", "003"]

    # schema_migrations 表已创建并记录版本
    cur = conn.execute("SELECT version FROM schema_migrations ORDER BY version")
    assert [row[0] for row in cur.fetchall()] == ["001", "002", "003"]

    # t1 表和索引存在
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='t1'")
    assert cur.fetchone() is not None
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_t1_name'")
    assert cur.fetchone() is not None


def test_migration_runner_is_idempotent(conn: sqlite3.Connection, tmp_migrations: Path) -> None:
    runner = MigrationRunner(conn, migrations_dir=tmp_migrations)
    assert runner.run() == ["001", "002", "003"]
    assert runner.run() == []


def test_migration_runner_respects_target(conn: sqlite3.Connection, tmp_migrations: Path) -> None:
    runner = MigrationRunner(conn, migrations_dir=tmp_migrations)
    assert runner.run(target="002") == ["001", "002"]
    cur = conn.execute("SELECT version FROM schema_migrations ORDER BY version")
    assert [row[0] for row in cur.fetchall()] == ["001", "002"]

    # 继续到最新
    assert runner.run() == ["003"]


def test_migration_runner_fails_on_bad_sql_and_does_not_record(conn: sqlite3.Connection, tmp_migrations: Path) -> None:
    runner = MigrationRunner(conn, migrations_dir=tmp_migrations)
    runner.run()  # 001-003 先成功

    bad_sql = tmp_migrations / "004_bad.sql"
    bad_sql.write_text("CREATE TABLE syntax_error_no_semicolon", encoding="utf-8")

    with pytest.raises(sqlite3.OperationalError):
        runner.run()

    # 004 不应被记录
    cur = conn.execute("SELECT version FROM schema_migrations WHERE version='004'")
    assert cur.fetchone() is None


def test_migration_runner_baseline_existing_db(conn: sqlite3.Connection, tmp_migrations: Path) -> None:
    # 模拟已有数据库：表已存在，但还没有 schema_migrations
    conn.execute("CREATE TABLE t1 (id INTEGER PRIMARY KEY)")
    conn.execute("INSERT INTO t1 (id) VALUES (1)")
    conn.commit()

    runner = MigrationRunner(conn, migrations_dir=tmp_migrations)
    applied = runner.run()
    # 已有表，但版本仍未记录，所以全部标记为已应用
    assert applied == ["001", "002", "003"]
    # 原有数据保留
    cur = conn.execute("SELECT id FROM t1")
    assert cur.fetchone()[0] == 1
    # 新增列被应用
    conn.execute("INSERT INTO t1 (id, name) VALUES (2, 'x')")
    conn.commit()


def test_python_migration_guard_skips_existing_column(conn: sqlite3.Connection, tmp_migrations: Path) -> None:
    # 先创建表并包含 name 列，002 应安全跳过
    conn.execute("CREATE TABLE t1 (id INTEGER PRIMARY KEY, name TEXT)")
    conn.commit()

    runner = MigrationRunner(conn, migrations_dir=tmp_migrations)
    runner.run()
    cur = conn.execute("PRAGMA table_info(t1)")
    cols = {row[1] for row in cur.fetchall()}
    assert "name" in cols


def test_migration_runner_pending(conn: sqlite3.Connection, tmp_migrations: Path) -> None:
    runner = MigrationRunner(conn, migrations_dir=tmp_migrations)
    pending = runner.pending()
    assert [m.version for m in pending] == ["001", "002", "003"]
    runner.run()
    assert runner.pending() == []
