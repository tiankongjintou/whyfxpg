"""T20: Pipeline & Archive seam tests."""

import sqlite3
from pathlib import Path
from typing import Any

import yaml

from whyfxpg.adapters.archive.file_system_archive import FileSystemArchiveAdapter
from whyfxpg.adapters.archive.in_memory_archive import InMemoryArchiveAdapter
from whyfxpg.core.db import get_db_connection
from whyfxpg.core.information_pipeline import (
    InformationPipeline,
    PipelineStage,
    StageStatus,
)
from whyfxpg.core.pipeline_store import AuditLogStore, PipelineRunStore
from whyfxpg.migrations import MigrationRunner
from whyfxpg.ports.archive import ArchiveHandle
from whyfxpg.services.feedback_learning_service import FeedbackLearningService
from whyfxpg.services.lineage_service import LineageService
from whyfxpg.services.pipeline_orchestrator import (
    PipelineContext,
    PipelineOrchestrator,
    StageResult,
)
from whyfxpg.services.review_service import ReviewService, ReviewSubmission


def _init_db(db_path: str) -> None:
    conn = get_db_connection(db_path)
    try:
        MigrationRunner(conn).run()
        conn.commit()
    finally:
        conn.close()


# ───────────────────────────────────────────────────────────────
# Migration & persistence
# ───────────────────────────────────────────────────────────────


def test_pipeline_audit_tables_created(tmp_db_path: str) -> None:
    _init_db(tmp_db_path)
    conn = sqlite3.connect(tmp_db_path)
    try:
        cursor = conn.cursor()
        for table in ["pipeline_runs", "pipeline_stage_runs", "audit_log"]:
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
            )
            assert cursor.fetchone() is not None, f"{table} should exist"
    finally:
        conn.close()


def test_pipeline_run_store_records_stages(tmp_db_path: str) -> None:
    _init_db(tmp_db_path)
    from whyfxpg.core.stores import UnitOfWork

    with UnitOfWork(tmp_db_path) as uow:
        store = PipelineRunStore(uow)
        store.create_run("run-1", "default")
        s1 = store.start_stage("run-1", "collection", 0)
        store.complete_stage(s1, StageStatus.SUCCESS.value)
        s2 = store.start_stage("run-1", "evaluation", 1)
        store.complete_stage(s2, StageStatus.FAILED.value, error_message="boom")
        store.complete_run("run-1", "partial")

    with UnitOfWork(tmp_db_path) as uow:
        store = PipelineRunStore(uow)
        run = store.get_run("run-1")
        assert run is not None
        assert run["status"] == "partial"

        stages = store.list_stage_runs("run-1")
        assert len(stages) == 2
        assert stages[0]["status"] == "success"
        assert stages[1]["status"] == "failed"


# ───────────────────────────────────────────────────────────────
# Archive adapters
# ───────────────────────────────────────────────────────────────


def test_in_memory_archive_adapter() -> None:
    archive = InMemoryArchiveAdapter()
    payload = {"events": [{"id": "e1"}]}
    handle = archive.archive("run-1", "events", "batch", payload)
    assert isinstance(handle, ArchiveHandle)
    assert handle.handle == "run-1/events/batch.json"
    assert archive.retrieve(handle) == payload

    listed = archive.list_run_artifacts("run-1")
    assert handle.handle in listed


def test_file_system_archive_adapter(tmp_path: Path) -> None:
    root = tmp_path / "archive"
    archive = FileSystemArchiveAdapter(str(root))
    payload = {"events": [{"id": "e1"}]}
    handle = archive.archive("run-1", "events", "batch", payload)
    assert (Path(handle.path)).exists()  # type: ignore[arg-type]
    assert archive.retrieve(handle) == payload

    listed = archive.list_run_artifacts("run-1")
    assert handle.handle in listed


# ───────────────────────────────────────────────────────────────
# Pipeline orchestrator
# ───────────────────────────────────────────────────────────────


