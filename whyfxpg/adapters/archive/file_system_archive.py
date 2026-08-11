"""File-system archive adapter.

Stores pipeline artifacts under ``whyfxpg/archive/<run_id>/<artifact_type>/<name>.json``.
This keeps large binary/structured outputs out of the SQLite database while
preserving a stable directory layout for debugging and compliance.
"""

import json
from pathlib import Path
from typing import Any

from whyfxpg.ports.archive import ArchiveHandle, ArchivePort


class FileSystemArchiveAdapter(ArchivePort):
    """Archive adapter that writes artifacts to a directory tree."""

    def __init__(self, root_dir: str):
        self.root = Path(root_dir)
        self.root.mkdir(parents=True, exist_ok=True)

    def archive(
        self,
        run_id: str,
        artifact_type: str,
        name: str,
        payload: dict[str, Any],
    ) -> ArchiveHandle:
        safe_run = Path(str(run_id)).name
        safe_type = Path(str(artifact_type)).name
        safe_name = Path(str(name)).name
        dir_path = self.root / safe_run / safe_type
        dir_path.mkdir(parents=True, exist_ok=True)
        file_path = dir_path / f"{safe_name}.json"
        file_path.write_text(
            json.dumps(payload, ensure_ascii=False, default=str, indent=2),
            encoding="utf-8",
        )
        handle = f"{safe_run}/{safe_type}/{safe_name}.json"
        return ArchiveHandle(handle=handle, artifact_type=artifact_type, path=str(file_path))

    def retrieve(self, handle: ArchiveHandle) -> dict[str, Any]:
        file_path = self.root / handle.handle
        return json.loads(file_path.read_text(encoding="utf-8"))

    def list_run_artifacts(self, run_id: str) -> dict[str, ArchiveHandle]:
        run_dir = self.root / run_id
        if not run_dir.exists():
            return {}
        result: dict[str, ArchiveHandle] = {}
        for path in run_dir.rglob("*.json"):
            relative = path.relative_to(self.root)
            parts = relative.parts
            artifact_type = parts[1] if len(parts) > 1 else "unknown"
            handle = ArchiveHandle(
                handle=str(relative).replace("\\", "/"),
                artifact_type=artifact_type,
                path=str(path),
            )
            result[handle.handle] = handle
        return result
