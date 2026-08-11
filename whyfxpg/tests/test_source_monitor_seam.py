"""Tests for the SourceMonitor seam (T17).

Covers timing/coverage fields in crawl_logs, SourceHealthPort adapters,
SourceMonitorService, and lineage queries. All tests use local fixtures or
in-memory databases so they do not depend on the production whyfxpg.db.
"""

import hashlib
from datetime import datetime

from whyfxpg.adapters.alerts import InMemoryAlertPublisher
from whyfxpg.adapters.monitoring import (
    DbSourceHealthAdapter,
    InMemorySourceHealthAdapter,
)
from whyfxpg.adapters.sources.in_memory_source_adapter import InMemorySourceAdapter
from whyfxpg.core.db import get_db_connection
from whyfxpg.core.fetcher import Fetcher
from whyfxpg.ports.source_port import FetchedPage
from whyfxpg.services.source_monitor import SourceMonitorService


def make_page(source_id: str, content: bytes, latency_ms: int = 123) -> FetchedPage:
    return FetchedPage(
        source_id=source_id,
        url="https://example.com/recalls",
        content=content,
        content_type="text/html",
        content_hash=hashlib.sha256(content).hexdigest(),
        fetched_at=datetime.now().isoformat(),  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
        request_started_at=datetime.now().isoformat(),  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
        latency_ms=latency_ms,
        content_length=len(content),
    )


def test_fetcher_records_latency_and_content_length(
    initialized_db: str, temp_config_dir: str
) -> None:
    content = b"page content with timing"
    adapter = InMemorySourceAdapter({"test_api": make_page("test_api", content, 250)})
    fetcher = Fetcher(temp_config_dir, initialized_db, source_port=adapter)

    fetcher.run()

    conn = get_db_connection(initialized_db)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT latency_ms, content_length, request_started_at FROM crawl_logs WHERE source_id = 'test_api'"
    )
    row = cursor.fetchone()
    assert row is not None
    assert row["latency_ms"] == 250
    assert row["content_length"] == len(content)
    assert row["request_started_at"] is not None

    cursor.execute(
        "SELECT last_content_length FROM monitor_sources WHERE source_id = 'test_api'"
    )
    source_row = cursor.fetchone()
    assert source_row["last_content_length"] == len(content)
    conn.close()


def test_db_source_health_adapter_coverage_and_latency(initialized_db: str) -> None:
    conn = get_db_connection(initialized_db)
    cursor = conn.cursor()
    now = datetime.now().isoformat()  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计

    cursor.execute(
        "INSERT OR REPLACE INTO monitor_sources (source_id, name, check_interval, last_check_at) VALUES (?, ?, ?, ?)",
        ("test_api", "Test API", "1h", now),
    )
    cursor.execute(
        """
        INSERT INTO crawl_logs (source_id, run_at, status, pages_fetched, pages_new, latency_ms, content_length)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        ("test_api", now, "ok", 1, 1, 500, 1000),
    )
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
            "e1", "p1", "test_api", "https://example.com/", "2026-01-01", "title",
            "产品A", "品牌A", "M1", "1234", "普通机电", "德国",
            "MfrA", "电气危险", "电击", "严重", 95,
            "可能", 95, 1.0, 1.0, 1.0, 1.0, 9000, "S", "",
            "text", now, now, "1.0", "1.0",
            0.5, "auto",
        ),
    )
    conn.commit()
    conn.close()

    adapter = DbSourceHealthAdapter(initialized_db)
    assert adapter.latency("test_api") == 500
    assert adapter.coverage("test_api") == 1.0
    assert adapter.freshness("test_api") == 1.0
    assert adapter.error_rate("test_api", "24h") == 0.0

    health = adapter.health("test_api")
    assert health.status == "ok"
    assert health.health_score > 0.5
    assert health.latency_ms == 500

    metrics = adapter.metrics("test_api", "24h")
    assert metrics["avg_latency_ms"] == 500

    adapter.write_snapshot(health)
    conn = get_db_connection(initialized_db)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM source_health_snapshots WHERE source_id = 'test_api'")
    assert cursor.fetchone()[0] == 1
    conn.close()


def test_db_source_health_adapter_lineage(initialized_db: str) -> None:
    conn = get_db_connection(initialized_db)
    cursor = conn.cursor()
    now = datetime.now().isoformat()  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
    cursor.execute(
        "INSERT OR REPLACE INTO monitor_sources (source_id, name, check_interval) VALUES (?, ?, ?)",
        ("test_api", "Test API", "1h"),
    )
    cursor.execute(
        "INSERT INTO raw_pages (page_id, source_id, url, fetched_at) VALUES (?, ?, ?, ?)",
        ("p1", "test_api", "https://example.com/1", now),
    )
    cursor.execute(
        "INSERT INTO crawl_logs (source_id, run_at, status) VALUES (?, ?, ?)",
        ("test_api", now, "ok"),
    )
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
            "e_lineage", "p1", "test_api", "https://example.com/1", "2026-01-01", "title",
            "产品A", "品牌A", "M1", "1234", "普通机电", "德国",
            "MfrA", "电气危险", "电击", "严重", 95,
            "可能", 95, 1.0, 1.0, 1.0, 1.0, 9000, "S", "",
            "text", now, now, "1.0", "1.0",
            0.5, "auto",
        ),
    )
    conn.commit()
    conn.close()

    adapter = DbSourceHealthAdapter(initialized_db)
    lineage = adapter.lineage("e_lineage")
    assert lineage.event_id == "e_lineage"
    assert lineage.page_id == "p1"
    assert lineage.source_id == "test_api"
    assert lineage.url == "https://example.com/1"


def test_in_memory_source_health_adapter() -> None:
    adapter = InMemorySourceHealthAdapter(
        sources={
            "s1": {
                "status": "degraded",
                "health_score": 0.6,
                "freshness": 0.5,
                "latency_ms": 2000,
                "coverage": 0.8,
                "error_rate": 0.1,
            }
        }
    )
    health = adapter.health("s1")
    assert health.status == "degraded"
    assert health.latency_ms == 2000
    adapter.write_snapshot(health)
    assert len(adapter.snapshots) == 1


def test_source_monitor_service_emits_alert() -> None:
    publisher = InMemoryAlertPublisher()
    adapter = InMemorySourceHealthAdapter(
        sources={
            "s1": {
                "status": "error",
                "health_score": 0.2,
                "freshness": 0.0,
                "latency_ms": 10000,
                "coverage": 0.3,
                "error_rate": 0.6,
            }
        }
    )
    service = SourceMonitorService(adapter, publisher=publisher)
    result = service.run()
    assert result["records_created"] == 1
    assert len(publisher.records) == 1
    assert publisher.records[0]["object_type"] == "source"
    assert publisher.records[0]["object_value"] == "s1"


def test_source_monitor_service_healthy_source_no_alert() -> None:
    publisher = InMemoryAlertPublisher()
    adapter = InMemorySourceHealthAdapter(
        sources={
            "s1": {
                "status": "ok",
                "health_score": 1.0,
                "freshness": 1.0,
                "latency_ms": 100,
                "coverage": 1.0,
                "error_rate": 0.0,
            }
        }
    )
    service = SourceMonitorService(adapter, publisher=publisher)
    result = service.run()
    assert result["records_created"] == 0
    assert publisher.records == []
