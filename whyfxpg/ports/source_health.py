"""Source health monitoring port.

Abstracts how the system observes data sources: health, freshness, latency,
coverage, lineage, and historical metrics. Adapters can read from SQLite,
Prometheus, or in-memory fixtures.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Lineage:
    """Trace a risk event back to its source run."""

    event_id: str
    page_id: str | None = None
    source_id: str | None = None
    run_at: str | None = None
    url: str | None = None


@dataclass
class SourceHealth:
    """Computed health snapshot for a single source."""

    source_id: str
    status: str  # ok, degraded, stale, error, unknown
    health_score: float = 0.0
    freshness_score: float = 0.0
    latency_ms: int | None = None
    coverage_score: float = 0.0
    error_rate: float = 0.0
    last_check_at: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class AlertDraft:
    """A proposed alert when a source degrades."""

    source_id: str
    severity: str
    title: str
    description: str


class SourceHealthPort(ABC):
    """Port for source observability and lineage queries."""

    @abstractmethod
    def list_sources(self) -> list[str]:
        """Return all known source IDs."""
        ...

    @abstractmethod
    def health(self, source_id: str) -> SourceHealth:
        """Return a current health snapshot for the source."""
        ...

    @abstractmethod
    def freshness(self, source_id: str) -> float:
        """Return freshness score between 0 and 1."""
        ...

    @abstractmethod
    def latency(self, source_id: str) -> int | None:
        """Return latest/typical latency in milliseconds."""
        ...

    @abstractmethod
    def coverage(self, source_id: str) -> float:
        """Return coverage score between 0 and 1."""
        ...

    @abstractmethod
    def lineage(self, event_id: str) -> Lineage:
        """Trace an event back to its source page and run."""
        ...

    @abstractmethod
    def metrics(self, source_id: str, window: str) -> dict[str, Any]:
        """Return historical metrics for the source over a window."""
        ...

    @abstractmethod
    def write_snapshot(self, health: SourceHealth) -> None:
        """Persist a health snapshot for trend analysis."""
        ...
