"""RiskPredictor 预测性预警写入测试。

测试 seam：RiskPredictor.write_predictive_alerts(warnings, publisher) 使用
AlertPublisher 而不是直接写 SQL。
"""

from datetime import datetime, timedelta

from whyfxpg.adapters.alerts import InMemoryAlertPublisher
from whyfxpg.core.db import get_db_connection
from whyfxpg.core.risk_predictor import RiskPredictor
from whyfxpg.core.stores import UnitOfWork


def _insert_event(cursor, event_id: str, country: str, category: str, publish_date: str) -> None:
    cursor.execute(
        """
        INSERT INTO risk_events (
            event_id, page_id, source_id, source_url, publish_date, title,
            product_name, brand, model, hs_code, product_category, country,
            manufacturer, hazard_type, hazard_desc, severity_level, ss_score,
            probability_level, ps_score, country_factor, product_factor,
            history_factor, evidence_factor, total_score, rs_level, standards,
            original_text, extracted_at, evaluated_at, config_version, model_version,
            extraction_confidence, review_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_id, f"p{event_id}", "test_api", "https://example.com/", publish_date, "title",
            "产品A", "品牌A", "M1", "1234", category, country,
            "MfrA", "电气危险", "电击", "中等", 60,
            "可能", 95, 1.0, 1.0, 1.0, 1.0, 5000, "M", "",
            "text", datetime.now().isoformat(), datetime.now().isoformat(), "1.0", "1.0",  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
            0.5, "auto",
        ),
    )


def test_predictor_publishes_country_and_category_warnings(initialized_db: str) -> None:
    predictor = RiskPredictor(initialized_db)
    now = datetime.now()  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
    conn = get_db_connection(initialized_db)
    cursor = conn.cursor()

    # 构造 0->1->5 的上升趋势，触发国别与类别预警
    _insert_event(cursor, "rp1", "测试国", "机电类", (now - timedelta(days=70)).isoformat())
    _insert_event(cursor, "rp2", "测试国", "机电类", (now - timedelta(days=40)).isoformat())
    for i in range(5):
        _insert_event(cursor, f"rp{i+3}", "测试国", "机电类", now.isoformat())
    conn.commit()
    conn.close()

    warnings = predictor.scan_early_warnings(horizon_months=6)
    publisher = InMemoryAlertPublisher()
    result = predictor.write_predictive_alerts(warnings, publisher=publisher)

    assert result["status"] == "success"
    assert result["records_created"] == 2
    assert len(publisher.records) == result["records_created"]
    rule_ids = {r["rule_id"] for r in publisher.records}
    assert "predictive_country" in rule_ids
    assert "predictive_category" in rule_ids


def test_no_warnings_returns_zero(initialized_db: str) -> None:
    predictor = RiskPredictor(initialized_db)
    publisher = InMemoryAlertPublisher()
    result = predictor.write_predictive_alerts(publisher=publisher)
    assert result["records_created"] == 0
    assert len(publisher.records) == 0


def test_predictor_publishes_to_db_by_default(initialized_db: str) -> None:
    predictor = RiskPredictor(initialized_db)
    now = datetime.now()  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
    conn = get_db_connection(initialized_db)
    cursor = conn.cursor()
    _insert_event(cursor, "rp4", "测试国2", "机电类2", (now - timedelta(days=70)).isoformat())
    _insert_event(cursor, "rp5", "测试国2", "机电类2", (now - timedelta(days=40)).isoformat())
    for i in range(5):
        _insert_event(cursor, f"rp{i+10}", "测试国2", "机电类2", now.isoformat())
    conn.commit()
    conn.close()

    result = predictor.write_predictive_alerts()
    assert result["records_created"] == 2

    with UnitOfWork(initialized_db) as uow:
        cursor = uow.connection.cursor()
        cursor.execute("SELECT COUNT(*) FROM alert_records WHERE rule_id LIKE 'predictive_%'")
        assert cursor.fetchone()[0] >= 1
