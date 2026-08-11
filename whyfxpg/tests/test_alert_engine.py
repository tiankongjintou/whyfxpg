from datetime import datetime

from whyfxpg.adapters.alerts import InMemoryAlertPublisher
from whyfxpg.core.alert_engine import AlertEngine
from whyfxpg.core.db import get_db_connection


def _insert_high_severity_events(cursor, n: int) -> None:
    for i in range(n):
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
                f"e{i}", f"p{i}", "test_api", "https://example.com/", datetime.now().isoformat(), "title",  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
                "产品A", "品牌A", "M1", "1234", "普通机电", "德国",
                "MfrA", "电气危险", "电击", "严重" if i == 0 else "中等", 95 if i == 0 else 60,
                "可能", 95, 1.0, 1.0, 1.0, 1.0, 9000 if i == 0 else 5000, "S" if i == 0 else "M", "",
                "text", datetime.now().isoformat(), datetime.now().isoformat(), "1.0", "1.0",  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
                0.5, "auto",
            ),
        )


def test_high_severity_event_rule(initialized_db: str, temp_config_dir: str) -> None:
    engine = AlertEngine(temp_config_dir, initialized_db)
    conn = get_db_connection(initialized_db)
    cursor = conn.cursor()
    _insert_high_severity_events(cursor, 3)
    conn.commit()
    conn.close()

    result = engine.run()
    assert result["status"] == "success"
    assert result["records_created"] >= 1

    conn = get_db_connection(initialized_db)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM alert_records WHERE rule_id = 'high_severity_event'")
    assert cursor.fetchone()[0] >= 1
    conn.close()


def test_high_severity_event_rule_with_in_memory_publisher(
    initialized_db: str, temp_config_dir: str
) -> None:
    """AlertEngine 可通过 publisher_factory 注入测试 double，不实际写数据库。"""
    publisher = InMemoryAlertPublisher()
    engine = AlertEngine(
        temp_config_dir,
        initialized_db,
        publisher_factory=lambda store: publisher,
    )
    conn = get_db_connection(initialized_db)
    cursor = conn.cursor()
    _insert_high_severity_events(cursor, 1)
    conn.commit()
    conn.close()

    result = engine.run()
    assert result["status"] == "success"
    assert result["records_created"] == 1
    assert len(publisher.records) == 1
    assert publisher.records[0]["rule_id"] == "high_severity_event"


def test_country_burst_rule(initialized_db: str, temp_config_dir: str) -> None:
    engine = AlertEngine(temp_config_dir, initialized_db)
    conn = get_db_connection(initialized_db)
    cursor = conn.cursor()
    for i in range(2):
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
                f"c{i}", f"cp{i}", "test_api", "https://example.com/", datetime.now().isoformat(), "title",  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
                "产品A", "品牌A", "M1", "1234", "普通机电", "测试国",
                "MfrA", "电气危险", "电击", "中等", 60,
                "可能", 95, 1.0, 1.0, 1.0, 1.0, 5000, "M", "",
                "text", datetime.now().isoformat(), datetime.now().isoformat(), "1.0", "1.0",  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
                0.5, "auto",
            ),
        )
    conn.commit()
    conn.close()

    result = engine.run()
    assert result["status"] == "success"
    assert result["records_created"] >= 1

    conn = get_db_connection(initialized_db)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM alert_records WHERE rule_id = 'country_burst'")
    assert cursor.fetchone()[0] >= 1
    conn.close()
