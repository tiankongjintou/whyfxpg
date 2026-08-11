"""In-memory configuration store adapter for tests and sandbox."""


import builtins

from whyfxpg.ports.config_store import ConfigRecord, ConfigStorePort, ConfigVersion


class InMemoryConfigStoreAdapter(ConfigStorePort):
    """Stores configuration objects in memory. Useful for unit tests and demos."""

    def __init__(self, data: dict[str, dict[str, ConfigRecord]] | None = None):
        self._records: dict[str, dict[str, ConfigRecord]] = data or {}
        self._versions: dict[str, dict[str, list[ConfigVersion]]] = {}

    def list(self, object_type: str) -> list[ConfigRecord]:
        return list(self._records.get(object_type, {}).values())

    def read(self, object_type: str, object_id: str) -> ConfigRecord | None:
        return self._records.get(object_type, {}).get(object_id)

    def write(self, record: ConfigRecord) -> ConfigRecord:
        self._records.setdefault(record.object_type, {})[record.object_id] = record
        snapshot = ConfigVersion(
            version_id=record.version_id,
            object_type=record.object_type,
            object_id=record.object_id,
            status=record.status,
            payload=record.payload,
            created_at=record.created_at,
            created_by=record.created_by,
        )
        self._versions.setdefault(record.object_type, {}).setdefault(record.object_id, []).insert(0, snapshot)
        return record

    def delete(self, object_type: str, object_id: str) -> None:
        self._records.get(object_type, {}).pop(object_id, None)

    def versions(self, object_type: str, object_id: str) -> builtins.list[ConfigVersion]:
        return list(self._versions.get(object_type, {}).get(object_id, []))
