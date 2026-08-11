"""
Phase 1 T1 测试：修复 RiskModel 在单次 run 内打开第二条数据库连接的问题。

覆盖：
- ConfigVersionManager 与 CausalKnowledge 支持复用外部 sqlite3.Connection。
- RiskModel.run(UnitOfWork) 在事务内不再调用 get_db_connection()。
- 多线程并发 run() 不再触发 database is locked（WAL 模式下）。
"""

import sqlite3
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from whyfxpg.core.causal_knowledge import CausalKnowledge
from whyfxpg.core.config_version import ConfigVersionManager
from whyfxpg.core.db import get_db_connection
from whyfxpg.core.risk_model import RiskModel
from whyfxpg.core.stores import UnitOfWork
from whyfxpg.migrations import MigrationRunner


def _init_test_db(db_path: Path) -> None:
    """初始化测试数据库（业务 schema + 因果图 schema，一次性应用全部迁移）。"""
    conn = get_db_connection(str(db_path))
    try:
        MigrationRunner(conn).run()
        conn.commit()
    finally:
        conn.close()


def _insert_pending_event(conn: sqlite3.Connection, severity_level: str = "轻微") -> str:
    """在指定连接上插入一条待评分事件。"""
    event_id = str(uuid.uuid4())
    now = datetime.now().isoformat()  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO risk_events (
            event_id, page_id, source_id, source_url, publish_date, title,
            product_name, brand, model, hs_code, product_category, country,
            manufacturer, hazard_type, hazard_desc, severity_level,
            standards, original_text, extracted_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_id, None, "test", "http://test", now[:10], "Test event",
            "Drill", "X", "M1", "846722", "电动工具", "中国",
            "TestMfr", "电击风险", "desc", severity_level,
            "GB", "text", now,
        ),
    )
    conn.commit()
    return event_id


def _seed_config_version(conn: sqlite3.Connection) -> None:
    """在指定连接上创建初始配置版本，使 RiskModel 只读配置版本表。"""
    manager = ConfigVersionManager.from_connection(conn)
    manager.create_version("test", "seed")
    conn.commit()


def _new_connection(db_path: Path) -> sqlite3.Connection:
    """打开一条全新的数据库连接，用于验证事务隔离。"""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def test_config_version_manager_reuses_connection(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    _init_test_db(db_path)
    conn = get_db_connection(str(db_path))

    manager = ConfigVersionManager.from_connection(conn)
    version = manager.create_version("test", "seed")
    assert version["version_id"] == "1.0"

    # 共享连接模式下，create_version 不应自行提交；
    # 使用另一条连接验证未提交数据不可见。
    other = _new_connection(db_path)
    cursor = other.cursor()
    cursor.execute("SELECT COUNT(*) FROM config_versions")
    assert cursor.fetchone()[0] == 0, "共享连接未提交前，其他连接不应看到写入"
    other.close()

    conn.commit()
    other = _new_connection(db_path)
    cursor = other.cursor()
    cursor.execute("SELECT COUNT(*) FROM config_versions WHERE version_id = ?", (version["version_id"],))
    assert cursor.fetchone()[0] == 1
    other.close()
    conn.close()


def test_causal_knowledge_reuses_connection(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    _init_test_db(db_path)
    conn = get_db_connection(str(db_path))

    causal = CausalKnowledge.from_connection(conn)
    causal.add_node("country", "Testland", risk_score=0.95, source="test")
    node = causal.get_node("country:Testland")
    assert node["risk_score"] == 0.95  # type: ignore[index]

    # 共享连接未提交，写操作对其它连接不可见
    other = _new_connection(db_path)
    cursor = other.cursor()
    cursor.execute("SELECT 1 FROM causal_nodes WHERE node_id = ?", ("country:Testland",))
    assert cursor.fetchone() is None
    other.close()

    conn.commit()
    other = _new_connection(db_path)
    cursor = other.cursor()
    cursor.execute("SELECT 1 FROM causal_nodes WHERE node_id = ?", ("country:Testland",))
    assert cursor.fetchone() is not None
    other.close()
    conn.close()


def test_risk_model_run_does_not_open_second_connection(tmp_path: Path) -> None:
    """
    核心 T1 回归测试：RiskModel 在已有 UoW 连接内运行时，
    ConfigVersionManager 与 CausalKnowledge 必须复用该连接，
    不得调用 get_db_connection() 开启新连接。
    """
    db_path = tmp_path / "test.db"
    _init_test_db(db_path)
    conn = get_db_connection(str(db_path))
    _seed_config_version(conn)
    event_id = _insert_pending_event(conn, severity_level="轻微")

    # 在 UoW 事务内，任何尝试打开新连接的行为都应被捕获
    raising_msg = "不应在 UoW 事务内打开第二条数据库连接"

    def raising_connection(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        raise AssertionError(raising_msg)

    import whyfxpg.core.causal_knowledge as ckm
    import whyfxpg.core.config_version as cvm

    original_ckm = ckm.get_db_connection  # type: ignore[attr-defined]
    original_cvm = cvm.get_db_connection
    ckm.get_db_connection = raising_connection  # type: ignore[attr-defined]
    cvm.get_db_connection = raising_connection

    try:
        with UnitOfWork.from_connection(conn) as uow:
            model = RiskModel(db_path=str(db_path))
            result = model.run(uow)
        assert result["records_processed"] == 1
        assert result["records_created"] == 1
    finally:
        ckm.get_db_connection = original_ckm  # type: ignore[attr-defined]
        cvm.get_db_connection = original_cvm

    conn.commit()
    other = _new_connection(db_path)
    cursor = other.cursor()
    cursor.execute(
        "SELECT rs_level, total_score, config_version FROM risk_events WHERE event_id = ?",
        (event_id,),
    )
    row = cursor.fetchone()
    assert row is not None
    # P0-1 后阈值 S≥85/M≥70/L≥50:轻微(15)×可能(95)=1425 → S 级
    assert row["rs_level"] == "S"
    assert row["config_version"] == "1.0"
    other.close()
    conn.close()


def test_concurrent_risk_model_runs_no_database_locked(tmp_path: Path) -> None:
    """
    并发回归测试：多线程各自使用独立 UoW 调用 RiskModel.run()，
    修复前若代码仍尝试开启额外交叉连接，极易触发 database is locked。
    """
    db_path = tmp_path / "test.db"
    _init_test_db(db_path)
    conn = get_db_connection(str(db_path))
    _seed_config_version(conn)
    for i in range(6):
        _insert_pending_event(conn, severity_level="轻微")
    conn.commit()
    conn.close()

    errors: list[str] = []

    def worker() -> None:
        try:
            model = RiskModel(db_path=str(db_path))
            with UnitOfWork(str(db_path)) as uow:
                model.run(uow)
        except Exception as e:  # noqa: BLE001 — 外部调用/配置解析兜底,刻意吞异常
            errors.append(str(e))

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"并发运行出现错误: {errors}"

    conn = get_db_connection(str(db_path))
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM risk_events WHERE rs_level IS NOT NULL")
    scored = cursor.fetchone()[0]
    conn.close()
    assert scored == 6
