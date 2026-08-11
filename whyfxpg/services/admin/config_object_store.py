"""Database registry for configuration object versions (Admin CRUD seam)."""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from whyfxpg.core.db import get_db_connection
from whyfxpg.ports.config_store import ConfigRecord, ConfigVersion


class ConfigObjectStore:
    """Records published/rolled-back configuration versions in SQLite.

    This is intentionally separate from the file store adapter: the adapter
    owns the durable YAML files and their snapshot directory, while this store
    owns the version registry for quick queries and audit.
    """

    def __init__(
        self,
        conn: sqlite3.Connection | None = None,
        db_path: Path | None = None,
    ):
        self._conn = conn
        self._db_path: str | None = str(db_path) if db_path else None
        self._owns_connection = conn is None

    def _connection(self) -> sqlite3.Connection:
        if self._conn is not None:
            return self._conn
        return get_db_connection(self._db_path)

    def _close(self, conn: sqlite3.Connection) -> None:
        if self._owns_connection:
            conn.close()

    def record_version(self, record: ConfigRecord) -> None:
        conn = self._connection()
        try:
            conn.execute(
                """
                INSERT INTO config_objects (
                    object_type, object_id, version_id, status, payload,
                    created_at, created_by, published_at, published_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.object_type,
                    record.object_id,
                    record.version_id,
                    record.status,
                    json.dumps(record.payload, ensure_ascii=False, sort_keys=True),
                    record.created_at.isoformat(),
                    record.created_by,
                    record.published_at.isoformat() if record.published_at else None,
                    record.published_by,
                ),
            )
            if self._owns_connection:
                conn.commit()
        finally:
            self._close(conn)

    def list_versions(self, object_type: str, object_id: str) -> list[ConfigVersion]:
        conn = self._connection()
        try:
            rows = conn.execute(
                """
                SELECT version_id, status, payload, created_at, created_by
                FROM config_objects
                WHERE object_type = ? AND object_id = ?
                ORDER BY created_at DESC
                """,
                (object_type, object_id),
            ).fetchall()
        finally:
            self._close(conn)

        versions: list[ConfigVersion] = []
        for row in rows:
            versions.append(
                ConfigVersion(
                    version_id=row[0],
                    object_type=object_type,
                    object_id=object_id,
                    status=row[1],
                    payload=json.loads(row[2]) if row[2] else {},
                    created_at=datetime.fromisoformat(row[3]),
                    created_by=row[4],
                )
            )
        return versions

    def get_version(self, version_id: str) -> ConfigVersion | None:
        conn = self._connection()
        try:
            row = conn.execute(
                """
                SELECT object_type, object_id, status, payload, created_at, created_by
                FROM config_objects
                WHERE version_id = ?
                LIMIT 1
                """,
                (version_id,),
            ).fetchone()
        finally:
            self._close(conn)
        if not row:
            return None
        return ConfigVersion(
            version_id=version_id,
            object_type=row[0],
            object_id=row[1],
            status=row[2],
            payload=json.loads(row[3]) if row[3] else {},
            created_at=datetime.fromisoformat(row[4]),
            created_by=row[5],
        )
