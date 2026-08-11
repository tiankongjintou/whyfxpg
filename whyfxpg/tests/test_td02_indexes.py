"""TD02: 数据库索引补全测试。

覆盖：
- 0002 迁移在 SQLite 上执行后补齐 risk_events/alert_records 索引与列，
  pipeline_runs 表不存在时条件跳过不报错；
- EXPLAIN QUERY PLAN 验证 manufacturer 查询实际使用索引；
- downgrade 完整回滚。
"""

import sqlite3
from pathlib import Path

from sqlalchemy import create_engine, inspect

from whyfxpg.migrations.sqlite_to_pg import generate_pg_ddl, sqlite_table_info

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _run_alembic(db_path: Path, rev: str) -> None:
    from alembic.config import Config

    from alembic import command

    cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(cfg, rev)


def test_0002_creates_query_indexes(tmp_path: Path) -> None:
    """0002 补齐 risk_events 3 索引 + alert_records 列/索引。"""
    db = tmp_path / "td02.db"
    _run_alembic(db, "head")

    engine = create_engine(f"sqlite:///{db}")
    insp = inspect(engine)

    re_indexes = {i["name"] for i in insp.get_indexes("risk_events")}
    assert {
        "idx_risk_events_country",
        "idx_risk_events_manufacturer",
        "idx_risk_events_product_category",
    } <= re_indexes

    al_cols = {c["name"] for c in insp.get_columns("alert_records")}
    assert "created_at" in al_cols
    al_indexes = {i["name"] for i in insp.get_indexes("alert_records")}
    assert "idx_alert_account_created" in al_indexes

    # pipeline_runs 表不存在（非 Alembic 管理）→ 条件跳过，不报错
    assert "pipeline_runs" not in insp.get_table_names()
    engine.dispose()


def test_0002_skips_existing_manufacturer_index(tmp_path: Path) -> None:
    """manufacturer 索引已由 0001 建立，0002 幂等不重复创建。"""
    db = tmp_path / "td02_idem.db"
    _run_alembic(db, "head")
    _run_alembic(db, "head")  # 重复执行 upgrade 不报错

    engine = create_engine(f"sqlite:///{db}")
    insp = inspect(engine)
    re_indexes = {i["name"] for i in insp.get_indexes("risk_events")}
    assert "idx_risk_events_manufacturer" in re_indexes
    engine.dispose()


def test_0002_index_used_by_manufacturer_query(tmp_path: Path) -> None:
    """EXPLAIN QUERY PLAN:manufacturer 查询应使用 idx_risk_events_manufacturer。"""
    db = tmp_path / "td02_explain.db"
    _run_alembic(db, "head")

    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO risk_events "
        "(event_id, manufacturer, country, product_category, created_at) "
        "VALUES ('e1', 'Bosch', '德国', '电动工具', '2026-01-01')"
    )
    plan = conn.execute(
        "EXPLAIN QUERY PLAN SELECT event_id FROM risk_events WHERE manufacturer = 'Bosch'"
    ).fetchall()
    conn.close()

    plan_text = " ".join(str(row) for row in plan)
    assert "idx_risk_events_manufacturer" in plan_text


def test_0002_downgrade_removes_indexes_and_column(tmp_path: Path) -> None:
    """downgrade 移除 0002 新增的索引与 created_at 列。"""
    from alembic.config import Config

    from alembic import command

    db = tmp_path / "td02_down.db"
    cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db}")
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "0001")

    engine = create_engine(f"sqlite:///{db}")
    insp = inspect(engine)
    re_indexes = {i["name"] for i in insp.get_indexes("risk_events")}
    assert "idx_risk_events_country" not in re_indexes
    assert "idx_risk_events_product_category" not in re_indexes
    # manufacturer 索引属于 0001,回退到 0001 后应仍在
    assert "idx_risk_events_manufacturer" in re_indexes
    al_cols = {c["name"] for c in insp.get_columns("alert_records")}
    assert "created_at" not in al_cols
    engine.dispose()


def test_generate_pg_ddl_supports_pipeline_table(tmp_path: Path) -> None:
    """数据迁移自动 DDL 可生成 pipeline_runs 表（0002 在其上建索引的前提）。"""
    src = sqlite3.connect(":memory:")
    src.execute(
        "CREATE TABLE pipeline_runs ("
        "run_id TEXT PRIMARY KEY, pipeline_name TEXT, started_at TEXT, "
        "completed_at TEXT, status TEXT, error_message TEXT, archived_path TEXT)"
    )
    ddl = generate_pg_ddl("pipeline_runs", sqlite_table_info(src, "pipeline_runs"))
    assert 'CREATE TABLE IF NOT EXISTS "pipeline_runs"' in ddl
    assert '"completed_at" TEXT' in ddl
    src.close()
