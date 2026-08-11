"""Pipeline orchestrator.

Runs the information-pipeline stages in order, records stage status, archives
outputs, and exposes a hook for feedback/audit tracing.
"""

import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from whyfxpg.core.information_pipeline import (
    InformationPipeline,
    PipelineStage,
    PipelineStatus,
    StageArtifact,
    StageStatus,
)
from whyfxpg.core.stores import UnitOfWork
from whyfxpg.core.stores.archive_store import AuditLogStore, PipelineRunStore
from whyfxpg.ports.archive import ArchiveHandle, ArchivePort
from whyfxpg.ports.telemetry import TelemetryPort
from whyfxpg.services.notification_service import NotificationService
from whyfxpg.services.telemetry_service import TelemetryService


@dataclass
class PipelineContext:
    """Mutable context passed to each stage runner."""

    run_id: str
    config_dir: str | None = None
    db_path: str | None = None
    params: dict[str, Any] = field(default_factory=dict)
    artifacts: dict[str, StageArtifact] = field(default_factory=dict)

    @property
    def artifact_payloads(self) -> dict[str, dict[str, Any]]:
        return {k: v.payload for k, v in self.artifacts.items()}


@dataclass
class StageResult:
    """Result returned by a stage runner."""

    status: str  # success / failed / skipped
    output: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    archive: bool = False
    artifact_type: str = ""
    artifact_name: str = ""


StageRunner = Callable[[PipelineContext], StageResult]


