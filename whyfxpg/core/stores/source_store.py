"""Auto-split store module."""

from datetime import datetime
from typing import Any

from whyfxpg.core.stores.unit_of_work import BaseStore


class MonitorSourceStore(BaseStore):
    """监控源状态 store，负责 monitor_sources / crawl_logs 的写入。"""

    def ensure_sources(self, sources: dict[str, Any]) -> None:
        """根据 sources.yaml 初始化 monitor_sources 表；已存在的 source_id 不覆盖。"""
        cursor = self.uow.connection.cursor()
        for source_id, cfg in sources.items():
            cursor.execute(
                "SELECT 1 FROM monitor_sources WHERE source_id = ?",
                (source_id,)
            )
            if cursor.fetchone():
                continue
            cursor.execute(
                """
                INSERT INTO monitor_sources (source_id, name, url, source_type, enabled, check_interval, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_id,
                    cfg.get("name", ""),
                    cfg.get("url", ""),
                    cfg.get("source_type", "web"),
                    1 if cfg.get("enabled", True) else 0,
                    cfg.get("check_interval", "1d"),
                    "ok",
                ),
            )

    def record_check(
        self,
        source_id: str,
        content_hash: str,
        status: str,
        error_msg: str | None = None,
        content_length: int | None = None,
    ) -> None:
        """更新 monitor_sources 的检查状态。"""
        cursor = self.uow.connection.cursor()
        cursor.execute(
            """
            UPDATE monitor_sources
            SET last_check_at = ?,
                last_hash = ?,
                status = ?,
                error_msg = ?,
                last_content_length = COALESCE(?, last_content_length)
            WHERE source_id = ?
            """,
            (
                datetime.now().isoformat(),  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
                content_hash,
                status,
                error_msg,
                content_length,
                source_id,
            ),
        )

    def record_crawl_log(
        self,
        source_id: str,
        status: str,
        pages_fetched: int,
        pages_new: int,
        error_msg: str | None = None,
        latency_ms: int | None = None,
        content_length: int | None = None,
        request_started_at: str | None = None,
    ) -> None:
        """写入一次采集日志。"""
        cursor = self.uow.connection.cursor()
        cursor.execute(
            """
            INSERT INTO crawl_logs (
                source_id, run_at, status, pages_fetched, pages_new, error_msg,
                request_started_at, latency_ms, content_length
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source_id,
                datetime.now().isoformat(),  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
                status,
                pages_fetched,
                pages_new,
                error_msg or "",
                request_started_at,
                latency_ms,
                content_length,
            ),
        )
