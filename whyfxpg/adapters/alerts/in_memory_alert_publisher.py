"""内存预警发布适配器（测试 double）。"""

from typing import Any

from ...ports.alert_publisher import AlertPublisher


class InMemoryAlertPublisher(AlertPublisher):
    """记录所有发布请求的测试替身，支持按规则/对象去重模拟。"""

    def __init__(self, existing: list[dict[str, Any]] | None = None):
        self.records: list[dict[str, Any]] = []
        self.existing: set = set()
        if existing:
            for a in existing:
                self.existing.add(
                    (a.get("rule_id"), a.get("object_type"), a.get("object_value"))
                )

    def publish(self, alert: dict[str, Any]) -> bool:
        key = (alert.get("rule_id"), alert.get("object_type"), alert.get("object_value"))
        if key in self.existing:
            return False
        self.existing.add(key)
        self.records.append(alert)
        return True

    def close(self) -> None:
        pass

    def clear(self) -> None:
        self.records.clear()
        self.existing.clear()
