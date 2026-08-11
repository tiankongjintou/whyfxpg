"""Archive port: long-term artifact storage seam.

The pipeline orchestrator archives stage outputs through this port so that
runs remain reproducible without keeping everything in the database.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ArchiveHandle:
    """A reference to an archived artifact."""

    handle: str
    artifact_type: str
    path: str | None = None


class ArchivePort(ABC):
    """Abstract archive for pipeline artifacts.

    Implementations may write to local disk, object storage, or keep payloads
    in memory for tests.
    """

    @abstractmethod
    def archive(
        self,
        run_id: str,
        artifact_type: str,
        name: str,
        payload: dict[str, Any],
    ) -> ArchiveHandle:
        """Persist an artifact and return a handle for later retrieval."""
        ...

    @abstractmethod
    def retrieve(self, handle: ArchiveHandle) -> dict[str, Any]:
        """Load the artifact referenced by *handle*."""
        ...

    @abstractmethod
    def list_run_artifacts(self, run_id: str) -> dict[str, ArchiveHandle]:
        """Return all artifact handles produced by a run."""
        ...