def test_orchestrator_runs_all_stages_and_archives(tmp_db_path: str, tmp_path: Path) -> None:
    _init_db(tmp_db_path)
    archive = InMemoryArchiveAdapter()

    def _collection(ctx: PipelineContext) -> StageResult:
        return StageResult(
            status="success",
            output={"items": [ctx.run_id]},
            archive=True,
            artifact_type="raw_pages",
            artifact_name="batch",
        )

    def _extraction(ctx: PipelineContext) -> StageResult:
        return StageResult(
            status="success",
            output={"events": [ctx.run_id]},
            archive=True,
            artifact_type="events",
            artifact_name="batch",
        )

    pipeline = InformationPipeline(
        name="test",
        stages=[
            PipelineStage(name="collection", order=0, output_types=["raw_pages"]),
            PipelineStage(name="extraction", order=1, input_types=["raw_pages"], output_types=["events"]),
        ],
    )
    orchestrator = PipelineOrchestrator(
        pipeline=pipeline,
        stage_runners={"collection": _collection, "extraction": _extraction},
        archive_port=archive,
        db_path=tmp_db_path,
    )
    result = orchestrator.run(params={"config_dir": str(tmp_path)})

    assert result["status"] == "success"
    assert result["run_id"]
    assert len(archive.list_run_artifacts(result["run_id"])) == 2

    from whyfxpg.core.stores import UnitOfWork

    with UnitOfWork(tmp_db_path) as uow:
        store = PipelineRunStore(uow)
        run = store.get_run(result["run_id"])
        assert run["status"] == "success"  # type: ignore[index]
        assert len(store.list_stage_runs(result["run_id"])) == 2


def test_orchestrator_retries_and_marks_partial(tmp_db_path: str) -> None:
    _init_db(tmp_db_path)
    archive = InMemoryArchiveAdapter()
    attempts = {"count": 0}

    def flaky_runner(ctx: PipelineContext) -> StageResult:
        attempts["count"] += 1
        if attempts["count"] < 2:
            raise RuntimeError("transient")
        return StageResult(status="success", output={"ok": True})

    pipeline = InformationPipeline(
        name="test",
        stages=[
            PipelineStage(name="collection", order=0, max_retries=2, output_types=["raw_pages"]),
            PipelineStage(name="extraction", order=1, output_types=["events"]),
        ],
    )
    orchestrator = PipelineOrchestrator(
        pipeline=pipeline,
        stage_runners={"collection": flaky_runner, "extraction": lambda ctx: StageResult(status="success", output={})},
        archive_port=archive,
        db_path=tmp_db_path,
    )
    result = orchestrator.run()
    assert result["status"] == "success"
    assert attempts["count"] == 2


def test_orchestrator_stage_failure_marks_partial(tmp_db_path: str) -> None:
    _init_db(tmp_db_path)
    archive = InMemoryArchiveAdapter()

    def bad_runner(ctx: PipelineContext) -> StageResult:
        raise RuntimeError("stage down")

    pipeline = InformationPipeline(
        name="test",
        stages=[
            PipelineStage(name="collection", order=0, output_types=["raw_pages"]),
            PipelineStage(name="extraction", order=1, output_types=["events"]),
        ],
    )
    orchestrator = PipelineOrchestrator(
        pipeline=pipeline,
        stage_runners={"collection": bad_runner, "extraction": lambda ctx: StageResult(status="success", output={})},
        archive_port=archive,
        db_path=tmp_db_path,
    )
    result = orchestrator.run()
    assert result["status"] == "partial"
    assert "collection" in result["errors"][0]


# ───────────────────────────────────────────────────────────────
# Lineage service
# ───────────────────────────────────────────────────────────────


