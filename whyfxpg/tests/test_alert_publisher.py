"""AlertPublisher 端口测试。

测试 seam：DbAlertPublisher.publish(alert) 与 InMemoryAlertPublisher.publish(alert)。
"""


from whyfxpg.adapters.alerts import DbAlertPublisher, InMemoryAlertPublisher
from whyfxpg.core.stores import AlertStore, UnitOfWork

ALERT = {
    "alert_id": "a1",
    "rule_id": "rule_high_severity",
    "rule_name": "高严重度事件预警",
    "object_type": "event",
    "object_value": "e1",
    "severity": "high",
    "triggered_value": "severity=严重",
    "description": "发现严重事件",
}


def test_db_publisher_inserts_alert(initialized_db: str) -> None:
    with UnitOfWork(initialized_db) as uow:
        publisher = DbAlertPublisher(AlertStore(uow))
        assert publisher.publish(ALERT) is True
        # 同 key 重复发布应被去重
        assert publisher.publish(ALERT) is False

    with UnitOfWork(initialized_db) as uow:
        cursor = uow.connection.cursor()
        cursor.execute("SELECT COUNT(*) FROM alert_records WHERE rule_id = ?", (ALERT["rule_id"],))
        assert cursor.fetchone()[0] == 1


def test_in_memory_publisher_records_and_deduplicates() -> None:
    publisher = InMemoryAlertPublisher()
    assert publisher.publish(ALERT) is True
    assert publisher.publish(ALERT) is False
    assert len(publisher.records) == 1
    assert publisher.records[0]["rule_id"] == "rule_high_severity"


def test_in_memory_publisher_with_existing_alerts() -> None:
    existing = [ALERT.copy()]
    publisher = InMemoryAlertPublisher(existing)
    assert publisher.publish(ALERT) is False
    assert len(publisher.records) == 0
