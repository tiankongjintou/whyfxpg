"""Telemetry service: thin convenience wrapper around TelemetryPort."""

from typing import Any

from whyfxpg.ports.telemetry import (
    AdapterCallRecord,
    HealthSnapshot,
    NullTelemetryPort,
    RunRecord,
    TelemetryPort,
)


class TelemetryService:
    """Records observability events through a TelemetryPort."""

    def __init__(self, port: TelemetryPort | None = None):
        self._port = port or NullTelemetryPort()

    def record_run(
        self,
        run_id: str,
        pipeline_name: str,
        duration_ms: float,
        status: str,
        stage_results: list[dict[str, Any]] | None = None,
    ) -> None:
        self._port.record_run(
            RunRecord(
                run_id=run_id,
                pipeline_name=pipeline_name,
                duration_ms=duration_ms,
                status=status,
                stage_results=stage_results or [],
            )
        )

    def record_adapter_call(
        self,
        adapter_name: str,
        method: str,
        duration_ms: float,
        success: bool,
    ) -> None:
        self._port.record_adapter_call(
            AdapterCallRecord(
                adapter_name=adapter_name,
                method=method,
                duration_ms=duration_ms,
                success=success,
            )
        )

    def record_health_snapshot(
        self,
        service_name: str,
        status: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        self._port.record_health_snapshot(
            HealthSnapshot(
                service_name=service_name,
                status=status,
                details=details or {},
            )
        )

    def snapshot(self) -> dict[str, Any]:
        return self._port.snapshot()