def _insert_lineage_fixtures(db_path: str) -> None:
    _init_db(db_path)
    conn = get_db_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO monitor_sources (source_id, name, url, source_type, enabled, check_interval, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("src-1", "Source 1", "https://example.com", "web", 1, "1h", "ok"),
        )
        cursor.execute(
            """
            INSERT INTO crawl_logs (source_id, run_at, status, pages_fetched, pages_new)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("src-1", "2026-01-01T00:00:00", "ok", 5, 2),
        )
        cursor.execute(
            """
            INSERT INTO raw_pages (page_id, source_id, url, fetched_at, content_type, content_hash, raw_content, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("page-1", "src-1", "https://example.com/1", "2026-01-01T00:00:00", "text/html", "hash", b"content", "fetched"),
        )
        cursor.execute(
            """
            INSERT INTO risk_events (
                event_id, page_id, source_id, source_url, title, country, manufacturer,
                product_category, hazard_type, publish_date, extracted_at,
                ss_score, ps_score, total_score, rs_level, evaluated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "evt-1", "page-1", "src-1", "https://example.com/1", "Recall", "测试国",
                "Mfr-A", "普通机电", "电击", "2026-01-01", "2026-01-01T00:00:00",
                90, 80, 7200, "M", "2026-01-01T00:00:00",
            ),
        )
        cursor.execute(
            """
            INSERT INTO alert_records (alert_id, rule_id, rule_name, triggered_at,
                                       object_type, object_value, severity, triggered_value, description, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("alert-1", "rule-1", "R1", "2026-01-01T00:00:00", "event", "evt-1", "high", "M", "desc", "pending"),
        )
        cursor.execute(
            """
            INSERT INTO manual_reviews (review_id, event_id, reviewer, reviewed_at, action,
                                        original_ss, adjusted_ss, original_ps, adjusted_ps,
                                        original_rs, adjusted_rs, reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("review-1", "evt-1", "operator", "2026-01-01T00:00:00", "correct", 90, 60, 80, 80, "M", "L", "reason"),
        )
        conn.commit()
    finally:
        conn.close()


def test_lineage_service_by_event(tmp_db_path: str) -> None:
    _insert_lineage_fixtures(tmp_db_path)
    service = LineageService(db_path=tmp_db_path)
    chain = service.get_lineage_by_event("evt-1")

    assert chain["seed_type"] == "event"
    assert chain["event"]["event_id"] == "evt-1"
    assert chain["raw_page"]["page_id"] == "page-1"
    assert chain["source"]["source_id"] == "src-1"
    assert chain["crawl_log"]["source_id"] == "src-1"
    assert len(chain["alerts"]) == 1
    assert chain["alerts"][0]["alert_id"] == "alert-1"
    assert len(chain["reviews"]) == 1
    assert chain["reviews"][0]["review_id"] == "review-1"


def test_lineage_service_by_alert(tmp_db_path: str) -> None:
    _insert_lineage_fixtures(tmp_db_path)
    service = LineageService(db_path=tmp_db_path)
    chain = service.get_lineage_by_alert("alert-1")
    assert chain["seed_type"] == "alert"
    assert chain["alert"]["alert_id"] == "alert-1"
    assert chain["event"]["event_id"] == "evt-1"


def test_lineage_service_by_review(tmp_db_path: str) -> None:
    _insert_lineage_fixtures(tmp_db_path)
    service = LineageService(db_path=tmp_db_path)
    chain = service.get_lineage_by_review("review-1")
    assert chain["seed_type"] == "review"
    assert chain["review"]["review_id"] == "review-1"
    assert chain["event"]["event_id"] == "evt-1"


# ───────────────────────────────────────────────────────────────
# Feedback learning service closes the loop
# ───────────────────────────────────────────────────────────────


def test_feedback_learning_service_updates_config_and_audits(
    tmp_db_path: str, tmp_path: Path, monkeypatch: Any
) -> None:
    from whyfxpg.core.config_loader import ConfigLoader
    from whyfxpg.core.feedback_learner import FeedbackLearner
    from whyfxpg.core.stores import UnitOfWork

    _init_db(tmp_db_path)

    # Seed a minimal risk_model.yaml in a temp config dir.
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir()
    risk_model = {
        "version": "1.0",
        "country_factors": {"测试国": 1.0, "unknown": 1.0},
        "product_factors": {"普通机电": 1.0, "unknown": 1.0},
        "severity_levels": {"严重": {"score": 100}},
        "probability_levels": {"可能": {"score": 80}},
        "history_factor": {"formula": "1", "max": 1.0, "min": 1.0},
        "evidence_factors": {"unknown": 1.0},
        "risk_level_thresholds": {"S": 8000, "M": 3000, "L": 1000, "A": 0},
    }
    (cfg_dir / "risk_model.yaml").write_text(yaml.safe_dump(risk_model), encoding="utf-8")

    # Monkeypatch FeedbackLearner to simulate an adjustment.
    def _fake_learn(self, yaml_config=None):
        updated = dict(yaml_config or ConfigLoader(str(cfg_dir)).risk_model)
        updated["country_factors"] = {"测试国": 1.1, "unknown": 1.0}
        return {
            "status": "success",
            "model_adjustments": [{"dimension": "country", "key": "测试国", "delta": 0.1}],
            "causal_adjustments": [],
            "message": "country factor bumped",
            "yaml_config": updated,
        }

    monkeypatch.setattr(FeedbackLearner, "learn", _fake_learn)

    service = FeedbackLearningService(
        db_path=tmp_db_path,
        config_dir=str(cfg_dir),
    )
    result = service.learn_and_apply()

    assert result["status"] == "success"
    assert result["published"] is True

    # Verify config file was updated.
    loader = ConfigLoader(str(cfg_dir))
    assert loader.risk_model["country_factors"]["测试国"] == 1.1

    # Verify audit log.
    with UnitOfWork(tmp_db_path) as uow:
        audit = AuditLogStore(uow)
        logs = audit.list_for_target("model", "default")
        assert any(log["action"] == "feedback_learning_applied" for log in logs)


# ───────────────────────────────────────────────────────────────
# Review service triggers feedback learning
# ───────────────────────────────────────────────────────────────


def test_review_service_triggers_feedback_learning(
    tmp_db_path: str, tmp_path: Path, monkeypatch: Any
) -> None:
    from whyfxpg.core.feedback_learner import FeedbackLearner

    _init_db(tmp_db_path)

    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir()
    (cfg_dir / "risk_model.yaml").write_text(
        "version: '1.0'\n"
        "severity_levels:\n"
        "  灾难性: {score: 100}\n"
        "  严重: {default: 95}\n"
        "  中等: {default: 60}\n"
        "  轻微: {default: 15}\n"
        "country_factors:\n"
        "  测试国: 1.0\n",
        encoding="utf-8",
    )

    # Seed a pending event.
    conn = get_db_connection(tmp_db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO risk_events (event_id, title, country, manufacturer, product_category,
                                     hazard_type, publish_date, extracted_at,
                                     severity_level, ss_score, ps_score, total_score, rs_level, evaluated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("evt-review", "R", "测试国", "Mfr", "普通机电", "电击",
             "2026-01-01", "2026-01-01T00:00:00",
             "中等", 60, 50, 3000, "L", "2026-01-01T00:00:00"),
        )
        conn.commit()
    finally:
        conn.close()

    triggered: dict[str, bool] = {"called": False}

    def _fake_learn(self, yaml_config=None):
        triggered["called"] = True
        return {
            "status": "success",
            "model_adjustments": [],
            "causal_adjustments": [],
            "message": "noop",
            "yaml_config": yaml_config or {},
        }

    monkeypatch.setattr(FeedbackLearner, "learn", _fake_learn)

    feedback_service = FeedbackLearningService(db_path=tmp_db_path, config_dir=str(cfg_dir))
    review_service = ReviewService(db_path=tmp_db_path, feedback_service=feedback_service)

    review_service.submit_review(
        ReviewSubmission(
            event_id="evt-review",
            reviewer="operator",
            reason="test",
            adjusted_rs_level="A",
            adjusted_ss_score=30,
        )
    )

    assert triggered["called"] is True
