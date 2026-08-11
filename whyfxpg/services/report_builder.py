"""
Report builder: assemble a ReportModel from the database.

Separates data gathering + LLM summarization from file rendering.
"""
from typing import Any

from whyfxpg.core.db import get_db_connection
from whyfxpg.services.llm_service import LLMService
from whyfxpg.services.report_model import ReportModel


class ReportBuilder:
    """Build a domain report model from the database and LLM service."""

    def __init__(
        self,
        db_path: str | None = None,
        llm_service: LLMService | None = None,
    ):
        self.db_path = db_path
        self._llm_service = llm_service

    @property
    def llm_service(self) -> LLMService:
        if self._llm_service is None:
            self._llm_service = LLMService()
        return self._llm_service

    def build(
        self,
        report_type: str = "comprehensive",
        filters: dict[str, Any] | None = None,
    ) -> ReportModel:
        """Read DB, generate executive summary, return a ReportModel."""
        data = self._fetch_data()
        try:
            summary = self.llm_service.executive_summary(data)
        except Exception as e:  # pragma: no cover - defence in depth  # noqa: BLE001 — 外部调用/配置解析兜底,刻意吞异常
            summary = f"（执行摘要生成失败：{e}）"

        return ReportModel(
            total_events=data["total_events"],
            level_counts=data["level_counts"],
            top_events=data["top_events"],
            top_products=data["top_products"],
            top_countries=data["top_countries"],
            pending_alerts=data["pending_alerts"],
            executive_summary=summary,
            report_type=report_type,
            filters=filters,
        )

    def _fetch_data(self) -> dict[str, Any]:
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            "SELECT COUNT(*) FROM risk_events WHERE ss_score IS NOT NULL"
        )
        total_events = cursor.fetchone()[0]

        cursor.execute(
            "SELECT rs_level, COUNT(*) FROM risk_events WHERE ss_score IS NOT NULL GROUP BY rs_level"
        )
        level_counts = {row["rs_level"]: row[1] for row in cursor.fetchall()}

        cursor.execute(
            "SELECT * FROM risk_events WHERE ss_score IS NOT NULL ORDER BY total_score DESC LIMIT 20"
        )
        top_events = [dict(r) for r in cursor.fetchall()]

        cursor.execute(
            "SELECT * FROM product_risk_summary ORDER BY latest_total_score DESC LIMIT 20"
        )
        top_products = [dict(r) for r in cursor.fetchall()]

        cursor.execute(
            "SELECT * FROM country_risk_summary ORDER BY s_count DESC, event_count DESC LIMIT 20"
        )
        top_countries = [dict(r) for r in cursor.fetchall()]

        cursor.execute(
            "SELECT * FROM alert_records WHERE status = 'pending' ORDER BY triggered_at DESC"
        )
        pending_alerts = [dict(r) for r in cursor.fetchall()]

        conn.close()

        return {
            "total_events": total_events,
            "level_counts": level_counts,
            "top_events": top_events,
            "top_products": top_products,
            "top_countries": top_countries,
            "pending_alerts": pending_alerts,
        }
