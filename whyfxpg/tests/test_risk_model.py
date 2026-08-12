from datetime import datetime

import pytest

from whyfxpg.core.db import get_db_connection
from whyfxpg.core.risk_model import RiskModel


def test_severity_to_score(initialized_db: str, temp_config_dir: str) -> None:
    model = RiskModel(temp_config_dir, initialized_db)
    assert model.severity_to_score("中等") == 60
    assert model.severity_to_score("不存在") == 60  # fallback default


def test_calculate_total_score(initialized_db: str, temp_config_dir: str) -> None:
    model = RiskModel(temp_config_dir, initialized_db)
    score = model.calculate_total_score(60, 95, 1.0, 1.0, 1.0, 1.0)
    assert score == pytest.approx(60 * 95 * 1.0 * 1.0 * 1.0 * 1.0)


def test_map_to_risk_level(initialized_db: str, temp_config_dir: str) -> None:
    model = RiskModel(temp_config_dir, initialized_db)
    # P1b-03：输入为 0-100 归一化分（阈值 S≥85/M≥70/L≥50）
    assert model.map_to_risk_level(90) == "S"
    assert model.map_to_risk_level(75) == "M"
    assert model.map_to_risk_level(60) == "L"
    assert model.map_to_risk_level(40) == "A"


def test_evaluate_event(initialized_db: str, temp_config_dir: str) -> None:
    model = RiskModel(temp_config_dir, initialized_db)
    event = {
        "event_id": "e1",
        "severity_level": "中等",
        "country": "德国",
        "product_category": "普通机电",
        "hazard_type": "电气危险",
        "source_id": "test_api",
    }
    conn = get_db_connection(initialized_db)
    result = model.evaluate_event(event, conn)
    conn.close()

    assert result["ss_score"] == 60
    assert result["rs_level"] in {"A", "L", "M", "S"}
    assert result["total_score"] > 0


def test_run_scores_event_and_updates_summaries(initialized_db: str, temp_config_dir: str) -> None:
    model = RiskModel(temp_config_dir, initialized_db)
    conn = get_db_connection(initialized_db)
    cursor = conn.cursor()
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
            "e1", "p1", "test_api", "https://example.com/1", "2025-03-05", "title",
            "产品A", "品牌A", "M1", "1234", "普通机电", "德国",
            "MfrA", "电气危险", "电击", "中等", None,
            "", None, None, None,
            None, None, None, None, "",
            "text", datetime.now().isoformat(), None, "", "",  # noqa: DTZ005 — 测试数据,无需时区语义
            0.5, "auto",
        ),
    )
    conn.commit()
    conn.close()

    result = model.run()
    assert result["status"] == "success"
    assert result["records_created"] == 1

    conn = get_db_connection(initialized_db)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM product_risk_summary")
    assert cursor.fetchone()[0] == 1
    cursor.execute("SELECT COUNT(*) FROM country_risk_summary")
    assert cursor.fetchone()[0] == 1
    cursor.execute("SELECT COUNT(*) FROM enterprise_risk_summary")
    assert cursor.fetchone()[0] == 1
    conn.close()
