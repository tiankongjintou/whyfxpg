"""
Source port + Fetcher orchestrator 测试。

不直接 mock requests，而是通过 InMemorySourceAdapter 注入测试数据，
验证 Fetcher 的 orchestration 与 Store 写入行为。
"""

import hashlib
from datetime import datetime

import pytest

from whyfxpg.adapters.sources.in_memory_source_adapter import InMemorySourceAdapter
from whyfxpg.core.db import get_db_connection
from whyfxpg.core.fetcher import Fetcher
from whyfxpg.ports.source_port import FetchedPage, SourcePort


def make_page(source_id: str, content: bytes, url: str = "https://example.com/recalls") -> FetchedPage:
    return FetchedPage(
        source_id=source_id,
        url=url,
        content=content,
        content_type="text/html",
        content_hash=hashlib.sha256(content).hexdigest(),
        fetched_at=datetime.now().isoformat(),  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
    )


def test_source_port_is_abstract():
    with pytest.raises(TypeError):
        SourcePort()


def test_init_monitor_sources_inserts_sources(initialized_db: str, temp_config_dir: str) -> None:
    fetcher = Fetcher(temp_config_dir, initialized_db, source_port=InMemorySourceAdapter())
    fetcher.init_monitor_sources()

    conn = get_db_connection(initialized_db)
    cursor = conn.cursor()
    cursor.execute("SELECT source_id, name, status FROM monitor_sources WHERE source_id = 'test_api'")
    row = cursor.fetchone()
    conn.close()

    assert row is not None
    assert row["source_id"] == "test_api"
    assert row["status"] == "ok"


def test_fetch_source_with_in_memory_adapter_inserts_page(
    initialized_db: str, temp_config_dir: str
) -> None:
    content = b"page content"
    adapter = InMemorySourceAdapter({"test_api": make_page("test_api", content)})
    fetcher = Fetcher(temp_config_dir, initialized_db, source_port=adapter)
    fetcher.init_monitor_sources()

    result = fetcher.fetch_source(
        "test_api",
        {"url": "https://example.com/recalls", "headers": {}, "enabled": True, "delay": 0},
    )

    assert result["success"] is True
    assert result["new"] is True
    assert result["content_hash"] == hashlib.sha256(content).hexdigest()

    conn = get_db_connection(initialized_db)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM raw_pages WHERE source_id = 'test_api'")
    assert cursor.fetchone()[0] == 1
    cursor.execute("SELECT COUNT(*) FROM crawl_logs WHERE source_id = 'test_api'")
    assert cursor.fetchone()[0] == 1
    conn.close()


def test_fetch_source_duplicate_content_not_inserted(
    initialized_db: str, temp_config_dir: str
) -> None:
    content = b"same page"
    adapter = InMemorySourceAdapter({"test_api": make_page("test_api", content)})
    fetcher = Fetcher(temp_config_dir, initialized_db, source_port=adapter)
    fetcher.init_monitor_sources()

    first = fetcher.fetch_source("test_api", {"url": "https://example.com/recalls", "headers": {}, "enabled": True, "delay": 0})
    assert first["new"] is True

    second = fetcher.fetch_source("test_api", {"url": "https://example.com/recalls", "headers": {}, "enabled": True, "delay": 0})
    assert second["new"] is False
    assert second["page_id"] == first["page_id"]

    conn = get_db_connection(initialized_db)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM raw_pages WHERE source_id = 'test_api'")
    assert cursor.fetchone()[0] == 1
    cursor.execute("SELECT COUNT(*) FROM crawl_logs WHERE source_id = 'test_api'")
    assert cursor.fetchone()[0] == 2
    conn.close()


def test_run_with_in_memory_adapter_and_logs(
    initialized_db: str, temp_config_dir: str
) -> None:
    content = b"run page content"
    adapter = InMemorySourceAdapter({"test_api": make_page("test_api", content)})
    fetcher = Fetcher(temp_config_dir, initialized_db, source_port=adapter)

    result = fetcher.run()

    assert result["module"] == "fetcher"
    assert result["status"] == "success"
    assert result["records_processed"] == 1
    assert result["records_created"] == 1
    assert result["errors"] == []

    conn = get_db_connection(initialized_db)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM crawl_logs WHERE source_id = 'test_api'")
    assert cursor.fetchone()[0] == 1
    cursor.execute("SELECT status, error_msg FROM monitor_sources WHERE source_id = 'test_api'")
    row = cursor.fetchone()
    assert row["status"] == "ok"
    assert row["error_msg"] is None
    conn.close()


def test_run_with_adapter_error_records_failure(
    initialized_db: str, temp_config_dir: str
) -> None:
    error_page = FetchedPage(
        source_id="test_api",
        url="https://example.com/recalls",
        content=b"",
        content_type="unknown",
        content_hash="",
        status="error",
        error_msg="network unreachable",
    )
    adapter = InMemorySourceAdapter({"test_api": error_page})
    fetcher = Fetcher(temp_config_dir, initialized_db, source_port=adapter)

    result = fetcher.run()

    assert result["status"] == "partial"
    assert result["records_processed"] == 1
    assert result["records_created"] == 0
    assert "network unreachable" in result["errors"][0]

    conn = get_db_connection(initialized_db)
    cursor = conn.cursor()
    cursor.execute("SELECT status, error_msg FROM monitor_sources WHERE source_id = 'test_api'")
    row = cursor.fetchone()
    assert row["status"] == "error"
    assert "network unreachable" in row["error_msg"]
    cursor.execute("SELECT status, error_msg FROM crawl_logs WHERE source_id = 'test_api'")
    log = cursor.fetchone()
    assert log["status"] == "error"
    assert "network unreachable" in log["error_msg"]
    conn.close()


def test_in_memory_adapter_callback_form():
    def callback(source_id: str, cfg: dict) -> FetchedPage:
        return FetchedPage(
            source_id=source_id,
            url=cfg["url"],
            content=b"callback",
            content_type="text/html",
            content_hash=hashlib.sha256(b"callback").hexdigest(),
        )

    adapter = InMemorySourceAdapter(callback=callback)
    page = adapter.fetch("x", {"url": "https://x.com"})
    assert page.content == b"callback"
    assert page.url == "https://x.com"


def test_in_memory_adapter_missing_source_raises():
    adapter = InMemorySourceAdapter()
    with pytest.raises(NotImplementedError):
        adapter.fetch("missing", {})
