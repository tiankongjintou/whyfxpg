"""Pipeline run and audit-log persistence."""

import uuid
from datetime import datetime
from typing import Any

from whyfxpg.core.stores.unit_of_work import BaseStore


class PipelineRunStore(BaseStore):
    """Store for pipeline_runs / pipeline_stage_runs tables."""

    def create_run(self, run_id: str, pipeline_name: str) -> None:
        cursor = self.uow.connection.cursor()
        cursor.execute(
            """
            INSERT INTO pipeline_runs (run_id, pipeline_name, started_at, status)
            VALUES (?, ?, ?, ?)
            """,
            (run_id, pipeline_name, datetime.now().isoformat(), "running"),  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
        )

    def start_stage(
        self,
        run_id: str,
        stage_name: str,
        stage_order: int,
        input_handle: str | None = None,
    ) -> str:
        stage_run_id = str(uuid.uuid4())
        cursor = self.uow.connection.cursor()
        cursor.execute(
            """
            INSERT INTO pipeline_stage_runs (
                stage_run_id, run_id, stage_name, stage_order,
                started_at, status, input_artifact_handle
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                stage_run_id,
                run_id,
                stage_name,
                stage_order,
                datetime.now().isoformat(),  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
                "running",
                input_handle,
            ),
        )
        return stage_run_id

    def complete_stage(
        self,
        stage_run_id: str,
        status: str,
        output_handle: str | None = None,
        error_message: str | None = None,
    ) -> None:
        cursor = self.uow.connection.cursor()
        cursor.execute(
            """
            UPDATE pipeline_stage_runs
            SET completed_at = ?, status = ?, output_artifact_handle = ?, error_message = ?
            WHERE stage_run_id = ?
            """,
            (
                datetime.now().isoformat(),  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
                status,
                output_handle,
                error_message or "",
                stage_run_id,
            ),
        )

    def complete_run(
        self,
        run_id: str,
        status: str,
        error_message: str | None = None,
        archived_path: str | None = None,
    ) -> None:
        cursor = self.uow.connection.cursor()
        cursor.execute(
            """
            UPDATE pipeline_runs
            SET completed_at = ?, status = ?, error_message = ?, archived_path = ?
            WHERE run_id = ?
            """,
            (
                datetime.now().isoformat(),  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
                status,
                error_message or "",
                archived_path or "",
                run_id,
            ),
        )

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        cursor = self.uow.connection.cursor()
        cursor.execute(
            "SELECT * FROM pipeline_runs WHERE run_id = ?",
            (run_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def list_stage_runs(self, run_id: str) -> list[dict[str, Any]]:
        cursor = self.uow.connection.cursor()
        cursor.execute(
            """
            SELECT * FROM pipeline_stage_runs
            WHERE run_id = ?
            ORDER BY stage_order, started_at
            """,
            (run_id,),
        )
        return [dict(r) for r in cursor.fetchall()]


class AuditLogStore(BaseStore):
    """Generic audit-log store for compliance and feedback tracing."""

    def write(
        self,
        actor: str,
        action: str,
        target_type: str,
        target_id: str,
        before_value: str | None = None,
        after_value: str | None = None,
        reason: str | None = None,
    ) -> str:
        audit_id = str(uuid.uuid4())
        cursor = self.uow.connection.cursor()
        cursor.execute(
            """
            INSERT INTO audit_log (
                audit_id, happened_at, actor, action,
                target_type, target_id, before_value, after_value, reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                audit_id,
                datetime.now().isoformat(),  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
                actor,
                action,
                target_type,
                target_id,
                before_value or "",
                after_value or "",
                reason or "",
            ),
        )
        return audit_id

    def list_for_target(self, target_type: str, target_id: str) -> list[dict[str, Any]]:
        cursor = self.uow.connection.cursor()
        cursor.execute(
            """
            SELECT * FROM audit_log
            WHERE target_type = ? AND target_id = ?
            ORDER BY happened_at DESC
            """,
            (target_type, target_id),
        )
        return [dict(r) for r in cursor.fetchall()]
