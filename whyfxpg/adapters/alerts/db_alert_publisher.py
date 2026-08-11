"""数据库预警发布适配器。"""

from typing import Any

from ...core.stores import AlertStore
from ...ports.alert_publisher import AlertPublisher


class DbAlertPublisher(AlertPublisher):
    """基于 AlertStore 的预警发布实现。"""

    def __init__(self, store: AlertStore):
        self.store = store

    def publish(self, alert: dict[str, Any]) -> bool:
        if self.store.find_existing(
            alert["rule_id"], alert["object_type"], alert["object_value"]
        ) > 0:
            return False

        self.store.insert_alert(
            rule_id=alert["rule_id"],
            rule_name=alert["rule_name"],
            object_type=alert["object_type"],
            object_value=alert["object_value"],
            severity=alert["severity"],
            triggered_value=alert["triggered_value"],
            description=alert["description"],
            explanation_json=alert.get("explanation_json"),
        )
        return True

    def close(self) -> None:
        pass
