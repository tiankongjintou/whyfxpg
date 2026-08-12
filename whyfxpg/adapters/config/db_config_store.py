"""Database-backed configuration store adapter (P1b-04).

配置对象直接持久化到 ``config_objects`` 表（004 迁移），与
``FileConfigStoreAdapter``（YAML 文件后端）互为替代实现；SQL 均为跨
SQLite/PostgreSQL 通用写法，PG 端表结构由 alembic 0004 迁移保证。

约定（与 ConfigObjectStore 版本注册表一致）：
- 每个 (object_type, object_id) 的最新 version_id 记录为当前配置；
- ``delete`` 把当前版本 status 标记为 deprecated（保留历史，可审计）；
- ``write`` 每次写入新版本号（audit 语义：版本 + 来源 + 操作记录）。
"""

import builtins
import json
import sqlite3
from datetime import datetime
from pathlib import Path

from whyfxpg.core.db import get_db_connection
from whyfxpg.ports.config_store import ConfigRecord, ConfigStorePort, ConfigVersion


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计


class DbConfigStoreAdapter(ConfigStorePort):
    """``config_objects`` 表后端：当前配置 = 每个 object_id 的最新版本。"""

    def __init__(
        self,
        conn: sqlite3.Connection | None = None,
        db_path: str | Path | None = None,
    ):
        self._conn = conn
        self._db_path: str | None = str(db_path) if db_path else None
        self._owns_connection = conn is None

    def _connection(self) -> sqlite3.Connection:
        if self._conn is not None:
            return self._conn
        conn = get_db_connection(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def close(self) -> None:
        """关闭自建连接（调用方传入的连接由调用方负责）。"""
        if self._owns_connection and self._conn is not None:
            self._conn.close()
            self._conn = None

    # ── ConfigStorePort ──────────────────────────────────────────

    def list(self, object_type: str) -> list[ConfigRecord]:
        conn = self._connection()
        rows = conn.execute(
            """
            SELECT * FROM (
                SELECT c.*, ROW_NUMBER() OVER (
                    PARTITION BY c.object_id
                    ORDER BY c.created_at DESC, c.version_id DESC
                ) AS rn
                FROM config_objects c
                WHERE c.object_type = ?
            ) ranked
            WHERE rn = 1
            ORDER BY object_id
            """,
            (object_type,),
        ).fetchall()
        return [self._to_record(row) for row in rows]

    def read(self, object_type: str, object_id: str) -> ConfigRecord | None:
        conn = self._connection()
        row = conn.execute(
            """
            SELECT * FROM config_objects
            WHERE object_type = ? AND object_id = ?
            ORDER BY created_at DESC, version_id DESC LIMIT 1
            """,
            (object_type, object_id),
        ).fetchone()
        return self._to_record(row) if row else None

    def write(self, record: ConfigRecord) -> ConfigRecord:
        conn = self._connection()
        conn.execute(
            """
            INSERT INTO config_objects
                (object_type, object_id, version_id, status, payload,
                 created_at, created_by, published_at, published_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.object_type,
                record.object_id,
                record.version_id,
                record.status,
                json.dumps(record.payload, ensure_ascii=False),
                record.created_at.isoformat(timespec="seconds"),
                record.created_by,
                record.published_at.isoformat(timespec="seconds") if record.published_at else None,
                record.published_by,
            ),
        )
        conn.commit()
        return record

    def delete(self, object_type: str, object_id: str) -> None:
        """把当前版本标记 deprecated（历史保留，可审计）。"""
        conn = self._connection()
        conn.execute(
            """
            UPDATE config_objects SET status = 'deprecated'
            WHERE object_type = ? AND object_id = ?
              AND status != 'deprecated'
            """,
            (object_type, object_id),
        )
        conn.commit()

    def versions(self, object_type: str, object_id: str) -> builtins.list[ConfigVersion]:
        conn = self._connection()
        rows = conn.execute(
            """
            SELECT * FROM config_objects
            WHERE object_type = ? AND object_id = ?
            ORDER BY created_at DESC, version_id DESC
            """,
            (object_type, object_id),
        ).fetchall()
        return [
            ConfigVersion(
                version_id=row["version_id"],
                object_type=row["object_type"],
                object_id=row["object_id"],
                status=row["status"],
                payload=json.loads(row["payload"] or "{}"),
                created_at=datetime.fromisoformat(row["created_at"]),
                created_by=row["created_by"],
            )
            for row in rows
        ]

    # ── helpers ──────────────────────────────────────────────────

    @staticmethod
    def _to_record(row: sqlite3.Row) -> ConfigRecord:
        return ConfigRecord(
            object_type=row["object_type"],
            object_id=row["object_id"],
            status=row["status"],
            payload=json.loads(row["payload"] or "{}"),
            version_id=row["version_id"],
            created_at=datetime.fromisoformat(row["created_at"]),
            created_by=row["created_by"],
            published_at=(
                datetime.fromisoformat(row["published_at"]) if row["published_at"] else None
            ),
            published_by=row["published_by"],
        )


# ── YAML → DB 导入（P1b-04）────────────────────────────────────

def import_yaml_configs(
    store: ConfigStorePort,
    source_dir: str | Path,
    object_types: list[str] | None = None,
    created_by: str = "system",
) -> int:
    """把配置目录下的 YAML 文件导入 DB store，返回导入对象数。

    每个顶层 key 视为一个 object_id（如 risk_model.yaml 的顶层
    ``risk_model`` / 列表型文件的每项 rule_id/source_id 等），按现有
    FileConfigStoreAdapter 的分片约定处理：
    - 列表型（rules/sources 等）：每项一个 object
    - 字典型：每 key 一个 object
    """
    from whyfxpg.adapters.config.file_config_store import (
        _FILE_MAP,
        FileConfigStoreAdapter,
    )

    file_store = FileConfigStoreAdapter(Path(source_dir))
    targets = object_types or list(_FILE_MAP)
    imported = 0
    for object_type in targets:
        records = file_store.list(object_type)
        for record in records:
            existing = store.read(object_type, record.object_id)
            if existing is not None and existing.payload == record.payload:
                continue  # 幂等：内容未变则跳过
            imported_record = ConfigRecord(
                object_type=object_type,
                object_id=record.object_id,
                status="published",
                payload=record.payload,
                version_id=record.version_id,
                created_at=record.created_at,
                created_by=created_by,
                published_at=record.published_at or record.created_at,
                published_by=created_by,
            )
            store.write(imported_record)
            imported += 1
    return imported
