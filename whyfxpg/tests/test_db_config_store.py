"""P1b-04: 配置存储 DB 后端测试。

覆盖：
- DbConfigStoreAdapter CRUD（list/read/write/delete/versions，SQLite 端，
  SQL 跨 SQLite/PostgreSQL 通用）
- import_yaml_configs 从配置目录导入 + 幂等
- Alembic 0004 迁移在 SQLite 上建出 config_objects 表（PG 实机验证留待环境）
"""

# ruff: noqa: DTZ001 — 测试数据用固定 naive 时间戳(与项目本地时间约定一致)
import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

from whyfxpg.adapters.config.db_config_store import (
    DbConfigStoreAdapter,
    import_yaml_configs,
)
from whyfxpg.ports.config_store import ConfigRecord

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _run_alembic_upgrade(db_path: Path) -> None:
    from alembic.config import Config

    from alembic import command

    cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(cfg, "head")


def _make_record(object_id: str = "obj1", payload: dict | None = None) -> ConfigRecord:
    return ConfigRecord(
        object_type="rule",
        object_id=object_id,
        status="published",
        payload=payload or {"rule_id": object_id, "name": "测试规则"},
        version_id="v1",
        created_at=datetime(2026, 8, 11, 10, 0, 0),
        created_by="tester",
        published_at=datetime(2026, 8, 11, 10, 0, 0),
        published_by="tester",
    )


@pytest.fixture
def db_store(tmp_path: Path) -> DbConfigStoreAdapter:
    db = tmp_path / "cfg.db"
    _run_alembic_upgrade(db)
    return DbConfigStoreAdapter(db_path=str(db))


# ──────────────────────────────────────────────────────────────
# Alembic 0004 迁移
# ──────────────────────────────────────────────────────────────


def test_alembic_0004_creates_config_objects(tmp_path: Path) -> None:
    db = tmp_path / "cfg0004.db"
    _run_alembic_upgrade(db)
    conn = sqlite3.connect(db)
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    conn.close()
    assert "config_objects" in tables
    assert "alembic_version" in tables


# ──────────────────────────────────────────────────────────────
# CRUD
# ──────────────────────────────────────────────────────────────


def test_write_and_read_roundtrip(db_store: DbConfigStoreAdapter) -> None:
    db_store.write(_make_record())
    record = db_store.read("rule", "obj1")
    assert record is not None
    assert record.object_id == "obj1"
    assert record.payload["name"] == "测试规则"
    assert record.version_id == "v1"


def test_read_returns_latest_version(db_store: DbConfigStoreAdapter) -> None:
    db_store.write(_make_record())
    r2 = _make_record()
    r2.version_id = "v2"
    r2.created_at = datetime(2026, 8, 11, 10, 0, 1)
    r2.payload = {"rule_id": "obj1", "name": "更新后"}
    db_store.write(r2)
    latest = db_store.read("rule", "obj1")
    assert latest is not None
    assert latest.version_id == "v2"
    assert latest.payload["name"] == "更新后"


def test_list_groups_by_object_id(db_store: DbConfigStoreAdapter) -> None:
    db_store.write(_make_record("a"))
    db_store.write(_make_record("b"))
    r2 = _make_record("a")
    r2.version_id = "v2"
    r2.created_at = datetime(2026, 8, 11, 10, 0, 1)
    db_store.write(r2)  # a 的第二版本
    records = db_store.list("rule")
    assert len(records) == 2
    assert {r.object_id for r in records} == {"a", "b"}


def test_delete_marks_deprecated(db_store: DbConfigStoreAdapter) -> None:
    db_store.write(_make_record())
    db_store.delete("rule", "obj1")
    record = db_store.read("rule", "obj1")
    assert record is not None
    assert record.status == "deprecated"
    # 历史保留
    assert len(db_store.versions("rule", "obj1")) == 1


def test_versions_ordered_newest_first(db_store: DbConfigStoreAdapter) -> None:
    db_store.write(_make_record())
    r2 = _make_record()
    r2.version_id = "v2"
    r2.created_at = datetime(2026, 8, 11, 10, 0, 1)
    db_store.write(r2)
    versions = db_store.versions("rule", "obj1")
    assert [v.version_id for v in versions] == ["v2", "v1"]


# ──────────────────────────────────────────────────────────────
# YAML → DB 导入
# ──────────────────────────────────────────────────────────────


def test_import_yaml_configs_and_idempotent(db_store: DbConfigStoreAdapter, tmp_path: Path) -> None:
    # 最小配置目录：含 1 个 rule
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir()
    (cfg_dir / "alert_rules.yaml").write_text(
        "rules:\n"
        "  - rule_id: r1\n"
        "    name: 规则一\n"
        "    severity: S\n",
        encoding="utf-8",
    )
    n1 = import_yaml_configs(db_store, cfg_dir, object_types=["rule"])
    assert n1 >= 1
    record = db_store.read("rule", "r1")
    assert record is not None
    assert record.payload["name"] == "规则一"
    # 幂等：内容未变不重复导入
    n2 = import_yaml_configs(db_store, cfg_dir, object_types=["rule"])
    assert n2 == 0
    assert len(db_store.versions("rule", "r1")) == 1
