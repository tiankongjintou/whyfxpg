"""
Dashboard read model: database queries for the Web UI without Streamlit.

All returned objects are plain pandas DataFrames / dicts so they can be
unit-tested without importing streamlit.
"""
from datetime import datetime, timedelta
from typing import Any

import pandas as pd

from whyfxpg.core.db import get_db_connection


def _coerce_date_columns(df: pd.DataFrame, *columns: str) -> pd.DataFrame:
    """Normalize date columns to strings to avoid Arrow serialization errors."""
    for col in columns:
        if col in df.columns:
            df[col] = df[col].apply(lambda x: "" if x is None else str(x))
    return df


class DashboardReadModel:
    """Read-only access to dashboard data, with no UI or caching dependencies."""

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path

    def get_events(self, limit: int = 200) -> pd.DataFrame:
        """获取风险事件列表"""
        conn = get_db_connection(self.db_path)
        try:
            df = pd.read_sql(
                """
                SELECT event_id, publish_date, product_name, brand, model, country,
                       manufacturer, hazard_type, severity_level, rs_level, total_score,
                       causal_factor, extraction_confidence, review_status,
                       source_id, extracted_at, evaluated_at
                FROM risk_events
                WHERE ss_score IS NOT NULL
                ORDER BY total_score DESC
                LIMIT ?
                """,
                conn,
                params=(limit,),
            )
        finally:
            conn.close()
        return _coerce_date_columns(df, "publish_date")

    def get_alerts(self, limit: int = 200) -> pd.DataFrame:
        """获取预警记录"""
        conn = get_db_connection(self.db_path)
        try:
            df = pd.read_sql(
                """
                SELECT alert_id, rule_name, triggered_at, object_type, object_value,
                       severity, triggered_value, description, status
                FROM alert_records
                ORDER BY triggered_at DESC
                LIMIT ?
                """,
                conn,
                params=(limit,),
            )
        finally:
            conn.close()
        return df

    def get_summary(self) -> dict:
        """仪表盘汇总指标"""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT COUNT(*) FROM risk_events WHERE ss_score IS NOT NULL"
            )
            total = cursor.fetchone()[0]

            cursor.execute(
                """
                SELECT rs_level, COUNT(*) as cnt
                FROM risk_events WHERE ss_score IS NOT NULL
                GROUP BY rs_level
                """
            )
            level_dist = {r["rs_level"]: r["cnt"] for r in cursor.fetchall()}

            cursor.execute(
                """
                SELECT COUNT(*) FROM alert_records
                """
            )
            total_alerts = cursor.fetchone()[0]

            cursor.execute(
                """
                SELECT COUNT(*) FROM alert_records WHERE status = 'pending'
                """
            )
            pending_alerts = cursor.fetchone()[0]

            cursor.execute(
                """
                SELECT COUNT(DISTINCT country)
                FROM risk_events
                WHERE country IS NOT NULL AND country != 'unknown'
                """
            )
            country_count = cursor.fetchone()[0]

            cursor.execute(
                """
                SELECT COUNT(*) FROM risk_events
                WHERE review_status = 'reviewed' AND ss_score IS NOT NULL
                """
            )
            reviewed_count = cursor.fetchone()[0]
        finally:
            conn.close()

        return {
            "total_events": total,
            "level_dist": level_dist,
            "total_alerts": total_alerts,
            "pending_alerts": pending_alerts,
            "processed_alerts": total_alerts - pending_alerts,
            "country_count": country_count,
            "reviewed_count": reviewed_count,
        }

    def get_country_summary(self, limit: int = 20) -> pd.DataFrame:
        """国别风险汇总"""
        conn = get_db_connection(self.db_path)
        try:
            df = pd.read_sql(
                """
                SELECT country, event_count, s_count, m_count, l_count, a_count, latest_event_date
                FROM country_risk_summary
                ORDER BY event_count DESC
                LIMIT ?
                """,
                conn,
                params=(limit,),
            )
        finally:
            conn.close()
        return _coerce_date_columns(df, "latest_event_date")

    def get_trend(self, days: int = 30) -> pd.DataFrame:
        """近 N 天风险事件趋势"""
        conn = get_db_connection(self.db_path)
        try:
            since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
            df = pd.read_sql(
                """
                SELECT DATE(publish_date) as date, COUNT(*) as cnt
                FROM risk_events
                WHERE ss_score IS NOT NULL AND publish_date >= ?
                GROUP BY DATE(publish_date)
                ORDER BY date
                """,
                conn,
                params=(since,),
            )
        finally:
            conn.close()
        return df

    def get_hazard_distribution(self, limit: int = 10) -> pd.DataFrame:
        """危害类型分布"""
        conn = get_db_connection(self.db_path)
        try:
            df = pd.read_sql(
                """
                SELECT hazard_type as type, COUNT(*) as cnt
                FROM risk_events
                WHERE ss_score IS NOT NULL AND hazard_type IS NOT NULL AND hazard_type != ''
                GROUP BY hazard_type
                ORDER BY cnt DESC
                LIMIT ?
                """,
                conn,
                params=(limit,),
            )
        finally:
            conn.close()
        return df

    def get_recent_high_risk(self, limit: int = 15) -> pd.DataFrame:
        """最新高风险事件"""
        conn = get_db_connection(self.db_path)
        try:
            df = pd.read_sql(
                """
                SELECT event_id, publish_date, product_name, brand, country,
                       hazard_type, rs_level, total_score
                FROM risk_events
                WHERE ss_score IS NOT NULL AND rs_level IN ('S', 'M')
                ORDER BY evaluated_at DESC, total_score DESC
                LIMIT ?
                """,
                conn,
                params=(limit,),
            )
        finally:
            conn.close()
        return _coerce_date_columns(df, "publish_date")

    def get_source_status(self) -> pd.DataFrame:
        """数据源监控状态（返回所有列，便于页面重命名）。"""
        conn = get_db_connection(self.db_path)
        try:
            df = pd.read_sql(
                """
                SELECT *
                FROM monitor_sources
                ORDER BY last_check_at DESC NULLS LAST
                """,
                conn,
            )
        finally:
            conn.close()
        return df


