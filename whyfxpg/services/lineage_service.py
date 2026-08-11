"""Lineage service: trace a risk event back to its source and forward to alerts/reviews.

Given an event_id, alert_id, or review_id, the service assembles:

    source -> crawl -> raw_page -> event -> score -> alerts -> reviews

plus causal-path metadata if available.
"""

from dataclasses import dataclass, field
from typing import Any

from whyfxpg.core.db import get_db_connection


@dataclass
class LineageNode:
    kind: str
    id: str
    name: str
    meta: dict[str, Any] = field(default_factory=dict)


class LineageService:
    """Build lineage chains from the SQLite database."""

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path

    def _conn(self):
        return get_db_connection(self.db_path)

    def get_lineage_by_event(self, event_id: str) -> dict[str, Any]:
        conn = self._conn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT event_id, page_id, source_id, source_url, title,
                       country, manufacturer, product_category, hazard_type,
                       ss_score, ps_score, total_score, rs_level, evaluated_at,
                       publish_date
                FROM risk_events
                WHERE event_id = ?
                """,
                (event_id,),
            )
            event_row = cursor.fetchone()
            if not event_row:
                return {"seed_type": "event", "seed_id": event_id}

            event = dict(event_row)
            page: dict[str, Any] | None = None
            source: dict[str, Any] | None = None
            crawl_log: dict[str, Any] | None = None

            page_id = event.get("page_id")
            source_id = event.get("source_id")

            if page_id:
                cursor.execute(
                    """
                    SELECT page_id, source_id, url, fetched_at, content_type, status
                    FROM raw_pages
                    WHERE page_id = ?
                    """,
                    (page_id,),
                )
                row = cursor.fetchone()
                if row:
                    page = dict(row)
                    source_id = page.get("source_id") or source_id

            if source_id:
                cursor.execute(
                    """
                    SELECT source_id, name, url, source_type, enabled, status, last_check_at
                    FROM monitor_sources
                    WHERE source_id = ?
                    """,
                    (source_id,),
                )
                row = cursor.fetchone()
                if row:
                    source = dict(row)
                cursor.execute(
                    """
                    SELECT source_id, run_at, status, pages_fetched, pages_new, latency_ms, content_length
                    FROM crawl_logs
                    WHERE source_id = ?
                    ORDER BY run_at DESC
                    LIMIT 1
                    """,
                    (source_id,),
                )
                log_row = cursor.fetchone()
                if log_row:
                    crawl_log = dict(log_row)

            cursor.execute(
                """
                SELECT alert_id, rule_id, rule_name, triggered_at, severity,
                       object_type, object_value, status, triggered_value
                FROM alert_records
                WHERE object_type = 'event' AND object_value = ?
                ORDER BY triggered_at DESC
                """,
                (event_id,),
            )
            alerts = [dict(r) for r in cursor.fetchall()]

            cursor.execute(
                """
                SELECT review_id, event_id, reviewed_at, reviewer, adjusted_rs,
                       reason
                FROM manual_reviews
                WHERE event_id = ?
                ORDER BY reviewed_at DESC
                """,
                (event_id,),
            )
            reviews = [dict(r) for r in cursor.fetchall()]

            cursor.execute(
                """
                SELECT path_id, chain, total_weight, confidence, explanation, generated_at
                FROM causal_paths
                WHERE root_event_id = ?
                ORDER BY generated_at DESC
                """,
                (event_id,),
            )
            causal_paths = [dict(r) for r in cursor.fetchall()]

            return {
                "seed_type": "event",
                "seed_id": event_id,
                "source": source,
                "crawl_log": crawl_log,
                "raw_page": page,
                "event": event,
                "score": {
                    "ss_score": event.get("ss_score"),
                    "ps_score": event.get("ps_score"),
                    "total_score": event.get("total_score"),
                    "rs_level": event.get("rs_level"),
                    "evaluated_at": event.get("evaluated_at"),
                },
                "alerts": alerts,
                "reviews": reviews,
                "causal_paths": causal_paths,
            }
        finally:
            conn.close()

    def get_lineage_by_alert(self, alert_id: str) -> dict[str, Any]:
        conn = self._conn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT alert_id, rule_id, rule_name, triggered_at, severity,
                       object_type, object_value, status
                FROM alert_records
                WHERE alert_id = ?
                """,
                (alert_id,),
            )
            row = cursor.fetchone()
            if not row:
                return {"seed_type": "alert", "seed_id": alert_id}
            alert = dict(row)
            event_id = None
            if alert.get("object_type") == "event":
                event_id = alert.get("object_value")
            if not event_id:
                return {"seed_type": "alert", "seed_id": alert_id, "alert": alert}
            chain = self.get_lineage_by_event(event_id)
            chain["seed_type"] = "alert"
            chain["seed_id"] = alert_id
            chain["alert"] = alert
            return chain
        finally:
            conn.close()

    def get_lineage_by_review(self, review_id: str) -> dict[str, Any]:
        conn = self._conn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT review_id, event_id, reviewed_at, reviewer, adjusted_rs, reason
                FROM manual_reviews
                WHERE review_id = ?
                """,
                (review_id,),
            )
            row = cursor.fetchone()
            if not row:
                return {"seed_type": "review", "seed_id": review_id}
            review = dict(row)
            event_id = review.get("event_id")
            if not event_id:
                return {"seed_type": "review", "seed_id": review_id, "review": review}
            chain = self.get_lineage_by_event(event_id)
            chain["seed_type"] = "review"
            chain["seed_id"] = review_id
            chain["review"] = review
            return chain
        finally:
            conn.close()
