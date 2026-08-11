"""Auto-split store module."""

from datetime import datetime
from typing import Any

from whyfxpg.core.stores.unit_of_work import BaseStore


class RiskEventStore(BaseStore):
    """风险事件 store，负责 risk_events 的查询与评分更新。"""

    def fetch_pending(self) -> list[dict[str, Any]]:
        """获取待评分事件。"""
        cursor = self.uow.connection.cursor()
        cursor.execute(
            "SELECT * FROM risk_events WHERE ss_score IS NULL OR ps_score IS NULL ORDER BY extracted_at"
        )
        return [dict(r) for r in cursor.fetchall()]

    def count_history(
        self,
        since: str,
        country: str,
        manufacturer: str,
        product_category: str,
        hazard_type: str,
    ) -> int:
        """统计近一年内与事件多维度匹配且已评分的历史事件数。"""
        cursor = self.uow.connection.cursor()
        cursor.execute(
            """
            SELECT COUNT(*) FROM risk_events
            WHERE publish_date >= ?
              AND (country = ? OR manufacturer = ? OR product_category = ? OR hazard_type = ?)
              AND ss_score IS NOT NULL
            """,
            (since, country, manufacturer, product_category, hazard_type),
        )
        return cursor.fetchone()[0]

    def count_history_by_product(
        self,
        since: str,
        product_category: str,
        hazard_type: str,
    ) -> int:
        """按产品类别 + 危害类型统计近一年已评分事件数。"""
        cursor = self.uow.connection.cursor()
        cursor.execute(
            """
            SELECT COUNT(*) FROM risk_events
            WHERE publish_date >= ? AND product_category = ? AND hazard_type = ? AND ss_score IS NOT NULL
            """,
            (since, product_category, hazard_type),
        )
        return cursor.fetchone()[0]

    def update_scores(
        self,
        event_id: str,
        result: dict[str, Any],
        config_version: str,
        model_version: str,
    ) -> None:
        """将评分结果更新到 risk_events 表。"""
        cursor = self.uow.connection.cursor()
        cursor.execute(
            """
            UPDATE risk_events SET
                ss_score = ?,
                ps_score = ?,
                probability_level = ?,
                country_factor = ?,
                product_factor = ?,
                history_factor = ?,
                evidence_factor = ?,
                causal_factor = ?,
                total_score = ?,
                rs_level = ?,
                evaluated_at = ?,
                config_version = ?,
                model_version = ?
            WHERE event_id = ?
            """,
            (
                result["ss_score"],
                result["ps_score"],
                result["probability_level"],
                result["country_factor"],
                result["product_factor"],
                result["history_factor"],
                result["evidence_factor"],
                result.get("causal_factor", 1.0),
                result["total_score"],
                result["rs_level"],
                datetime.now().isoformat(),  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
                config_version,
                model_version,
                event_id,
            ),
        )

    def append_risk_reasoning(self, event_id: str, reasoning: str) -> None:
        """为事件追加 LLM 风险推理说明。"""
        cursor = self.uow.connection.cursor()
        cursor.execute(
            "UPDATE risk_events SET hazard_desc = hazard_desc || ? WHERE event_id = ?",
            (f"\n\n【AI风险分析】{reasoning}", event_id),
        )
