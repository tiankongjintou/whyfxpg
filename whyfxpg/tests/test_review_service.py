"""Tests for whyfxpg.services.review_service."""


import pytest

from whyfxpg.services.review_service import (
    ReviewRecord,
    ReviewService,
    ReviewSubmission,
)


def _insert_event(conn, event_id: str, **overrides) -> None:
    defaults = {
        "page_id": "p1",
        "source_id": "src1",
        "publish_date": "2026-01-01",
        "product_name": "测试产品",
        "brand": "测试品牌",
        "model": "M1",
        "country": "测试国",
        "manufacturer": "测试厂",
        "hazard_type": "电气危险",
        "severity_level": "高",
        "ss_score": 90,
        "ps_score": 80,
        "rs_level": "M",
        "total_score": 7200.0,
    }
    defaults.update(overrides)
    fields = ", ".join(defaults.keys())
    placeholders = ", ".join(["?"] * len(defaults))
    conn.execute(f"INSERT INTO risk_events (event_id, {fields}) VALUES (?, {placeholders})", (event_id, *defaults.values()))


def test_submit_review_inserts_record_and_updates_status(initialized_db):
    service = ReviewService(initialized_db)
    conn = pytest.importorskip("whyfxpg.core.db").get_db_connection(initialized_db)
    _insert_event(conn, "evt-001")
    conn.commit()
    conn.close()

    record = service.submit_review(
        ReviewSubmission(
            event_id="evt-001",
            reviewer="张三",
            reason="测试修正",
            adjusted_rs_level="S",
            adjusted_ss_score=95,
        )
    )

    assert isinstance(record, ReviewRecord)
    assert record.event_id == "evt-001"
    assert record.adjusted_rs == "S"
    assert record.adjusted_ss == 95
    assert record.reviewer == "张三"

    conn = pytest.importorskip("whyfxpg.core.db").get_db_connection(initialized_db)
    cursor = conn.cursor()
    cursor.execute("SELECT review_status FROM risk_events WHERE event_id = ?", ("evt-001",))
    assert cursor.fetchone()["review_status"] == "reviewed"

    cursor.execute("SELECT * FROM manual_reviews WHERE event_id = ?", ("evt-001",))
    row = cursor.fetchone()
    assert row is not None
    assert row["adjusted_rs"] == "S"
    assert row["adjusted_ss"] == 95
    conn.close()


def test_submit_review_defaults_ss_from_severity(initialized_db):
    service = ReviewService(initialized_db)
    conn = pytest.importorskip("whyfxpg.core.db").get_db_connection(initialized_db)
    _insert_event(conn, "evt-002", severity_level="中", ss_score=60, rs_level="L")
    conn.commit()
    conn.close()

    record = service.submit_review(
        ReviewSubmission(
            event_id="evt-002",
            reviewer="李四",
            reason="中风险",
            adjusted_rs_level="M",
            adjusted_ss_score=70,
        )
    )

    assert record.original_ss == 60
    assert record.adjusted_ss == 70


def test_submit_review_missing_event_raises(initialized_db):
    service = ReviewService(initialized_db)
    with pytest.raises(ValueError, match="事件不存在"):
        service.submit_review(
            ReviewSubmission(
                event_id="evt-missing",
                reviewer="王五",
                reason="不存在",
                adjusted_rs_level="S",
                adjusted_ss_score=100,
            )
        )


@pytest.mark.parametrize("field", ["reviewer", "reason"])
def test_submit_review_validation(initialized_db, field):
    service = ReviewService(initialized_db)
    kwargs = {
        "event_id": "evt-003",
        "reviewer": "王五",
        "reason": "测试",
        "adjusted_rs_level": "S",
        "adjusted_ss_score": 80,
    }
    kwargs[field] = "   "
    with pytest.raises(ValueError):
        service.submit_review(ReviewSubmission(**kwargs))


def test_submit_review_invalid_rs_level(initialized_db):
    service = ReviewService(initialized_db)
    with pytest.raises(ValueError):
        service.submit_review(
            ReviewSubmission(
                event_id="evt-004",
                reviewer="王五",
                reason="bad level",
                adjusted_rs_level="X",
                adjusted_ss_score=80,
            )
        )


def test_get_history(initialized_db):
    service = ReviewService(initialized_db)
    conn = pytest.importorskip("whyfxpg.core.db").get_db_connection(initialized_db)
    for i in range(3):
        eid = f"evt-h{i}"
        _insert_event(conn, eid, product_name=f"产品{i}", country=f"国{i}")
    conn.commit()
    conn.close()

    for i in range(3):
        service.submit_review(
            ReviewSubmission(
                event_id=f"evt-h{i}",
                reviewer=f"reviewer-{i}",
                reason=f"reason-{i}",
                adjusted_rs_level="S",
                adjusted_ss_score=90 + i,
            )
        )

    history = service.get_history(limit=2)
    assert len(history) == 2
    assert all(isinstance(r, ReviewRecord) for r in history)
    # 默认按时间倒序
    assert history[0].reviewed_at >= history[1].reviewed_at

    full = service.get_history(limit=100)
    assert len(full) == 3


def test_get_history_limit_validation(initialized_db):
    service = ReviewService(initialized_db)
    with pytest.raises(ValueError, match="limit 必须大于 0"):
        service.get_history(limit=0)


def test_default_adjusted_ss_score():
    assert ReviewService.default_adjusted_ss_score("高") == 90
    assert ReviewService.default_adjusted_ss_score("中") == 60
    assert ReviewService.default_adjusted_ss_score("低") == 30
    assert ReviewService.default_adjusted_ss_score(None) == 30
