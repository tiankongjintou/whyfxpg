"""File-based configuration store adapter.

Maps configuration object types to YAML files in the config directory and
keeps published snapshots under `config/objects/<type>/<id>/versions/`.

Supported object types:
  - source            -> sources.yaml (sources dict)
  - rule              -> alert_rules.yaml (rules list)
  - model             -> risk_model.yaml (single model dict)
  - dimension         -> dimensions.yaml (dimensions list)
  - taxonomy          -> taxonomies.yaml (taxonomies list)
  - dashboard_template -> dashboard_templates.yaml (dashboards list)
"""

import builtins
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from whyfxpg.core.config_loader import DEFAULT_CONFIG_DIR, load_yaml
from whyfxpg.ports.config_store import ConfigRecord, ConfigStorePort, ConfigVersion

_FILE_MAP: dict[str, str] = {
    "source": "sources.yaml",
    "rule": "alert_rules.yaml",
    "model": "risk_model.yaml",
    "dimension": "dimensions.yaml",
    "taxonomy": "taxonomies.yaml",
    "dashboard_template": "dashboard_templates.yaml",
}

_LIST_KEYS: dict[str, str] = {
    "rule": "rules",
    "dimension": "dimensions",
    "taxonomy": "taxonomies",
    "dashboard_template": "dashboards",
}

_ID_FIELDS: dict[str, str] = {
    "rule": "rule_id",
    "dimension": "dimension_id",
    "taxonomy": "taxonomy_id",
    "dashboard_template": "dashboard_id",
}


def _version_dir(config_dir: Path, object_type: str, object_id: str) -> Path:
    return config_dir / "objects" / object_type / object_id / "versions"


def _safe_id(value: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in value)