class SourceHealthReadModel:
    """Read-only source health data for the Web UI, no Streamlit dependency."""

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path

    def get_source_health(self) -> pd.DataFrame:
        """Return a DataFrame of source health snapshots."""
        from whyfxpg.adapters.monitoring.db_source_health import DbSourceHealthAdapter

        adapter = DbSourceHealthAdapter(self.db_path)
        rows = []
        for source_id in adapter.list_sources():
            health = adapter.health(source_id)
            rows.append(
                {
                    "source_id": health.source_id,
                    "status": health.status,
                    "health_score": health.health_score,
                    "freshness_score": health.freshness_score,
                    "latency_ms": health.latency_ms,
                    "coverage_score": health.coverage_score,
                    "error_rate": health.error_rate,
                    "last_check_at": health.last_check_at,
                }
            )
        return pd.DataFrame(rows)

    def get_source_metrics(self, source_id: str, window: str = "24h") -> dict[str, Any]:
        """Return metrics for a single source."""
        from whyfxpg.adapters.monitoring.db_source_health import DbSourceHealthAdapter

        adapter = DbSourceHealthAdapter(self.db_path)
        return adapter.metrics(source_id, window)

    def get_lineage(self, event_id: str) -> dict[str, Any]:
        """Return lineage for a single event."""
        from whyfxpg.services.lineage_service import LineageService

        return LineageService(self.db_path).get_lineage_by_event(event_id)

    def get_health_trend(self, source_id: str, limit: int = 30) -> pd.DataFrame:
        """Return recent health snapshots for a source as a trend DataFrame."""
        conn = get_db_connection(self.db_path)
        try:
            df = pd.read_sql(
                """
                SELECT captured_at, health_score, freshness_score, coverage_score, error_rate
                FROM source_health_snapshots
                WHERE source_id = ?
                ORDER BY captured_at DESC
                LIMIT ?
                """,
                conn,
                params=(source_id, limit),
            )
            return df
        finally:
            conn.close()