class PipelineOrchestrator:
    """Run an InformationPipeline, recording every stage and archiving artifacts."""

    def __init__(
        self,
        pipeline: InformationPipeline,
        stage_runners: dict[str, StageRunner],
        archive_port: ArchivePort,
        db_path: str | None = None,
        telemetry_port: TelemetryPort | None = None,
    ):
        self.pipeline = pipeline
        self.stage_runners = stage_runners
        self.archive_port = archive_port
        self.db_path = db_path
        self._telemetry = TelemetryService(telemetry_port)

    def run(
        self,
        params: dict[str, Any] | None = None,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        run_id = run_id or str(uuid.uuid4())
        params = params or {}
        run_start = time.perf_counter()

        with UnitOfWork(self.db_path) as uow:
            store = PipelineRunStore(uow)
            audit = AuditLogStore(uow)
            store.create_run(run_id, self.pipeline.name)
            audit.write(
                actor="pipeline_orchestrator",
                action="pipeline_started",
                target_type="pipeline_run",
                target_id=run_id,
                after_value=f"stages={len(self.pipeline.ordered_stages())}",
            )

        context = PipelineContext(
            run_id=run_id,
            config_dir=params.get("config_dir"),
            db_path=self.db_path,
            params=params,
        )

        statuses: list[str] = []
        errors: list[str] = []
        stage_results: list[dict[str, Any]] = []
        last_output_handle: str | None = None

        for stage in self.pipeline.ordered_stages():
            last_output_handle = self._run_stage(
                run_id=run_id,
                stage=stage,
                context=context,
                statuses=statuses,
                errors=errors,
                stage_results=stage_results,
                input_handle=last_output_handle,
            )

        final_status = self._derive_status(statuses)
        archived_path: str | None = None
        if self._has_archive_stage():
            archived_path = self._archive_run_manifest(run_id, context, statuses)

        # 失败/部分成功时写入通知中心，便于 Web UI 提醒
        if final_status in (PipelineStatus.FAILED, PipelineStatus.PARTIAL):
            try:
                NotificationService(self.db_path).record(
                    notification_type="pipeline_failure",
                    severity="error" if final_status == PipelineStatus.FAILED else "warning",
                    title=f"流水线运行 {final_status.value}: {self.pipeline.name}",
                    message="; ".join(errors) if errors else "存在阶段未成功完成，请检查运行日志",
                    source_type="pipeline",
                    source_id=run_id,
                )
            except Exception:  # noqa: BLE001, S110 — 刻意用法(见 TD03)
                # 通知写入失败不应阻塞流水线归档
                pass

        run_duration_ms = (time.perf_counter() - run_start) * 1000

        with UnitOfWork(self.db_path) as uow:
            store = PipelineRunStore(uow)
            audit = AuditLogStore(uow)
            store.complete_run(
                run_id=run_id,
                status=final_status.value,
                error_message="; ".join(errors) if errors else None,
                archived_path=archived_path,
            )
            audit.write(
                actor="pipeline_orchestrator",
                action="pipeline_completed",
                target_type="pipeline_run",
                target_id=run_id,
                after_value=f"status={final_status.value}",
            )

        self._telemetry.record_run(
            run_id=run_id,
            pipeline_name=self.pipeline.name,
            duration_ms=round(run_duration_ms, 3),
            status=final_status.value,
            stage_results=stage_results,
        )
        self._telemetry.record_health_snapshot(
            service_name="pipeline_orchestrator",
            status=final_status.value,
            details={
                "run_id": run_id,
                "pipeline_name": self.pipeline.name,
                "stage_count": len(self.pipeline.ordered_stages()),
                "error_count": len(errors),
                "duration_ms": round(run_duration_ms, 3),
            },
        )

        return {
            "run_id": run_id,
            "pipeline_name": self.pipeline.name,
            "status": final_status.value,
            "errors": errors,
            "artifacts": {k: v.artifact_type for k, v in context.artifacts.items()},
            "archived_path": archived_path,
        }

    def _run_stage(
        self,
        run_id: str,
        stage: PipelineStage,
        context: PipelineContext,
        statuses: list[str],
        errors: list[str],
        stage_results: list[dict[str, Any]],
        input_handle: str | None,
    ) -> str | None:
        stage_start = time.perf_counter()
        runner = self.stage_runners.get(stage.name)
        if runner is None:
            # Stage configured but no runner -> mark skipped.
            with UnitOfWork(self.db_path) as uow:
                store = PipelineRunStore(uow)
                stage_run_id = store.start_stage(
                    run_id, stage.name, stage.order, input_handle
                )
                store.complete_stage(
                    stage_run_id,
                    StageStatus.SKIPPED.value,
                    error_message="no stage runner registered",
                )
            statuses.append(StageStatus.SKIPPED.value)
            stage_results.append({"stage": stage.name, "status": StageStatus.SKIPPED.value})
            return input_handle

        attempt = 0
        max_attempts = max(stage.max_retries + 1, 1)
        result: StageResult | None = None
        last_error: str | None = None

        while attempt < max_attempts:
            attempt += 1
            try:
                result = runner(context)
                break
            except Exception as exc:  # noqa: BLE001
                last_error = f"{type(exc).__name__}: {exc}"
                continue

        stage_duration_ms = (time.perf_counter() - stage_start) * 1000

        output_handle: str | None = None
        if result is None:
            status = StageStatus.FAILED.value
            error = last_error or "stage runner failed"
            stage_error = error
            result = StageResult(status=status, error=error)
        elif result.status != StageStatus.SUCCESS.value and result.status != "success":
            status = result.status
            stage_error = result.error or ""
        else:
            status = StageStatus.SUCCESS.value
            stage_error = None
            if result.archive and result.artifact_type:
                handle = self._timed_archive(
                    run_id,
                    result.artifact_type,
                    result.artifact_name or stage.name,
                    result.output,
                )
                output_handle = handle.handle
                archived_path = handle.path or output_handle  # noqa: F841 — 刻意用法(见 TD03)
                context.artifacts[stage.name] = StageArtifact(
                    artifact_type=result.artifact_type,
                    payload=result.output,
                    handle=output_handle,
                    archived_path=handle.path,
                )
            else:
                context.artifacts[stage.name] = StageArtifact(
                    artifact_type=stage.output_types[0] if stage.output_types else "object",
                    payload=result.output,
                )

        with UnitOfWork(self.db_path) as uow:
            store = PipelineRunStore(uow)
            stage_run_id = store.start_stage(
                run_id, stage.name, stage.order, input_handle
            )
            store.complete_stage(
                stage_run_id,
                status,
                output_handle=output_handle,
                error_message=stage_error,
            )

        statuses.append(status)
        stage_results.append({
            "stage": stage.name,
            "status": status,
            "duration_ms": round(stage_duration_ms, 3),
            "error": stage_error,
        })
        if status != StageStatus.SUCCESS.value and stage_error:
            errors.append(f"{stage.name}: {stage_error}")
        return output_handle or input_handle

    def _timed_archive(
        self,
        run_id: str,
        artifact_type: str,
        artifact_name: str,
        payload: Any,
    ) -> ArchiveHandle:
        start = time.perf_counter()
        success = False
        try:
            handle = self.archive_port.archive(
                run_id, artifact_type, artifact_name, payload
            )
            success = True
            return handle
        finally:
            self._telemetry.record_adapter_call(
                adapter_name=self.archive_port.__class__.__name__,
                method="archive",
                duration_ms=round((time.perf_counter() - start) * 1000, 3),
                success=success,
            )

    def _derive_status(self, statuses: list[str]) -> PipelineStatus:
        if not statuses:
            return PipelineStatus.SKIPPED
        if all(s in (StageStatus.SUCCESS.value, StageStatus.SKIPPED.value) for s in statuses):
            return PipelineStatus.SUCCESS
        if all(s == StageStatus.SKIPPED.value for s in statuses):
            return PipelineStatus.SKIPPED
        if any(s == StageStatus.SUCCESS.value for s in statuses):
            return PipelineStatus.PARTIAL
        return PipelineStatus.FAILED

    def _has_archive_stage(self) -> bool:
        return any(s.name == "archive" for s in self.pipeline.stages)

    def _archive_run_manifest(
        self,
        run_id: str,
        context: PipelineContext,
        statuses: list[str],
    ) -> str | None:
        manifest = {
            "run_id": run_id,
            "pipeline_name": self.pipeline.name,
            "created_at": datetime.now().isoformat(),  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
            "stage_statuses": statuses,
            "artifact_handles": {k: v.handle for k, v in context.artifacts.items()},
        }
        handle = self._timed_archive(
            run_id,
            "manifest",
            "run_manifest",
            manifest,
        )
        return handle.path or handle.handle


def build_default_stage_runners(
    config_dir: str | None = None,
    db_path: str | None = None,
) -> dict[str, StageRunner]:
    """Default stage runners that delegate to existing WHYfxpg modules.

    This registry wires legacy modules through the new seam without replacing
    them. Each runner returns a lightweight StageResult so the orchestrator can
    record status and archive outputs.
    """
    from whyfxpg.core.alert_engine import AlertEngine
    from whyfxpg.core.extract_engine import ExtractEngine
    from whyfxpg.core.fetcher import Fetcher
    from whyfxpg.core.report_generator import ReportGenerator
    from whyfxpg.core.risk_evaluation_runner import RiskEvaluationRunner

    def _collection(ctx: PipelineContext) -> StageResult:
        fetcher = Fetcher(
            config_dir=ctx.config_dir,
            db_path=ctx.db_path or ctx.db_path,
        )
        result = fetcher.run()
        return StageResult(
            status="success" if result.get("status") == "success" else "partial",
            output={"fetcher_result": result},
            archive=False,
        )

    def _extraction(ctx: PipelineContext) -> StageResult:
        engine = ExtractEngine(
            config_dir=ctx.config_dir,
            db_path=ctx.db_path,
        )
        result = engine.run()
        return StageResult(
            status="success" if not result.get("errors") else "partial",
            output={"extract_result": result},
            archive=False,
        )

    def _evaluation(ctx: PipelineContext) -> StageResult:
        runner = RiskEvaluationRunner(
            config_dir=ctx.config_dir,
            db_path=ctx.db_path,
        )
        result = runner.run()
        return StageResult(
            status="success" if result.get("status") == "success" else "partial",
            output={"evaluation_result": result},
            archive=False,
        )

    def _alerting(ctx: PipelineContext) -> StageResult:
        engine = AlertEngine(
            config_dir=ctx.config_dir,
            db_path=ctx.db_path,
        )
        result = engine.run()
        return StageResult(
            status="success" if not result.get("errors") else "partial",
            output={"alert_result": result},
            archive=False,
        )

    def _reporting(ctx: PipelineContext) -> StageResult:
        generator = ReportGenerator(
            db_path=ctx.db_path,
            output_dir=ctx.params.get("report_output_dir"),
        )
        result = generator.run()
        return StageResult(
            status="success" if result.get("status") == "success" else "partial",
            output={"report_result": result},
            archive=False,
        )

    return {
        "collection": _collection,
        "extraction": _extraction,
        "evaluation": _evaluation,
        "alerting": _alerting,
        "reporting": _reporting,
    }
