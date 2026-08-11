"""Admin CRUD service for configuration objects."""

import builtins
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar

from whyfxpg.core.db import get_db_connection
from whyfxpg.migrations import MigrationRunner
from whyfxpg.ports.config_store import ConfigRecord, ConfigStorePort, ConfigVersion
from whyfxpg.services.admin.config_object_store import ConfigObjectStore

__all__ = [
    "ConfigDraft",
    "ConfigRecord",
    "ConfigVersion",
    "ConfigurationAdminService",
    "default_configuration_admin_service",
]


@dataclass
class ConfigDraft:
    object_type: str
    object_id: str
    payload: dict[str, Any] = field(default_factory=dict)
    created_by: str = "admin"


class ConfigurationAdminService:
    """Application service for creating, editing, publishing and rolling back
    configuration objects (sources, rules, models, dimensions, taxonomies).

    The durable storage is delegated to a ConfigStorePort; the version registry
    is kept in the SQLite `config_objects` table via ConfigObjectStore.
    """

    VALID_OBJECT_TYPES: ClassVar[set[str]] = {"source", "rule", "model", "dimension", "taxonomy"}

    def __init__(
        self,
        store: ConfigStorePort,
        db_conn: sqlite3.Connection | None = None,
        db_path: Path | None = None,
    ):
        self.store = store
        self._db_conn = db_conn
        self._db_path = db_path
        self._version_store: ConfigObjectStore | None = None
        if db_conn is not None:
            MigrationRunner(db_conn).run()
        elif db_path is not None:
            conn = get_db_connection(str(db_path))
            try:
                MigrationRunner(conn).run()
                conn.commit()
            finally:
                conn.close()
        else:
            # Default production path will be initialized lazily by ConfigObjectStore.
            pass

    def _get_version_store(self) -> ConfigObjectStore:
        if self._version_store is None:
            self._version_store = ConfigObjectStore(
                conn=self._db_conn,
                db_path=self._db_path,
            )
        return self._version_store

    def _new_version_id(self) -> str:
        return str(uuid.uuid4())[:8]

    def _now(self) -> datetime:
        return datetime.now()  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计

    def list(self, object_type: str) -> list[ConfigRecord]:
        if object_type not in self.VALID_OBJECT_TYPES:
            raise ValueError(f"Invalid object type: {object_type}")
        return self.store.list(object_type)

    def get(self, object_type: str, object_id: str) -> ConfigRecord | None:
        return self.store.read(object_type, object_id)

    def create(self, draft: ConfigDraft) -> ConfigRecord:
        if draft.object_type not in self.VALID_OBJECT_TYPES:
            raise ValueError(f"Invalid object type: {draft.object_type}")
        if not draft.object_id:
            raise ValueError("object_id is required")
        existing = self.store.read(draft.object_type, draft.object_id)
        if existing is not None:
            raise ValueError(f"{draft.object_type} '{draft.object_id}' already exists")
        record = ConfigRecord(
            object_type=draft.object_type,
            object_id=draft.object_id,
            status="draft",
            payload=draft.payload,
            version_id=self._new_version_id(),
            created_at=self._now(),
            created_by=draft.created_by,
        )
        return self.store.write(record)

    def update(
        self,
        object_type: str,
        object_id: str,
        payload: dict[str, Any],
        updated_by: str = "admin",
    ) -> ConfigRecord:
        existing = self.store.read(object_type, object_id)
        if existing is None:
            raise ValueError(f"{object_type} '{object_id}' not found")
        record = ConfigRecord(
            object_type=object_type,
            object_id=object_id,
            status="draft",
            payload=payload,
            version_id=self._new_version_id(),
            created_at=self._now(),
            created_by=updated_by,
        )
        return self.store.write(record)

    def delete(self, object_type: str, object_id: str) -> None:
        self.store.delete(object_type, object_id)

    def publish(
        self,
        object_type: str,
        object_id: str,
        published_by: str = "admin",
    ) -> ConfigRecord:
        existing = self.store.read(object_type, object_id)
        if existing is None:
            raise ValueError(f"{object_type} '{object_id}' not found")
        record = ConfigRecord(
            object_type=object_type,
            object_id=object_id,
            status="published",
            payload=existing.payload,
            version_id=self._new_version_id(),
            created_at=self._now(),
            created_by=published_by,
            published_at=self._now(),
            published_by=published_by,
        )
        persisted = self.store.write(record)
        self._get_version_store().record_version(persisted)
        return persisted

    def versions(self, object_type: str, object_id: str) -> builtins.list[ConfigVersion]:
        # Prefer file snapshots; merge with DB registry to ensure nothing is lost.
        file_versions = {v.version_id: v for v in self.store.versions(object_type, object_id)}
        db_versions = {v.version_id: v for v in self._get_version_store().list_versions(object_type, object_id)}
        merged = {**file_versions, **db_versions}
        return sorted(merged.values(), key=lambda v: v.created_at, reverse=True)

    def rollback(
        self,
        object_type: str,
        object_id: str,
        version_id: str,
        rolled_back_by: str = "admin",
    ) -> ConfigRecord:
        # Try the DB registry first, then the file snapshots.
        version = self._get_version_store().get_version(version_id)
        if version is None:
            for v in self.store.versions(object_type, object_id):
                if v.version_id == version_id:
                    version = v
                    break
        if version is None:
            raise ValueError(f"Version {version_id} not found")
        record = ConfigRecord(
            object_type=object_type,
            object_id=object_id,
            status="draft",
            payload=version.payload,
            version_id=self._new_version_id(),
            created_at=self._now(),
            created_by=rolled_back_by,
        )
        return self.store.write(record)


# ----------------------------------------------------------------------
# Production factory
# ----------------------------------------------------------------------
def default_configuration_admin_service() -> ConfigurationAdminService:
    """Return the production admin service wired to the file config store."""
    from whyfxpg.adapters.config.file_config_store import FileConfigStoreAdapter

    return ConfigurationAdminService(FileConfigStoreAdapter())
