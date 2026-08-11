"""Source monitoring service.

Orchestrates source health checks, persists snapshots, and drafts alerts when a
source degrades. Keeps the core domain thin by delegating metric computation to
a SourceHealthPort adapter.
"""

from typing import Any

from whyfxpg.ports.alert_publisher import AlertPublisher
from whyfxpg.ports.source_health import (
    AlertDraft,
    SourceHealth,
    SourceHealthPort,
)


class SourceMonitorService:
    """Monitor all sources, snapshot health, and emit degradation alerts."""

    def __init__(
        self,
        health_port: SourceHealthPort,
        publisher: AlertPublisher | None = None,
    ):
        self.health_port = health_port
        self.publisher = publisher

    def check_source(self, source_id: str) -> SourceHealth:
        """Evaluate and snapshot a single source."""
        health = self.health_port.health(source_id)
        self.health_port.write_snapshot(health)
        return health

    def check_all(self) -> list[SourceHealth]:
        """Evaluate and snapshot every known source."""
        results = []
        for source_id in self.health_port.list_sources():
            results.append(self.check_source(source_id))
        return results

    def health_alert(self, health: SourceHealth) -> AlertDraft | None:
        """Return an alert draft if the source health is degraded or worse."""
        if health.status in {"ok", "unknown"}:
            return None
        severity = "high" if health.status == "error" else "medium"
        return AlertDraft(
            source_id=health.source_id,
            severity=severity,
            title=f"数据源 {health.source_id} 状态：{health.status}",
            description=(
                f"健康分 {health.health_score}，"
                f"新鲜度 {health.freshness_score}，"
                f"覆盖率 {health.coverage_score}，"
                f"错误率 {health.error_rate}"
            ),
        )

    def publish_alert(self, alert: AlertDraft) -> bool:
        """Publish a degradation alert via the configured publisher."""
        if self.publisher is None:
            return False
        return self.publisher.publish(
            {
                "rule_id": "source_health",
                "rule_name": alert.title,
                "object_type": "source",
                "object_value": alert.source_id,
                "severity": alert.severity,
                "triggered_value": alert.severity,
                "description": alert.description,
            }
        )

    def run(self) -> dict[str, Any]:
        """Evaluate all sources, persist snapshots, and publish alerts."""
        healths = self.check_all()
        alerts: list[AlertDraft] = []
        for health in healths:
            alert = self.health_alert(health)
            if alert:
                alerts.append(alert)
                self.publish_alert(alert)
        return {
            "module": "source_monitor",
            "status": "success" if not any(h.status == "error" for h in healths) else "partial",
            "records_processed": len(healths),
            "records_created": len(alerts),
            "healths": [h.__dict__ for h in healths],
            "alerts": [
                {
                    "source_id": a.source_id,
                    "severity": a.severity,
                    "title": a.title,
                }
                for a in alerts
            ],
        }
