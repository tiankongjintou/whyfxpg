"""Configuration storage port (Admin CRUD seam)."""

import builtins
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class ConfigRecord:
    """A single configuration object as seen by the admin service."""

    object_type: str
    object_id: str
    status: str  # draft | published | deprecated
    payload: dict[str, Any]
    version_id: str
    created_at: datetime
    created_by: str
    published_at: datetime | None = None
    published_by: str | None = None


@dataclass
class ConfigVersion:
    """Historical snapshot of a configuration object."""

    version_id: str
    object_type: str
    object_id: str
    status: str
    payload: dict[str, Any]
    created_at: datetime
    created_by: str


class ConfigStorePort(ABC):
    """Persistence seam for configuration objects.

    Implementations decide whether objects live in YAML files, a database,
    or memory. The admin service uses this port to create, read, update,
    delete and rollback objects without knowing the storage format.
    """

    @abstractmethod
    def list(self, object_type: str) -> list[ConfigRecord]:
        """Return all objects of the given type."""
        ...

    @abstractmethod
    def read(self, object_type: str, object_id: str) -> ConfigRecord | None:
        """Return a single object, or None if not found."""
        ...

    @abstractmethod
    def write(self, record: ConfigRecord) -> ConfigRecord:
        """Create or update an object and return the persisted record."""
        ...

    @abstractmethod
    def delete(self, object_type: str, object_id: str) -> None:
        """Remove an object."""
        ...

    @abstractmethod
    def versions(self, object_type: str, object_id: str) -> builtins.list[ConfigVersion]:
        """Return historical snapshots of the object, newest first."""
        ...
