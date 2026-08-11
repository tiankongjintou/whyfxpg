"""
配置版本管理模块 (M1)

功能：
- 计算各配置文件哈希
- 检测配置变化并记录新版本
- 将配置版本写入数据库
- 提供版本查询和回滚接口

输入：config目录下所有YAML文件
输出：config_versions表

Phase 1 T1 修改：
- 支持复用外部 sqlite3.Connection，避免在 RiskModel 主事务中打开第二条连接。
"""

import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from .config_loader import DEFAULT_CONFIG_DIR, ConfigLoader
from .db import get_db_connection

CONFIG_FILES = [
    "sources.yaml",
    "keywords.yaml",
    "extract_rules.yaml",
    "risk_model.yaml",
    "alert_rules.yaml",
    "version_history.yaml",
]


def file_hash(path: Path) -> str:
    """计算文件SHA256哈希"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


class ConfigVersionManager:
    """配置版本管理器"""

    def __init__(
        self,
        config_dir: str | None = None,
        db_path: str | None = None,
        conn: sqlite3.Connection | None = None,
    ):
        self.config_dir = Path(config_dir) if config_dir else DEFAULT_CONFIG_DIR
        self.db_path = db_path
        self._conn = conn
        self.loader = ConfigLoader(str(self.config_dir))

    @classmethod
    def from_connection(
        cls,
        conn: sqlite3.Connection,
        config_dir: str | None = None,
    ) -> "ConfigVersionManager":
        """基于已存在的数据库连接创建管理器，不管理连接生命周期。"""
        return cls(config_dir=config_dir, conn=conn)

    def _get_connection(self) -> tuple[sqlite3.Connection, bool]:
        """
        返回 (connection, own) 元组。
        own=True 表示由本管理器负责提交/回滚/关闭。
        """
        if self._conn is not None:
            return self._conn, False
        return get_db_connection(self.db_path), True

    def compute_hashes(self) -> dict[str, str]:
        """计算所有配置文件哈希"""
        hashes = {}
        for filename in CONFIG_FILES:
            path = self.config_dir / filename
            if path.exists():
                hashes[filename] = file_hash(path)
        return hashes

    def get_latest_db_version(self) -> dict[str, Any] | None:
        """获取数据库中最新配置版本"""
        conn, own = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM config_versions ORDER BY created_at DESC LIMIT 1"
            )
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None
        finally:
            if own:
                conn.close()

    def get_latest_history_version(self) -> str | None:
        """从version_history.yaml获取最新版本号"""
        history = self.loader.version_history
        if history and "history" in history and len(history["history"]) > 0:
            return history["history"][-1]["version"]
        return None

    def compare_hashes(self, current: dict[str, str], previous: dict[str, str]) -> bool:
        """比较哈希是否相同"""
        return current == previous

    def create_version(self, author: str = "system", description: str = "") -> dict[str, Any]:
        """
        检测配置变化，如果变化则创建新版本并写入数据库
        返回当前版本信息
        """
        current_hashes = self.compute_hashes()
        conn, own = self._get_connection()
        cursor = conn.cursor()
        try:
            # 在可能的共享连接内读取最新版本，避免跨连接竞态
            cursor.execute(
                "SELECT * FROM config_versions ORDER BY created_at DESC LIMIT 1"
            )
            row = cursor.fetchone()
            latest_db = dict(row) if row else None
            history_version = self.get_latest_history_version()

            version_id = history_version or "1.0"

            if latest_db and self.compare_hashes(current_hashes, json.loads(latest_db["file_hashes"])):
                return {
                    "version_id": latest_db["version_id"],
                    "created_at": latest_db["created_at"],
                    "changed": False,
                    "hashes": current_hashes,
                }

            # 配置发生变化，创建新版本
            if latest_db:
                parts = latest_db["version_id"].split(".")
                if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                    major, minor = int(parts[0]), int(parts[1])
                    version_id = f"{major}.{minor + 1}"
                else:
                    version_id = f"{latest_db['version_id']}.1"

            # 读取配置快照
            config_snapshot = {}
            for filename in CONFIG_FILES:
                path = self.config_dir / filename
                if path.exists():
                    config_snapshot[filename] = self.loader.load(filename)

            cursor.execute(
                """
                INSERT INTO config_versions (version_id, created_at, created_by, description, file_hashes, config_snapshot)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    version_id,
                    datetime.now().isoformat(),  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
                    author,
                    description,
                    json.dumps(current_hashes, ensure_ascii=False),
                    json.dumps(config_snapshot, ensure_ascii=False),
                ),
            )
            if own:
                conn.commit()
        except Exception:
            if own:
                conn.rollback()
            raise
        finally:
            if own:
                conn.close()

        return {
            "version_id": version_id,
            "changed": True,
            "hashes": current_hashes,
        }

    def list_versions(self) -> list[dict[str, Any]]:
        """列出所有配置版本"""
        conn, own = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM config_versions ORDER BY created_at DESC")
            rows = [dict(r) for r in cursor.fetchall()]
            return rows
        finally:
            if own:
                conn.close()

    def get_version(self, version_id: str) -> dict[str, Any] | None:
        """获取指定版本详情"""
        conn, own = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM config_versions WHERE version_id = ?", (version_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None
        finally:
            if own:
                conn.close()

    def run(self) -> dict[str, Any]:
        """模块主入口"""
        result = self.create_version(author="system", description="自动版本检测")
        return {
            "module": "config_version",
            "status": "success",
            "version_id": result["version_id"],
            "changed": result["changed"],
            "records_processed": 1,
            "records_created": 1 if result["changed"] else 0,
            "errors": [],
            "message": f"当前配置版本: {result['version_id']}",
        }


if __name__ == "__main__":
    from .db import init_db
    init_db()
    manager = ConfigVersionManager()
    print(manager.run())
