"""通知中心服务。

把需要人工关注的系统事件（流水线失败/部分成功、数据源长期不可用等）
写入 ``notifications`` 表，供 Web UI 消息中心展示。

当前只实现持久化与查询，不直接发送邮件/钉钉；后续可无缝替换为
外部通知适配器，而不影响业务调用方。
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from whyfxpg.core.stores import UnitOfWork


@dataclass(frozen=True)
class Notification:
    """一条系统通知。"""

    notification_id: str
    notification_type: str
    severity: str
    title: str
    message: str | None
    source_type: str | None
    source_id: str | None
    created_at: str
    read_at: str | None
    dismissed_at: str | None


class NotificationService:
    """轻量级应用内通知服务。"""

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path

    def record(
        self,
        notification_type: str,
        title: str,
        message: str = "",
        severity: str = "info",
        source_type: str | None = None,
        source_id: str | None = None,
    ) -> str:
        """写入一条通知。返回 notification_id。"""
        notification_id = str(uuid.uuid4())
        created_at = datetime.now().isoformat()  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
        with UnitOfWork(self.db_path) as uow:
            cursor = uow.connection.cursor()
            cursor.execute(
                """
                INSERT INTO notifications
                (notification_id, notification_type, severity, title, message,
                 source_type, source_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    notification_id,
                    notification_type,
                    severity,
                    title,
                    message,
                    source_type,
                    source_id,
                    created_at,
                ),
            )
        return notification_id

    def list_unread(
        self,
        limit: int = 50,
        notification_type: str | None = None,
    ) -> list[Notification]:
        """查询未读且未忽略的通知。"""
        with UnitOfWork(self.db_path) as uow:
            cursor = uow.connection.cursor()
            sql = """
                SELECT notification_id, notification_type, severity, title, message,
                       source_type, source_id, created_at, read_at, dismissed_at
                FROM notifications
                WHERE read_at IS NULL AND dismissed_at IS NULL
            """
            params: list = []
            if notification_type:
                sql += " AND notification_type = ?"
                params.append(notification_type)
            sql += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            rows = cursor.execute(sql, params).fetchall()
        return [self._row_to_notification(r) for r in rows]

    def unread_count(self, notification_type: str | None = None) -> int:
        """未读通知数量。"""
        with UnitOfWork(self.db_path) as uow:
            cursor = uow.connection.cursor()
            sql = "SELECT COUNT(*) FROM notifications WHERE read_at IS NULL AND dismissed_at IS NULL"
            params: list = []
            if notification_type:
                sql += " AND notification_type = ?"
                params.append(notification_type)
            return cursor.execute(sql, params).fetchone()[0]

    def mark_read(self, notification_id: str) -> None:
        """标记已读。"""
        with UnitOfWork(self.db_path) as uow:
            uow.connection.execute(
                "UPDATE notifications SET read_at = ? WHERE notification_id = ?",
                (datetime.now().isoformat(), notification_id),  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
            )

    def mark_dismissed(self, notification_id: str) -> None:
        """标记忽略。"""
        with UnitOfWork(self.db_path) as uow:
            uow.connection.execute(
                "UPDATE notifications SET dismissed_at = ? WHERE notification_id = ?",
                (datetime.now().isoformat(), notification_id),  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
            )

    @staticmethod
    def _row_to_notification(row) -> Notification:
        return Notification(
            notification_id=row["notification_id"],
            notification_type=row["notification_type"],
            severity=row["severity"],
            title=row["title"],
            message=row["message"],
            source_type=row["source_type"],
            source_id=row["source_id"],
            created_at=row["created_at"],
            read_at=row["read_at"],
            dismissed_at=row["dismissed_at"],
        )
