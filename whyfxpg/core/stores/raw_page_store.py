"""Auto-split store module."""

from datetime import datetime

from whyfxpg.core.stores.unit_of_work import BaseStore


class RawPageStore(BaseStore):
    """原始页面 store，负责 raw_pages 的查询与写入。"""

    def find_existing_by_hash(self, source_id: str, content_hash: str) -> str | None:
        """根据来源和 content_hash 查找已存在的 page_id。"""
        if not content_hash:
            return None
        cursor = self.uow.connection.cursor()
        cursor.execute(
            """
            SELECT page_id FROM raw_pages
            WHERE source_id = ? AND content_hash = ?
            ORDER BY fetched_at DESC
            LIMIT 1
            """,
            (source_id, content_hash),
        )
        row = cursor.fetchone()
        return row["page_id"] if row else None

    def insert_page(
        self,
        page_id: str,
        source_id: str,
        url: str,
        content_type: str,
        content_hash: str,
        content: bytes,
        status: str = "fetched",
    ) -> None:
        """插入一条 raw_pages 记录。"""
        cursor = self.uow.connection.cursor()
        cursor.execute(
            """
            INSERT INTO raw_pages (page_id, source_id, url, fetched_at, content_type, content_hash, raw_content, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                page_id,
                source_id,
                url,
                datetime.now().isoformat(),  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
                content_type,
                content_hash,
                content,
                status,
            ),
        )
