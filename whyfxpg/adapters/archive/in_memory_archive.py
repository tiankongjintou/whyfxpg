"""In-memory archive adapter for tests and ephemeral pipelines."""

import json
from typing import Any

from whyfxpg.ports.archive import ArchiveHandle, ArchivePort


class InMemoryArchiveAdapter(ArchivePort):
    """Archive adapter that keeps all payloads in memory."""

    def __init__(self, initial: dict[str, dict[str, Any]] | None = None):
        self._storage: dict[str, dict[str, Any]] = initial or {}

    def archive(
        self,
        run_id: str,
        artifact_type: str,
        name: str,
        payload: dict[str, Any],
    ) -> ArchiveHandle:
        handle = f"{run_id}/{artifact_type}/{name}.json"
        self._storage[handle] = payload
        return ArchiveHandle(handle=handle, artifact_type=artifact_type, path=None)

    def retrieve(self, handle: ArchiveHandle) -> dict[str, Any]:
        if handle.handle not in self._storage:
            raise KeyError(f"Artifact not found: {handle.handle}")
        return json.loads(json.dumps(self._storage[handle.handle], ensure_ascii=False, default=str))

    def list_run_artifacts(self, run_id: str) -> dict[str, ArchiveHandle]:
        prefix = f"{run_id}/"
        return {
            key: ArchiveHandle(handle=key, artifact_type=key.split("/")[1], path=None)
            for key in self._storage
            if key.startswith(prefix)
        }
