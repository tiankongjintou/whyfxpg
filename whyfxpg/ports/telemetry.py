"""Telemetry port for pipeline observability.

Records pipeline run timings, adapter call counts/durations, and health snapshots
without coupling to any specific backend (in-memory, logging, metrics, etc.).
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol


@dataclass
class RunRecord:
    """One pipeline run observation."""

    run_id: str
    pipeline_name: str
    duration_ms: float
    status: str
    stage_results: list[dict[str, Any]] = field(default_factory=list)
    recorded_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass
class AdapterCallRecord:
    """One adapter method invocation."""

    adapter_name: str
    method: str
    duration_ms: float
    success: bool
    recorded_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass
class HealthSnapshot:
    """Health snapshot for a service or the whole system."""

    service_name: str
    status: str
    details: dict[str, Any] = field(default_factory=dict)
    recorded_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class TelemetryPort(Protocol):
    """Outbound port for observability data."""

    def record_run(self, record: RunRecord) -> None:
        ...

    def record_adapter_call(self, record: AdapterCallRecord) -> None:
        ...

    def record_health_snapshot(self, snapshot: HealthSnapshot) -> None:
        ...

    def snapshot(self) -> dict[str, Any]:
        ...


class NullTelemetryPort:
    """No-op telemetry port. Keeps callers simple when telemetry is disabled."""

    def record_run(self, record: RunRecord) -> None:
        pass

    def record_adapter_call(self, record: AdapterCallRecord) -> None:
        pass

    def record_health_snapshot(self, snapshot: HealthSnapshot) -> None:
        pass

    def snapshot(self) -> dict[str, Any]:
        return {
            "runs": [],
            "adapter_calls": [],
            "health_snapshots": [],
        }
