from datetime import datetime, timedelta

import pytest

from whyfxpg.core.db import get_db_connection
from whyfxpg.core.stores import AlertStore, RiskEventStore, SummaryStore, UnitOfWork
from whyfxpg.migrations import MigrationRunner


def _init_db(db_path: str) -> None:
    conn = get_db_connection(db_path)
    try:
        MigrationRunner(conn).run()
        conn.commit()
    finally:
        conn.close()


EVENT_COLUMNS = [
    "event_id", "page_id", "source_id", "source_url", "publish_date", "title",
    "product_name", "brand", "model", "hs_code", "product_category", "country",
    "manufacturer", "hazard_type", "hazard_desc", "severity_level", "ss_score",
    "probability_level", "ps_score", "country_factor", "product_factor",
    "history_factor", "evidence_factor", "causal_factor", "total_score", "rs_level",
    "standards", "original_text", "extracted_at", "evaluated_at", "config_version",
    "model_version", "extraction_confidence", "review_status",
]


def _insert_risk_event(conn, event_id: str, **overrides) -> None:
    defaults = {
        "event_id": event_id,
        "page_id": f"p_{event_id}",
        "source_id": "test_api",
        "source_url": "https://example.com/",
        "publish_date": datetime.now().strftime("%Y-%m-%d"),  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
        "title": "title",
        "product_name": "产品A",
        "brand": "品牌A",
        "model": "M1",
        "hs_code": "1234",
        "product_category": "普通机电",
        "country": "测试国",
        "manufacturer": "MfrA",
        "hazard_type": "电气危险",
        "hazard_desc": "电击",
        "severity_level": "中等",
        "ss_score": None,
        "probability_level": "可能",
        "ps_score": None,
        "country_factor": 1.0,
        "product_factor": 1.0,
        "history_factor": 1.0,
        "evidence_factor": 1.0,
        "causal_factor": 1.0,
        "total_score": None,
        "rs_level": None,
        "standards": "",
        "original_text": "text",
        "extracted_at": datetime.now().isoformat(),  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
        "evaluated_at": None,
        "config_version": "1.0",
        "model_version": "1.0",
        "extraction_confidence": 0.5,
        "review_status": "auto",
    }
    defaults.update(overrides)
    placeholders = ", ".join(["?"] * len(EVENT_COLUMNS))
    sql = f"INSERT INTO risk_events ({', '.join(EVENT_COLUMNS)}) VALUES ({placeholders})"
    conn.execute(sql, [defaults[c] for c in EVENT_COLUMNS])


def test_unit_of_work_commits_on_success(tmp_path):
    db_path = str(tmp_path / "uow.db")
    _init_db(db_path)

    with UnitOfWork(db_path) as uow:
        cursor = uow.connection.cursor()
        cursor.execute(
            "INSERT INTO alert_records (alert_id, rule_id, rule_name, triggered_at, object_type, object_value, severity, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("a1", "r1", "rule1", datetime.now().isoformat(), "event", "e1", "high", "pending"),  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
        )

    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM alert_records WHERE alert_id = 'a1'")
    assert cursor.fetchone()[0] == 1
    conn.close()


def test_unit_of_work_rolls_back_on_exception(tmp_path):
    db_path = str(tmp_path / "uow.db")
    _init_db(db_path)

    with pytest.raises(RuntimeError), UnitOfWork(db_path) as uow:
            cursor = uow.connection.cursor()
            cursor.execute(
                "INSERT INTO alert_records (alert_id, rule_id, rule_name, triggered_at, object_type, object_value, severity, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                ("a2", "r1", "rule1", datetime.now().isoformat(), "event", "e2", "high", "pending"),  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
            )
            raise RuntimeError("boom")

    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM alert_records WHERE alert_id = 'a2'")
    assert cursor.fetchone()[0] == 0
    conn.close()


def test_unit_of_work_connection_outside_context_raises(tmp_path):
    db_path = str(tmp_path / "uow.db")
    uow = UnitOfWork(db_path)
    with pytest.raises(RuntimeError):
        _ = uow.connection


def test_alert_store_find_and_insert(tmp_path, temp_config_dir):
    db_path = str(tmp_path / "store.db")
    _init_db(db_path)

    with UnitOfWork(db_path) as uow:
        store = AlertStore(uow)
        assert store.find_existing("r1", "event", "e1") == 0
        store.insert_alert(
            rule_id="r1",
            rule_name="rule1",
            object_type="event",
            object_value="e1",
            severity="high",
            triggered_value="severity=严重",
            description="测试预警",
        )
        assert store.find_existing("r1", "event", "e1") == 1

    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT rule_id, status FROM alert_records WHERE object_value = 'e1'")
    row = cursor.fetchone()
    assert row["rule_id"] == "r1"
    assert row["status"] == "pending"
    conn.close()


