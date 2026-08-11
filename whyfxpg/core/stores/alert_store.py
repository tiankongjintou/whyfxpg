"""Auto-split store module."""

import sqlite3
import uuid
from collections.abc import Sequence
from datetime import datetime

from whyfxpg.core.stores.unit_of_work import BaseStore


class AlertStore(BaseStore):
    """预警记录 store，负责 alert_records 的读写。"""

    def find_existing(
        self,
        rule_id: str,
        object_type: str,
        object_value: str,
        statuses: Sequence[str] = ("pending", "confirmed"),
    ) -> int:
        """检查是否已存在相同且未关闭的预警。"""
        cursor = self.uow.connection.cursor()
        placeholders = ",".join(["?"] * len(statuses))
        cursor.execute(
            f"""
            SELECT COUNT(*) FROM alert_records
            WHERE rule_id = ? AND object_type = ? AND object_value = ?
              AND status IN ({placeholders})
            """,
            (rule_id, object_type, object_value) + tuple(statuses),
        )
        return cursor.fetchone()[0]

    def insert_alert(
        self,
        rule_id: str,
        rule_name: str,
        object_type: str,
        object_value: str,
        severity: str,
        triggered_value: str,
        description: str,
        status: str = "pending",
        explanation_json: str | None = None,
    ) -> None:
        """插入一条预警记录。"""
        cursor = self.uow.connection.cursor()
        cursor.execute(
            """
            INSERT INTO alert_records (alert_id, rule_id, rule_name, triggered_at, object_type, object_value,
                                       severity, triggered_value, description, status, explanation_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                rule_id,
                rule_name,
                datetime.now().isoformat(),  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
                object_type,
                object_value,
                severity,
                triggered_value,
                description,
                status,
                explanation_json,
            ),
        )

    def count_events_by_dimension(
        self,
        dimension: str,
        since: str,
        threshold: int,
    ) -> list[sqlite3.Row]:
        """按维度统计指定时间窗口内事件数 >= threshold 的维度值。"""
        cursor = self.uow.connection.cursor()
        cursor.execute(
            f"""
            SELECT {dimension}, COUNT(*) as cnt
            FROM risk_events
            WHERE publish_date >= ? AND {dimension} IS NOT NULL AND {dimension} != 'unknown'
            GROUP BY {dimension}
            HAVING COUNT(*) >= ?
            """,
            (since, threshold),
        )
        return cursor.fetchall()

    def fetch_risk_level_changes(
        self,
        since: str,
        levels: Sequence[str],
    ) -> list[sqlite3.Row]:
        """查询产品风险汇总中风险等级上升为指定级别的记录。"""
        cursor = self.uow.connection.cursor()
        placeholders = ",".join(["?"] * len(levels))
        cursor.execute(
            f"""
            SELECT product_id, latest_rs_level, latest_total_score
            FROM product_risk_summary
            WHERE updated_at >= ?
              AND latest_rs_level IN ({placeholders})
            """,
            (since,) + tuple(levels),
        )
        return cursor.fetchall()

    def fetch_high_severity_events(
        self,
        values: Sequence[str],
        rule_id: str,
    ) -> list[sqlite3.Row]:
        """查询严重度在给定列表且尚未被该规则预警过的事件。"""
        cursor = self.uow.connection.cursor()
        placeholders = ",".join(["?"] * len(values))
        cursor.execute(
            f"""
            SELECT event_id, severity_level, title
            FROM risk_events
            WHERE severity_level IN ({placeholders})
              AND event_id NOT IN (
                  SELECT object_value FROM alert_records WHERE rule_id = ? AND object_type = 'event'
              )
            """,
            tuple(values) + (rule_id,),
        )
        return cursor.fetchall()

    def fetch_novel_patterns(
        self,
        group_by: str,
        dimension: str,
        since: str,
    ) -> list[sqlite3.Row]:
        """查询在时间窗口内首次出现的 group_by + dimension 组合。"""
        cursor = self.uow.connection.cursor()
        cursor.execute(
            f"""
            SELECT {group_by}, {dimension}
            FROM risk_events
            WHERE publish_date >= ?
            GROUP BY {group_by}, {dimension}
            """,
            (since,),
        )
        return cursor.fetchall()
