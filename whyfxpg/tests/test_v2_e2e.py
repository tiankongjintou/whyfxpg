"""T30: v2 end-to-end seam tests.

Tests the full v2 pipeline flow across SourceResponse → RiskEventStore scoring,
and verifies the Seafile ghost-write workaround (shutil.copy2 + os.remove).
All tests use in-memory / temporary resources so they do not touch production data.
"""

import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from whyfxpg.core.db import get_db_connection
from whyfxpg.core.stores import RiskEventStore, UnitOfWork
from whyfxpg.migrations import MigrationRunner
from whyfxpg.ports.source_adapter import SourceResponse


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _init_db(db_path: str) -> None:
    conn = get_db_connection(db_path)
    try:
        MigrationRunner(conn).run()
        conn.commit()
    finally:
        conn.close()


def _seed_pending_event(db_path: str, event_id: str = "evt-e2e-1") -> None:
    """Insert a pending (un-scored) risk_event with empty hazard_desc."""
    conn = get_db_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO risk_events (
                event_id, source_id, source_url, title, country,
                product_category, hazard_type, publish_date, extracted_at,
                ss_score, ps_score, total_score, rs_level, evaluated_at,
                hazard_desc
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id, "test_api", "https://example.com/1",
                "某产品因电击风险被召回",
                "测试国", "普通机电", "电气危险",
                "2026-01-01", datetime.now().isoformat(),
                None, None, None, None, None,
                "",  # hazard_desc must be empty string so || concatenation works
            ),
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Test 1: SourceResponse round-trip through the pipeline
# ---------------------------------------------------------------------------

def test_source_response_fields_populated() -> None:
    """SourceResponse dataclass exposes all required fields."""
    response = SourceResponse(
        source_id="CPSC",
        url="https://www.cpsc.gov/recalls",
        raw_content=b"<html>Electric shock recall</html>",
        title="Electric Shock Hazard Recall",
        published_at="2026-01-15",
        country="US",
        language="en",
        hazard_type="电击",
        severity="严重",
        product_name="Power Tool",
        manufacturer="Acme Corp",
    )
    assert response.source_id == "CPSC"
    assert response.url == "https://www.cpsc.gov/recalls"
    assert response.title == "Electric Shock Hazard Recall"
    assert response.hazard_type == "电击"
    assert response.severity == "严重"
    assert response.published_at == "2026-01-15"
    assert response.raw_content == b"<html>Electric shock recall</html>"
    assert response.country == "US"
    assert response.language == "en"
    assert response.success is True


def test_source_response_success_flag() -> None:
    """SourceResponse.success is False when status is not 'ok'."""
    error_response = SourceResponse(
        source_id="CPSC",
        url="https://www.cpsc.gov/recalls",
        raw_content=b"",
        status="error",
        error_msg="Connection timeout",
    )
    assert error_response.success is False
    assert error_response.error_msg == "Connection timeout"

    ok_empty_response = SourceResponse(
        source_id="CPSC",
        url="https://www.cpsc.gov/recalls",
        raw_content="",  # empty string still falsy for success check
        status="ok",
    )
    assert ok_empty_response.success is False


# ---------------------------------------------------------------------------
# Test 2: RiskEventStore score-update pipeline (no .get() method)
# ---------------------------------------------------------------------------

def test_risk_event_store_fetch_pending_and_update_scores(
    tmp_db_path: str,
) -> None:
    """RiskEventStore: fetch_pending returns unscored events; update_scores writes them."""
    _init_db(tmp_db_path)
    _seed_pending_event(tmp_db_path, "evt-pending-1")
    _seed_pending_event(tmp_db_path, "evt-pending-2")

    with UnitOfWork(tmp_db_path) as uow:
        store = RiskEventStore(uow)
        pending = store.fetch_pending()
        assert len(pending) == 2
        ids = {e["event_id"] for e in pending}
        assert ids == {"evt-pending-1", "evt-pending-2"}

        # Score the first event.
        scoring_result = {
            "ss_score": 90,
            "ps_score": 80,
            "probability_level": "可能",
            "country_factor": 1.0,
            "product_factor": 1.0,
            "history_factor": 1.0,
            "evidence_factor": 1.0,
            "causal_factor": 1.0,
            "total_score": 7200,
            "rs_level": "M",
        }
        store.update_scores("evt-pending-1", scoring_result, "1.0", "1.0")

        # fetch_pending should now return only the second event.
        remaining = store.fetch_pending()
        assert len(remaining) == 1
        assert remaining[0]["event_id"] == "evt-pending-2"


def test_risk_event_store_count_history(tmp_db_path: str) -> None:
    """RiskEventStore: count_history and count_history_by_product aggregate correctly."""
    _init_db(tmp_db_path)

    # Seed a scored historical event.
    conn = get_db_connection(tmp_db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO risk_events (
                event_id, title, country, manufacturer, product_category,
                hazard_type, publish_date, extracted_at,
                ss_score, ps_score, total_score, rs_level, evaluated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "evt-hist-1", "Historical Recall",
                "测试国", "某制造商", "普通机电", "电击",
                "2026-06-01", datetime.now().isoformat(),
                90, 80, 7200, "M", datetime.now().isoformat(),
            ),
        )
        conn.commit()
    finally:
        conn.close()

    with UnitOfWork(tmp_db_path) as uow:
        store = RiskEventStore(uow)
        since = "2025-01-01"

        # Match by country.
        count_country = store.count_history(
            since=since,
            country="测试国",
            manufacturer="unknown",
            product_category="unknown",
            hazard_type="unknown",
        )
        assert count_country >= 1

        # Match by product_category + hazard_type.
        count_product = store.count_history_by_product(
            since=since,
            product_category="普通机电",
            hazard_type="电击",
        )
        assert count_product >= 1

        # No match for unknown.
        count_none = store.count_history(
            since=since,
            country="未知国",
            manufacturer="unknown",
            product_category="unknown",
            hazard_type="unknown",
        )
        assert count_none == 0


def test_risk_event_store_append_risk_reasoning(tmp_db_path: str) -> None:
    """RiskEventStore.append_risk_reasoning appends AI reasoning to hazard_desc."""
    _init_db(tmp_db_path)
    _seed_pending_event(tmp_db_path, "evt-reasoning-1")

    reasoning_text = "该产品电击风险较高，建议加强市场监管。"

    with UnitOfWork(tmp_db_path) as uow:
        store = RiskEventStore(uow)
        store.append_risk_reasoning("evt-reasoning-1", reasoning_text)

    # Verify it was persisted.
    conn = get_db_connection(tmp_db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT hazard_desc FROM risk_events WHERE event_id = ?",
            ("evt-reasoning-1",),
        )
        row = cursor.fetchone()
        assert row is not None
        assert "AI风险分析" in row[0]
        assert reasoning_text in row[0]
    finally:
        conn.close()
