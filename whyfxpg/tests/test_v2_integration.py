"""T22: End-to-end v2 seam integration test.

This test runs the full WHYfxpg v2 pipeline from a fake source to a dashboard
view model, using only in-memory / temporary resources. It verifies that the
seams (SourcePort, ExtractEngine, RiskEvaluationRunner, AlertEngine,
ReportGenerator, DashboardBuilderService, ArchivePort) can be wired together
and produce a coherent result without touching real networks or the production
whyfxpg.db.
"""

import hashlib
import sqlite3
from pathlib import Path
from typing import Any

from whyfxpg.adapters.archive.in_memory_archive import InMemoryArchiveAdapter
from whyfxpg.adapters.dashboard import (
    DashboardReadModelAdapter,
    InMemoryDashboardExportAdapter,
)
from whyfxpg.adapters.reports.in_memory_report_adapter import InMemoryReportRenderer
from whyfxpg.adapters.sources.in_memory_source_adapter import InMemorySourceAdapter
from whyfxpg.core.alert_engine import AlertEngine
from whyfxpg.core.db import get_db_connection
from whyfxpg.core.extract_engine import ExtractEngine
from whyfxpg.core.fetcher import Fetcher
from whyfxpg.core.information_pipeline import InformationPipeline, PipelineStage
from whyfxpg.core.report_generator import ReportGenerator
from whyfxpg.core.risk_evaluation_runner import RiskEvaluationRunner
from whyfxpg.ports.source_port import FetchedPage
from whyfxpg.services.dashboard_builder import DashboardBuilderService
from whyfxpg.services.pipeline_orchestrator import (
    PipelineContext,
    PipelineOrchestrator,
    StageResult,
)
from whyfxpg.webui.dashboard_models import (
    DashboardTemplate,
    ExportFormat,
    WidgetSpec,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TEST_CONTENT = (
    "标题：某普通机电产品因电击风险被召回。\n"
    "危害：产品存在电气危险，已导致消费者住院接受治疗。\n"
    "原产国：测试国\n"
    "发布日期：2024-05-20\n"
).encode()


def _content_hash(content: bytes) -> str:
    return hashlib.md5(content).hexdigest()


def _fake_source_page(source_id: str, cfg: dict[str, Any]) -> FetchedPage:
    return FetchedPage(
        source_id=source_id,
        url=cfg.get("url", "https://example.com/recall"),
        content=TEST_CONTENT,
        content_type="text/plain",
        content_hash=_content_hash(TEST_CONTENT),
        content_length=len(TEST_CONTENT),
        status="ok",
    )


def _fetch_collection(ctx: PipelineContext) -> StageResult:
    fetcher = Fetcher(
        config_dir=ctx.config_dir,
        db_path=ctx.db_path,
        source_port=InMemorySourceAdapter(callback=_fake_source_page),
    )
    result = fetcher.run()
    return StageResult(
        status="success" if result.get("status") == "success" else "partial",
        output={"fetcher_result": result},
        archive=True,
        artifact_type="raw_pages",
        artifact_name="batch",
    )


def _extract(ctx: PipelineContext) -> StageResult:
    engine = ExtractEngine(config_dir=ctx.config_dir, db_path=ctx.db_path)
    result = engine.run()
    return StageResult(
        status="success" if not result.get("errors") else "partial",
        output={"extract_result": result},
        archive=True,
        artifact_type="events",
        artifact_name="batch",
    )


def _evaluate(ctx: PipelineContext) -> StageResult:
    runner = RiskEvaluationRunner(config_dir=ctx.config_dir, db_path=ctx.db_path)
    result = runner.run()
    return StageResult(
        status="success" if result.get("status") == "success" else "partial",
        output={"evaluation_result": result},
        archive=True,
        artifact_type="risk_scores",
        artifact_name="batch",
    )


def _alert(ctx: PipelineContext) -> StageResult:
    engine = AlertEngine(config_dir=ctx.config_dir, db_path=ctx.db_path)
    result = engine.run()
    return StageResult(
        status="success" if not result.get("errors") else "partial",
        output={"alert_result": result},
        archive=True,
        artifact_type="alerts",
        artifact_name="batch",
    )


def _report(ctx: PipelineContext) -> StageResult:
    word_renderer = InMemoryReportRenderer()
    excel_renderer = InMemoryReportRenderer()
    generator = ReportGenerator(
        db_path=ctx.db_path,
        output_dir=ctx.params.get("report_output_dir"),
        word_renderer=word_renderer,
        excel_renderer=excel_renderer,
    )
    result = generator.run()
    return StageResult(
        status="success" if result.get("status") == "success" else "partial",
        output={
            "report_result": result,
            "word_calls": word_renderer.call_count,
            "excel_calls": excel_renderer.call_count,
        },
        archive=True,
        artifact_type="reports",
        artifact_name="batch",
    )


def _archive(ctx: PipelineContext) -> StageResult:
    return StageResult(status="success", output={})


def _count_rows(db_path: str, table: str) -> int:
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        return cursor.fetchone()[0]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------

def test_v2_end_to_end_pipeline(
    initialized_db: str, temp_config_dir: str, tmp_path: Path
) -> None:
    """Run the full v2 pipeline and verify every seam produces data."""
    report_output_dir = tmp_path / "reports"
    archive = InMemoryArchiveAdapter()

    pipeline = InformationPipeline(
        name="v2-integration",
        stages=[
            PipelineStage(name="collection", order=0, output_types=["raw_pages"]),
            PipelineStage(name="extraction", order=1, output_types=["events"]),
            PipelineStage(name="evaluation", order=2, output_types=["risk_scores"]),
            PipelineStage(name="alerting", order=3, output_types=["alerts"]),
            PipelineStage(name="reporting", order=4, output_types=["reports"]),
            PipelineStage(name="archive", order=5, output_types=["manifest"]),
        ],
    )

    orchestrator = PipelineOrchestrator(
        pipeline=pipeline,
        stage_runners={
            "collection": _fetch_collection,
            "extraction": _extract,
            "evaluation": _evaluate,
            "alerting": _alert,
            "reporting": _report,
            "archive": _archive,
        },
        archive_port=archive,
        db_path=initialized_db,
    )

    pipeline_result = orchestrator.run(
        params={
            "config_dir": temp_config_dir,
            "report_output_dir": str(report_output_dir),
        }
    )

    # 1. Pipeline completed successfully
    assert pipeline_result["status"] == "success", pipeline_result.get("errors")
    assert pipeline_result["run_id"]
    run_id = pipeline_result["run_id"]

    # 2. Run manifest archived
    artifacts = archive.list_run_artifacts(run_id)
    assert f"{run_id}/manifest/run_manifest.json" in artifacts

    # 3. Stage artifacts archived
    assert any(a.endswith("/raw_pages/batch.json") for a in artifacts)
    assert any(a.endswith("/events/batch.json") for a in artifacts)
    assert any(a.endswith("/reports/batch.json") for a in artifacts)

    # 4. Raw page persisted
    assert _count_rows(initialized_db, "raw_pages") == 1

    # 5. Risk event extracted and scored
    conn = get_db_connection(initialized_db)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT event_id, country, hazard_type, severity_level, total_score, rs_level "
            "FROM risk_events"
        )
        row = cursor.fetchone()
        assert row is not None
        _event_id, country, hazard_type, severity_level, total_score, rs_level = row
        assert country == "测试国"
        assert hazard_type == "电气危险"
        assert severity_level == "严重"
        assert total_score >= 8000
        # P1b-03:严重(95)×可能(95)=9025 → 归一化 75.1 → M 级(0-100 量纲)
        assert rs_level == "M"
    finally:
        conn.close()

    # 6. Alert triggered for high-severity event
    assert _count_rows(initialized_db, "alert_records") >= 1

    # 7. Report renderers invoked
    report_handle = artifacts[f"{run_id}/reports/batch.json"]
    reports_payload = archive.retrieve(report_handle)
    assert reports_payload["report_result"]["status"] == "success"
    assert reports_payload["word_calls"] == 1
    assert reports_payload["excel_calls"] == 1

    # 8. Dashboard can be built from the resulting DB state
    dashboard_data = DashboardReadModelAdapter(initialized_db)
    export_port = InMemoryDashboardExportAdapter()
    builder = DashboardBuilderService(
        data_port=dashboard_data,
        export_port=export_port,
    )
    template = DashboardTemplate(
        dashboard_id="v2-integration",
        name="V2 Integration",
        widgets=[
            WidgetSpec(
                widget_id="kpi_total",
                type="metric",
                query="summary.total_events",
                title="Total Events",
            ),
            WidgetSpec(
                widget_id="table_high_risk",
                type="table",
                query="recent_high_risk.limit=15",
                title="High Risk Events",
            ),
        ],
    )
    view_model = builder.build(template)
    assert view_model.dashboard_id == "v2-integration"
    assert len(view_model.widgets) == 2
    assert view_model.widgets[0].data == 1
    assert len(view_model.widgets[1].data) == 1

    # 9. Dashboard can be exported
    export_path = builder.export(view_model, ExportFormat.EXCEL)
    assert export_path is not None
    assert export_port.exports == [("v2-integration", ExportFormat.EXCEL)]
