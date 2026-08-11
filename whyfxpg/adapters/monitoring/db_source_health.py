"""SQLite source health monitoring adapter.

Derives health/freshness/latency/coverage/lineage from the existing SQLite tables
without introducing a separate time-series database. Writes snapshots to
`source_health_snapshots` for trend charts.
"""

import json
from datetime import datetime, timedelta
from typing import Any

from whyfxpg.core.db import get_db_connection
from whyfxpg.ports.source_health import (
    Lineage,
    SourceHealth,
    SourceHealthPort,
)


def _parse_interval(interval: str) -> int:
    """Convert '1h', '30m', '1d' into seconds."""
    if not interval:
        return 3600
    value = int("".join(c for c in interval if c.isdigit()) or "1")
    unit = "".join(c for c in interval if c.isalpha()).lower() or "h"
    multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    return value * multipliers.get(unit, 3600)


def _since_from_window(window: str) -> str:
    """Convert a window like '24h' or '7d' into an ISO timestamp."""
    if not window:
        window = "24h"
    seconds = _parse_interval(window)
    return (datetime.now() - timedelta(seconds=seconds)).isoformat()  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计


class DbSourceHealthAdapter(SourceHealthPort):
    """Source health adapter backed by the SQLite database."""

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path

    def _conn(self):
        return get_db_connection(self.db_path)

    def list_sources(self) -> list[str]:
        conn = self._conn()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT source_id FROM monitor_sources ORDER BY source_id")
            return [row["source_id"] for row in cursor.fetchall()]
        finally:
            conn.close()

    def latency(self, source_id: str) -> int | None:
        conn = self._conn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT AVG(latency_ms) AS avg_latency
                FROM crawl_logs
                WHERE source_id = ?
                  AND status = 'ok'
                  AND latency_ms IS NOT NULL
                  AND run_at >= datetime('now', '-7 days')
                """,
                (source_id,),
            )
            row = cursor.fetchone()
            return int(row["avg_latency"]) if row and row["avg_latency"] else None
        finally:
            conn.close()

    def coverage(self, source_id: str) -> float:
        conn = self._conn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT COUNT(*) AS total,
                       SUM(CASE WHEN product_name IS NOT NULL AND product_name != ''
                                AND country IS NOT NULL AND country != ''
                                AND hazard_type IS NOT NULL AND hazard_type != ''
                                AND publish_date IS NOT NULL
                           THEN 1 ELSE 0 END) AS complete
                FROM risk_events
                WHERE source_id = ?
                """,
                (source_id,),
            )
            row = cursor.fetchone()
            total = row["total"] if row else 0
            complete = row["complete"] if row else 0
            if total == 0:
                return 0.0
            return round(complete / total, 3)
        finally:
            conn.close()

    def error_rate(self, source_id: str, window: str = "24h") -> float:
        conn = self._conn()
        try:
            cursor = conn.cursor()
            since = _since_from_window(window)
            cursor.execute(
                """
                SELECT COUNT(*) AS total,
                       SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) AS errors
                FROM crawl_logs
                WHERE source_id = ? AND run_at >= ?
                """,
                (source_id, since),
            )
            row = cursor.fetchone()
            total = row["total"] if row else 0
            errors = row["errors"] if row else 0
            if total == 0:
                return 0.0
            return round(errors / total, 3)
        finally:
            conn.close()

    def freshness(self, source_id: str) -> float:
        conn = self._conn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT last_check_at, check_interval FROM monitor_sources WHERE source_id = ?",
                (source_id,),
            )
            row = cursor.fetchone()
            if not row or not row["last_check_at"]:
                return 0.0
            interval = _parse_interval(row["check_interval"] or "1h")
            last = datetime.fromisoformat(row["last_check_at"])
            elapsed = (datetime.now() - last).total_seconds()  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
            if elapsed <= 0:
                return 1.0
            if elapsed >= 2 * interval:
                return 0.0
            return round(1.0 - (elapsed / (2 * interval)), 3)
        finally:
            conn.close()

    def health(self, source_id: str) -> SourceHealth:
        freshness = self.freshness(source_id)
        latency = self.latency(source_id)
        coverage = self.coverage(source_id)
        error_rate = self.error_rate(source_id, "24h")

        latency_score = 1.0
        if latency is not None:
            if latency <= 1000:
                latency_score = 1.0
            elif latency <= 5000:
                latency_score = 0.7
            else:
                latency_score = 0.4

        score = round(
            0.35 * freshness
            + 0.25 * latency_score
            + 0.20 * coverage
            + 0.20 * (1.0 - error_rate),
            3,
        )

        if error_rate >= 0.5:
            status = "error"
        elif score >= 0.8:
            status = "ok"
        elif score >= 0.5:
            status = "degraded"
        elif freshness == 0.0:
            status = "stale"
        else:
            status = "error"

        conn = self._conn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT last_check_at FROM monitor_sources WHERE source_id = ?",
                (source_id,),
            )
            row = cursor.fetchone()
            last_check_at = row["last_check_at"] if row else None
        finally:
            conn.close()

        return SourceHealth(
            source_id=source_id,
            status=status,
            health_score=score,
            freshness_score=freshness,
            latency_ms=latency,
            coverage_score=coverage,
            error_rate=error_rate,
            last_check_at=last_check_at,
            details={
                "latency_score": latency_score,
                "window": "24h",
            },
        )

    def metrics(self, source_id: str, window: str) -> dict[str, Any]:
        conn = self._conn()
        try:
            cursor = conn.cursor()
            since = _since_from_window(window)
            cursor.execute(
                """
                SELECT COUNT(*) AS total_logs,
                       AVG(CASE WHEN status = 'ok' THEN latency_ms END) AS avg_latency,
                       SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) AS errors,
                       MAX(run_at) AS last_run
                FROM crawl_logs
                WHERE source_id = ? AND run_at >= ?
                """,
                (source_id, since),
            )
            row = cursor.fetchone()
            return {
                "source_id": source_id,
                "window": window,
                "total_logs": row["total_logs"] if row else 0,
                "avg_latency_ms": int(row["avg_latency"]) if row and row["avg_latency"] else None,
                "errors": row["errors"] if row else 0,
                "error_rate": self.error_rate(source_id, window),
                "freshness": self.freshness(source_id),
                "coverage": self.coverage(source_id),
                "last_run": row["last_run"] if row else None,
            }
        finally:
            conn.close()

    def lineage(self, event_id: str) -> Lineage:
        conn = self._conn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT event_id, page_id, source_id, source_url
                FROM risk_events
                WHERE event_id = ?
                """,
                (event_id,),
            )
            event_row = cursor.fetchone()
            if not event_row:
                return Lineage(event_id=event_id)

            page_id = event_row["page_id"]
            source_id = event_row["source_id"]
            url = event_row["source_url"]
            run_at = None
            if page_id:
                cursor.execute(
                    "SELECT source_id, fetched_at FROM raw_pages WHERE page_id = ?",
                    (page_id,),
                )
                page_row = cursor.fetchone()
                if page_row:
                    source_id = page_row["source_id"] or source_id
                    run_at = page_row["fetched_at"]
            if source_id:
                cursor.execute(
                    "SELECT run_at FROM crawl_logs WHERE source_id = ? ORDER BY run_at DESC LIMIT 1",
                    (source_id,),
                )
                log_row = cursor.fetchone()
                if log_row and not run_at:
                    run_at = log_row["run_at"]

            return Lineage(
                event_id=event_id,
                page_id=page_id,
                source_id=source_id,
                run_at=run_at,
                url=url,
            )
        finally:
            conn.close()

    def write_snapshot(self, health: SourceHealth) -> None:
        conn = self._conn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO source_health_snapshots
                (source_id, captured_at, health_score, freshness_score, latency_ms,
                 coverage_score, error_rate, status, details_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    health.source_id,
                    datetime.now().isoformat(),  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
                    health.health_score,
                    health.freshness_score,
                    health.latency_ms,
                    health.coverage_score,
                    health.error_rate,
                    health.status,
                    json.dumps(health.details, ensure_ascii=False),
                ),
            )
            conn.commit()
        finally:
            conn.close()