class FileConfigStoreAdapter(ConfigStorePort):
    """YAML file-backed configuration store."""

    def __init__(self, config_dir: Path | None = None):
        self.config_dir = Path(config_dir) if config_dir else DEFAULT_CONFIG_DIR

    def _file_path(self, object_type: str) -> Path:
        filename = _FILE_MAP.get(object_type)
        if not filename:
            raise ValueError(f"Unsupported object type: {object_type}")
        return self.config_dir / filename

    def _read_file(self, object_type: str) -> dict[str, Any]:
        path = self._file_path(object_type)
        if not path.exists():
            return {}
        return load_yaml(path)

    def _write_file(self, object_type: str, data: dict[str, Any]) -> None:
        path = self._file_path(object_type)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)

    def _extract_records(self, object_type: str, data: dict[str, Any]) -> list[ConfigRecord]:
        records: list[ConfigRecord] = []
        if object_type == "source":
            for source_id, payload in (data.get("sources") or {}).items():
                records.append(self._record(object_type, str(source_id), payload))
        elif object_type in _LIST_KEYS:
            key = _LIST_KEYS[object_type]
            id_field = _ID_FIELDS[object_type]
            for item in (data.get(key) or []):
                if not isinstance(item, dict):
                    continue
                obj_id = str(item.get(id_field, ""))
                if not obj_id:
                    continue
                records.append(self._record(object_type, obj_id, item))
        elif object_type == "model" and isinstance(data, dict) and data:
            obj_id = str(data.get("model_name", "default"))
            records.append(self._record(object_type, obj_id, data))
        return records

    def _record(
        self,
        object_type: str,
        object_id: str,
        payload: dict[str, Any],
        version_id: str = "active",
        status: str = "published",
        created_at: datetime | None = None,
        created_by: str = "system",
    ) -> ConfigRecord:
        return ConfigRecord(
            object_type=object_type,
            object_id=object_id,
            status=status,
            payload=payload,
            version_id=version_id,
            created_at=created_at or datetime.now(),  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
            created_by=created_by,
            published_at=datetime.now() if status == "published" else None,  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
            published_by=created_by if status == "published" else None,
        )

    def _update_payload(self, object_type: str, data: dict[str, Any], record: ConfigRecord) -> dict[str, Any]:
        data = dict(data) if data else {}
        if object_type == "source":
            data.setdefault("sources", {})
            data["sources"][record.object_id] = dict(record.payload)
            # Ensure the source_id key is also in the payload for display consistency
            data["sources"][record.object_id]["source_id"] = record.object_id
        elif object_type in _LIST_KEYS:
            key = _LIST_KEYS[object_type]
            id_field = _ID_FIELDS[object_type]
            items = list(data.get(key) or [])
            found = False
            for i, item in enumerate(items):
                if isinstance(item, dict) and str(item.get(id_field, "")) == record.object_id:
                    items[i] = dict(record.payload)
                    items[i][id_field] = record.object_id
                    found = True
                    break
            if not found:
                new_item = dict(record.payload)
                new_item[id_field] = record.object_id
                items.append(new_item)
            data[key] = items
        elif object_type == "model":
            data = dict(record.payload)
            data["model_name"] = record.object_id
        return data

    def _remove_payload(self, object_type: str, data: dict[str, Any], object_id: str) -> dict[str, Any]:
        data = dict(data) if data else {}
        if object_type == "source":
            data.setdefault("sources", {}).pop(object_id, None)
        elif object_type in _LIST_KEYS:
            key = _LIST_KEYS[object_type]
            id_field = _ID_FIELDS[object_type]
            data[key] = [
                item for item in (data.get(key) or [])
                if not (isinstance(item, dict) and str(item.get(id_field, "")) == object_id)
            ]
        elif object_type == "model":
            data = {}
        return data

    def _snapshot_version(self, record: ConfigRecord) -> None:
        if not record.version_id or record.version_id == "active":
            return
        vdir = _version_dir(self.config_dir, record.object_type, record.object_id)
        vdir.mkdir(parents=True, exist_ok=True)
        snapshot = {
            "version_id": record.version_id,
            "object_type": record.object_type,
            "object_id": record.object_id,
            "status": record.status,
            "created_at": record.created_at.isoformat(),
            "created_by": record.created_by,
            "published_at": record.published_at.isoformat() if record.published_at else None,
            "published_by": record.published_by,
            "payload": record.payload,
        }
        vpath = vdir / f"{_safe_id(record.version_id)}.yaml"
        with open(vpath, "w", encoding="utf-8") as f:
            yaml.safe_dump(snapshot, f, allow_unicode=True, sort_keys=False)

    def list(self, object_type: str) -> list[ConfigRecord]:
        data = self._read_file(object_type)
        return self._extract_records(object_type, data)

    def read(self, object_type: str, object_id: str) -> ConfigRecord | None:
        for record in self.list(object_type):
            if record.object_id == object_id:
                return record
        return None

    def write(self, record: ConfigRecord) -> ConfigRecord:
        data = self._read_file(record.object_type)
        data = self._update_payload(record.object_type, data, record)
        self._write_file(record.object_type, data)
        self._snapshot_version(record)
        return record

    def delete(self, object_type: str, object_id: str) -> None:
        data = self._read_file(object_type)
        data = self._remove_payload(object_type, data, object_id)
        self._write_file(object_type, data)

    def versions(self, object_type: str, object_id: str) -> builtins.list[ConfigVersion]:
        vdir = _version_dir(self.config_dir, object_type, object_id)
        versions: list[ConfigVersion] = []
        if not vdir.exists():
            return versions
        for vpath in sorted(vdir.glob("*.yaml"), reverse=True):
            try:
                snapshot = load_yaml(vpath)
                versions.append(
                    ConfigVersion(
                        version_id=str(snapshot.get("version_id", vpath.stem)),
                        object_type=str(snapshot.get("object_type", object_type)),
                        object_id=str(snapshot.get("object_id", object_id)),
                        status=str(snapshot.get("status", "published")),
                        payload=snapshot.get("payload") or {},
                        created_at=datetime.fromisoformat(str(snapshot.get("created_at"))),
                        created_by=str(snapshot.get("created_by", "system")),
                    )
                )
            except Exception:  # noqa: BLE001, S112 — 刻意用法(见 TD03)
                # Skip corrupted snapshot files
                continue
        return sorted(versions, key=lambda v: v.created_at, reverse=True)
