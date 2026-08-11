"""T27: Telemetry observability tests."""

from pathlib import Path

from whyfxpg.adapters.archive.in_memory_archive import InMemoryArchiveAdapter
from whyfxpg.adapters.telemetry.in_memory import InMemoryTelemetryAdapter
from whyfxpg.core.db import get_db_connection
from whyfxpg.core.information_pipeline import InformationPipeline, PipelineStage
from whyfxpg.migrations import MigrationRunner
from whyfxpg.services.pipeline_orchestrator import (
    PipelineContext,
    PipelineOrchestrator,
    StageResult,
)


def _init_db(db_path: str) -> None:
    conn = get_db_connection(db_path)
    try:
        MigrationRunner(conn).run()
        conn.commit()
    finally:
        conn.close()


def _build_pipeline() -> InformationPipeline:
    return InformationPipeline(
        name="telemetry-test",
        stages=[
            PipelineStage(name="collection", order=0, output_types=["raw_pages"]),
            PipelineStage(name="extraction", order=1, output_types=["events"]),
        ],
    )



def test_orchestrator_records_run_and_adapter_calls(
    tmp_path: Path,
) -> None:
    db_path = str(tmp_path / "telemetry.db")
    _init_db(db_path)
    archive = InMemoryArchiveAdapter()
    telemetry = InMemoryTelemetryAdapter()

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

    orchestrator = PipelineOrchestrator(
        pipeline=_build_pipeline(),
        stage_runners={"collection": _collection, "extraction": _extraction},
        archive_port=archive,
        db_path=db_path,
        telemetry_port=telemetry,
    )
    result = orchestrator.run()

    assert result["status"] == "success"
    assert len(telemetry.runs) == 1
    run_record = telemetry.runs[0]
    assert run_record.run_id == result["run_id"]
    assert run_record.pipeline_name == "telemetry-test"
    assert run_record.status == "success"
    assert len(run_record.stage_results) == 2
    assert {s["stage"] for s in run_record.stage_results} == {"collection", "extraction"}
    assert all("duration_ms" in s for s in run_record.stage_results)

    # Two stage artifacts archived = 2 adapter calls (no explicit archive stage => no manifest).
    assert len(telemetry.adapter_calls) == 2
    for call in telemetry.adapter_calls:
        assert call.adapter_name == "InMemoryArchiveAdapter"
        assert call.method == "archive"
        assert call.success



def test_orchestrator_records_health_snapshot(
    tmp_path: Path,
) -> None:
    db_path = str(tmp_path / "health.db")
    _init_db(db_path)
    archive = InMemoryArchiveAdapter()
    telemetry = InMemoryTelemetryAdapter()

    orchestrator = PipelineOrchestrator(
        pipeline=_build_pipeline(),
        stage_runners={
            "collection": lambda ctx: StageResult(
                status="success", output={}, archive=False
            ),
            "extraction": lambda ctx: StageResult(
                status="success", output={}, archive=False
            ),
        },
        archive_port=archive,
        db_path=db_path,
        telemetry_port=telemetry,
    )
    orchestrator.run()

    assert len(telemetry.health_snapshots) == 1
    snap = telemetry.health_snapshots[0]
    assert snap.service_name == "pipeline_orchestrator"
    assert snap.status == "success"
    assert snap.details["stage_count"] == 2
    assert snap.details["error_count"] == 0



def test_telemetry_port_is_optional(
    tmp_path: Path,
) -> None:
    """NullTelemetryPort keeps the orchestrator working when telemetry is omitted."""
    db_path = str(tmp_path / "noop.db")
    _init_db(db_path)
    archive = InMemoryArchiveAdapter()

    orchestrator = PipelineOrchestrator(
        pipeline=_build_pipeline(),
        stage_runners={
            "collection": lambda ctx: StageResult(
                status="success", output={}, archive=False
            ),
            "extraction": lambda ctx: StageResult(
                status="success", output={}, archive=False
            ),
        },
        archive_port=archive,
        db_path=db_path,
    )
    result = orchestrator.run()
    assert result["status"] == "success"
