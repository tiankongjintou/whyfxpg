"""Auto-split store module."""

from datetime import datetime

from whyfxpg.core.stores.unit_of_work import BaseStore


class SummaryStore(BaseStore):
    """风险汇总 store，负责重建产品/国别/企业三张汇总表。"""

    def rebuild_summaries(self, config_version: str, model_version: str) -> None:
        """清空并重建风险汇总表。"""
        cursor = self.uow.connection.cursor()
        updated_at = datetime.now().isoformat()  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计

        cursor.execute("DELETE FROM product_risk_summary")
        cursor.execute("DELETE FROM country_risk_summary")
        cursor.execute("DELETE FROM enterprise_risk_summary")

        cursor.execute("""
            INSERT INTO product_risk_summary (
                product_id, product_name, brand, hs_code, product_category, country, manufacturer,
                event_count, latest_ss, latest_ps, latest_total_score, latest_rs_level, highest_hazard_type,
                last_event_date, first_event_date, updated_at, config_version, model_version
            )
            SELECT
                COALESCE(product_name, '') || '|' || COALESCE(brand, '') || '|' || COALESCE(country, ''),
                MAX(product_name),
                MAX(brand),
                MAX(hs_code),
                MAX(product_category),
                MAX(country),
                MAX(manufacturer),
                COUNT(*),
                MAX(ss_score),
                MAX(ps_score),
                MAX(total_score),
                MAX(rs_level),
                MAX(hazard_type),
                MAX(publish_date),
                MIN(publish_date),
                ?,
                MAX(config_version),
                MAX(model_version)
            FROM risk_events
            WHERE ss_score IS NOT NULL
            GROUP BY COALESCE(product_name, '') || '|' || COALESCE(brand, '') || '|' || COALESCE(country, '')
        """, (updated_at,))

        cursor.execute("""
            INSERT INTO country_risk_summary (country, event_count, s_count, m_count, l_count, a_count, latest_event_date, updated_at)
            SELECT
                COALESCE(country, 'unknown'),
                COUNT(*),
                SUM(CASE WHEN rs_level = 'S' THEN 1 ELSE 0 END),
                SUM(CASE WHEN rs_level = 'M' THEN 1 ELSE 0 END),
                SUM(CASE WHEN rs_level = 'L' THEN 1 ELSE 0 END),
                SUM(CASE WHEN rs_level = 'A' THEN 1 ELSE 0 END),
                MAX(publish_date),
                ?
            FROM risk_events
            WHERE ss_score IS NOT NULL
            GROUP BY COALESCE(country, 'unknown')
        """, (updated_at,))

        cursor.execute("""
            INSERT INTO enterprise_risk_summary (manufacturer, country, event_count, s_count, m_count, l_count, a_count, latest_event_date, updated_at)
            SELECT
                COALESCE(manufacturer, 'unknown'),
                MAX(country),
                COUNT(*),
                SUM(CASE WHEN rs_level = 'S' THEN 1 ELSE 0 END),
                SUM(CASE WHEN rs_level = 'M' THEN 1 ELSE 0 END),
                SUM(CASE WHEN rs_level = 'L' THEN 1 ELSE 0 END),
                SUM(CASE WHEN rs_level = 'A' THEN 1 ELSE 0 END),
                MAX(publish_date),
                ?
            FROM risk_events
            WHERE ss_score IS NOT NULL
            GROUP BY COALESCE(manufacturer, 'unknown')
        """, (updated_at,))
