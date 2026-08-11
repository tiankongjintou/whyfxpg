"""In-memory telemetry adapter for tests and local observability."""

from dataclasses import dataclass, field
from typing import Any

from whyfxpg.ports.telemetry import (
    AdapterCallRecord,
    HealthSnapshot,
    RunRecord,
    TelemetryPort,
)


@dataclass
class InMemoryTelemetryAdapter(TelemetryPort):
    """Records all telemetry events in memory."""

    runs: list[RunRecord] = field(default_factory=list)
    adapter_calls: list[AdapterCallRecord] = field(default_factory=list)
    health_snapshots: list[HealthSnapshot] = field(default_factory=list)

    def record_run(self, record: RunRecord) -> None:
        self.runs.append(record)

    def record_adapter_call(self, record: AdapterCallRecord) -> None:
        self.adapter_calls.append(record)

    def record_health_snapshot(self, snapshot: HealthSnapshot) -> None:
        self.health_snapshots.append(snapshot)

    def snapshot(self) -> dict[str, Any]:
        return {
            "runs": [
                {
                    "run_id": r.run_id,
                    "pipeline_name": r.pipeline_name,
                    "duration_ms": r.duration_ms,
                    "status": r.status,
                    "stage_results": r.stage_results,
                    "recorded_at": r.recorded_at,
                }
                for r in self.runs
            ],
            "adapter_calls": [
                {
                    "adapter_name": c.adapter_name,
                    "method": c.method,
                    "duration_ms": c.duration_ms,
                    "success": c.success,
                    "recorded_at": c.recorded_at,
                }
                for c in self.adapter_calls
            ],
            "health_snapshots": [
                {
                    "service_name": h.service_name,
                    "status": h.status,
                    "details": h.details,
                    "recorded_at": h.recorded_at,
                }
                for h in self.health_snapshots
            ],
        }
