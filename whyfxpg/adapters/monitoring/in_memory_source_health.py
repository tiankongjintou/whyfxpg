"""In-memory source health adapter for tests and sandboxing."""

from typing import Any

from whyfxpg.ports.source_health import (
    Lineage,
    SourceHealth,
    SourceHealthPort,
)


class InMemorySourceHealthAdapter(SourceHealthPort):
    """Backs SourceHealthPort with dictionaries, no database required."""

    def __init__(
        self,
        sources: dict[str, dict[str, Any]] | None = None,
        lineages: dict[str, Lineage] | None = None,
    ):
        self.sources = sources or {}
        self.lineages = lineages or {}
        self.snapshots: list[SourceHealth] = []

    def list_sources(self) -> list[str]:
        return list(self.sources.keys())

    def latency(self, source_id: str) -> int | None:
        return self.sources.get(source_id, {}).get("latency_ms")

    def coverage(self, source_id: str) -> float:
        return self.sources.get(source_id, {}).get("coverage", 0.0)

    def error_rate(self, source_id: str, window: str = "24h") -> float:
        return self.sources.get(source_id, {}).get("error_rate", 0.0)

    def freshness(self, source_id: str) -> float:
        return self.sources.get(source_id, {}).get("freshness", 0.0)

    def health(self, source_id: str) -> SourceHealth:
        data = self.sources.get(source_id, {})
        return SourceHealth(
            source_id=source_id,
            status=data.get("status", "unknown"),
            health_score=data.get("health_score", 0.0),
            freshness_score=data.get("freshness", 0.0),
            latency_ms=data.get("latency_ms"),
            coverage_score=data.get("coverage", 0.0),
            error_rate=data.get("error_rate", 0.0),
            last_check_at=data.get("last_check_at"),
            details=data.get("details", {}),
        )

    def metrics(self, source_id: str, window: str) -> dict[str, Any]:
        data = self.sources.get(source_id, {})
        return {
            "source_id": source_id,
            "window": window,
            "latency_ms": data.get("latency_ms"),
            "coverage": data.get("coverage", 0.0),
            "error_rate": data.get("error_rate", 0.0),
            "freshness": data.get("freshness", 0.0),
            "last_check_at": data.get("last_check_at"),
        }

    def lineage(self, event_id: str) -> Lineage:
        return self.lineages.get(event_id, Lineage(event_id=event_id))

    def write_snapshot(self, health: SourceHealth) -> None:
        self.snapshots.append(health)