def test_alert_store_count_events_by_dimension(tmp_path, temp_config_dir):
    db_path = str(tmp_path / "store.db")
    _init_db(db_path)

    since = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
    conn = get_db_connection(db_path)
    _insert_risk_event(conn, "e0", ss_score=60, ps_score=95, total_score=5000, rs_level="M")
    _insert_risk_event(conn, "e1", ss_score=60, ps_score=95, total_score=5000, rs_level="M")
    _insert_risk_event(conn, "e2", ss_score=60, ps_score=95, total_score=5000, rs_level="M")
    conn.commit()
    conn.close()

    with UnitOfWork(db_path) as uow:
        store = AlertStore(uow)
        rows = store.count_events_by_dimension("country", since, 2)
        assert len(rows) == 1
        assert rows[0]["country"] == "测试国"
        assert rows[0]["cnt"] == 3


def test_alert_store_fetch_high_severity_events(tmp_path):
    db_path = str(tmp_path / "store.db")
    _init_db(db_path)

    conn = get_db_connection(db_path)
    _insert_risk_event(
        conn,
        "e1",
        country="德国",
        severity_level="严重",
        ss_score=95,
        ps_score=95,
        total_score=9000,
        rs_level="S",
    )
    conn.commit()
    conn.close()

    with UnitOfWork(db_path) as uow:
        store = AlertStore(uow)
        rows = store.fetch_high_severity_events(["严重", "灾难性"], "r1")
        assert len(rows) == 1
        assert rows[0]["event_id"] == "e1"

    # 已存在的 alert_records 应该过滤掉该事件
    with UnitOfWork(db_path) as uow:
        store = AlertStore(uow)
        store.insert_alert(
            rule_id="r1",
            rule_name="rule1",
            object_type="event",
            object_value="e1",
            severity="high",
            triggered_value="severity=严重",
            description="已预警",
        )
        rows = store.fetch_high_severity_events(["严重"], "r1")
        assert len(rows) == 0


def test_risk_event_store_fetch_pending_returns_only_unscored(tmp_path):
    db_path = str(tmp_path / "store.db")
    _init_db(db_path)

    conn = get_db_connection(db_path)
    _insert_risk_event(conn, "e1", ss_score=None, ps_score=None)
    _insert_risk_event(conn, "e2", ss_score=60, ps_score=95, total_score=5000, rs_level="M")
    conn.commit()
    conn.close()

    with UnitOfWork(db_path) as uow:
        store = RiskEventStore(uow)
        pending = store.fetch_pending()

    assert len(pending) == 1
    assert pending[0]["event_id"] == "e1"


def test_risk_event_store_count_history_matches_multiple_dimensions(tmp_path):
    db_path = str(tmp_path / "store.db")
    _init_db(db_path)

    since = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
    conn = get_db_connection(db_path)
    _insert_risk_event(conn, "e1", country="德国", manufacturer="MfrX", product_category="A", hazard_type="H1", ss_score=80)
    _insert_risk_event(conn, "e2", country="法国", manufacturer="MfrA", product_category="B", hazard_type="H2", ss_score=80)
    _insert_risk_event(conn, "e3", country="日本", manufacturer="MfrY", product_category="普通机电", hazard_type="电气危险", ss_score=80)
    # older / unscored / no dimension match
    _insert_risk_event(conn, "e4", country="德国", manufacturer="MfrX", product_category="A", hazard_type="H1", ss_score=80, publish_date="2000-01-01")
    _insert_risk_event(conn, "e5", country="德国", manufacturer="MfrX", product_category="A", hazard_type="H1", ss_score=None)
    conn.commit()
    conn.close()

    with UnitOfWork(db_path) as uow:
        store = RiskEventStore(uow)
        count = store.count_history(since, "德国", "MfrA", "普通机电", "电气危险")

    assert count == 3


