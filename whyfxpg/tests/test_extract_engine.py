from whyfxpg.core.db import get_db_connection
from whyfxpg.core.extract_engine import ExtractEngine


def test_apply_regex_extracts_value():
    engine = ExtractEngine()
    text = "原产国：德国 制造商：ABC"
    result = engine.apply_regex(text, [r"原产国[:：]\s*([^，。；\s]+)"])
    assert result == "德国"


def test_apply_keyword_map_categorizes():
    engine = ExtractEngine()
    mapping = {"电气危险": ["电击", "触电"]}
    category = engine.apply_keyword_map("发生电击事故", mapping, "组合危险")
    assert category == "电气危险"

    default = engine.apply_keyword_map("未知事故", mapping, "组合危险")
    assert default == "组合危险"


def test_normalize_date_chinese():
    engine = ExtractEngine()
    assert engine.normalize_date("2025年3月5日") == "2025-03-05"


def test_normalize_date_numeric():
    engine = ExtractEngine()
    assert engine.normalize_date("2025-03-05") == "2025-03-05"


def test_extract_event_from_page(initialized_db: str, temp_config_dir: str) -> None:
    engine = ExtractEngine(temp_config_dir, initialized_db)
    page = {
        "page_id": "test_001",
        "source_id": "test_api",
        "url": "https://example.com/1",
        "raw_content": "2025-03-05 电击事故 原产国：德国".encode(),
    }
    event = engine.extract_event(page)
    assert event is not None
    assert event["source_id"] == "test_api"
    assert event["country"] == "德国"
    assert event["hazard_type"] == "电气危险"
    assert event["severity_level"] == "中等"
    assert event["ss_score"] is None


def test_run_extracts_and_inserts_event(initialized_db: str, temp_config_dir: str) -> None:
    engine = ExtractEngine(temp_config_dir, initialized_db)
    # 先写入 raw_page
    conn = get_db_connection(initialized_db)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO raw_pages (page_id, source_id, url, fetched_at, content_type, content_hash, raw_content, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "test_002",
            "test_api",
            "https://example.com/2",
            "2025-03-05T00:00:00",
            "text/html",
            "hash",
            "2025-03-05 电击事故 原产国：德国".encode(),
            "fetched",
        ),
    )
    conn.commit()
    conn.close()

    result = engine.run()
    assert result["status"] == "success"
    assert result["records_created"] == 1

    conn = get_db_connection(initialized_db)
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM raw_pages WHERE page_id = 'test_002'")
    assert cursor.fetchone()[0] == "parsed"
    conn.close()