def test_risk_event_store_count_history_by_product(tmp_path):
    db_path = str(tmp_path / "store.db")
    _init_db(db_path)

    since = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
    conn = get_db_connection(db_path)
    _insert_risk_event(conn, "e1", product_category="普通机电", hazard_type="电气危险", ss_score=80)
    _insert_risk_event(conn, "e2", product_category="普通机电", hazard_type="电气危险", ss_score=80)
    _insert_risk_event(conn, "e3", product_category="普通机电", hazard_type="机械危险", ss_score=80)
    _insert_risk_event(conn, "e4", product_category="普通机电", hazard_type="电气危险", ss_score=None)
    conn.commit()
    conn.close()

    with UnitOfWork(db_path) as uow:
        store = RiskEventStore(uow)
        count = store.count_history_by_product(since, "普通机电", "电气危险")

    assert count == 2


def test_risk_event_store_update_scores(tmp_path):
    db_path = str(tmp_path / "store.db")
    _init_db(db_path)

    conn = get_db_connection(db_path)
    _insert_risk_event(conn, "e1")
    conn.commit()
    conn.close()

    result = {
        "ss_score": 85,
        "ps_score": 95,
        "probability_level": "可能",
        "country_factor": 1.2,
        "product_factor": 1.1,
        "history_factor": 1.0,
        "evidence_factor": 1.0,
        "causal_factor": 1.05,
        "total_score": 9000,
        "rs_level": "S",
    }
    with UnitOfWork(db_path) as uow:
        store = RiskEventStore(uow)
        store.update_scores("e1", result, "1.0", "v2")

    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM risk_events WHERE event_id = 'e1'")
    row = cursor.fetchone()
    conn.close()

    assert row["ss_score"] == 85
    assert row["ps_score"] == 95
    assert row["total_score"] == 9000
    assert row["rs_level"] == "S"
    assert row["causal_factor"] == 1.05
    assert row["config_version"] == "1.0"
    assert row["model_version"] == "v2"
    assert row["evaluated_at"] is not None


def test_risk_event_store_append_risk_reasoning(tmp_path):
    db_path = str(tmp_path / "store.db")
    _init_db(db_path)

    conn = get_db_connection(db_path)
    _insert_risk_event(conn, "e1", hazard_desc="初始")
    conn.commit()
    conn.close()

    with UnitOfWork(db_path) as uow:
        store = RiskEventStore(uow)
        store.append_risk_reasoning("e1", "不建议进口")

    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT hazard_desc FROM risk_events WHERE event_id = 'e1'")
    row = cursor.fetchone()
    conn.close()

    assert "初始" in row["hazard_desc"]
    assert "【AI风险分析】不建议进口" in row["hazard_desc"]


def test_summary_store_rebuild_summaries(tmp_path):
    db_path = str(tmp_path / "store.db")
    _init_db(db_path)

    conn = get_db_connection(db_path)
    base = datetime.now().strftime("%Y-%m-%d")  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
    _insert_risk_event(conn, "e1", product_name="电钻", brand="Bosch", country="德国", manufacturer="MfrD", hazard_type="机械危险", ss_score=95, ps_score=95, total_score=9000, rs_level="S", publish_date=base, model_version="v2")
    _insert_risk_event(conn, "e2", product_name="电钻", brand="Bosch", country="德国", manufacturer="MfrD", hazard_type="电气危险", ss_score=60, ps_score=95, total_score=5000, rs_level="M", publish_date=base, model_version="v2")
    _insert_risk_event(conn, "e3", product_name="电锯", brand="Makita", country="日本", manufacturer="MfrJ", hazard_type="机械危险", ss_score=60, ps_score=60, total_score=3000, rs_level="L", publish_date=base, model_version="v2")
    conn.commit()
    conn.close()

    with UnitOfWork(db_path) as uow:
        store = SummaryStore(uow)
        store.rebuild_summaries("1.0", "v2")

    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM product_risk_summary WHERE product_name = '电钻'")
    product = cursor.fetchone()
    assert product["event_count"] == 2
    assert product["latest_total_score"] == 9000
    assert product["latest_rs_level"] == "S"
    assert product["config_version"] == "1.0"
    assert product["model_version"] == "v2"

    cursor.execute("SELECT * FROM country_risk_summary WHERE country = '德国'")
    country = cursor.fetchone()
    assert country["event_count"] == 2
    assert country["s_count"] == 1
    assert country["m_count"] == 1

    cursor.execute("SELECT * FROM enterprise_risk_summary WHERE manufacturer = 'MfrD'")
    enterprise = cursor.fetchone()
    assert enterprise["event_count"] == 2
    assert enterprise["country"] == "德国"

    conn.close()
