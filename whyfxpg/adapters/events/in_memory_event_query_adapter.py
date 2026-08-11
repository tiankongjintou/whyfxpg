"""InMemory 事件查询适配器（P03 测试替身）。"""


from whyfxpg.ports.event_query_port import (
    AlertRecord,
    CompanyProfile,
    EventQueryPort,
    EventRecord,
)


class InMemoryEventQueryAdapter(EventQueryPort):
    """内存事件/预警存储：key 为 (account_id, event_id)。"""

    def __init__(
        self,
        events: dict[tuple[str, str], EventRecord] | None = None,
        alerts: dict[tuple[str, str], AlertRecord] | None = None,
    ):
        self._events: dict[tuple[str, str], EventRecord] = events or {}
        self._alerts: dict[tuple[str, str], AlertRecord] = alerts or {}

    def add_event(self, account_id: str, event: EventRecord) -> None:
        self._events[(account_id, event.event_id)] = event

    def add_alert(self, account_id: str, alert: AlertRecord) -> None:
        self._alerts[(account_id, alert.alert_id)] = alert

    def list_events(
        self,
        account_id: str,
        page: int,
        per_page: int,
        manufacturer: str | None = None,
        country: str | None = None,
        hazard_type: str | None = None,
    ) -> tuple[list[EventRecord], int]:
        rows = [
            e
            for (acc, _), e in self._events.items()
            if acc == account_id
            and (manufacturer is None or e.manufacturer == manufacturer)
            and (country is None or e.country == country)
            and (hazard_type is None or e.hazard_type == hazard_type)
        ]
        rows.sort(key=lambda e: e.publish_date, reverse=True)
        start = (page - 1) * per_page
        return rows[start : start + per_page], len(rows)

    def get_event(self, account_id: str, event_id: str) -> EventRecord | None:
        return self._events.get((account_id, event_id))

    def company_profile(self, account_id: str, company_name: str) -> CompanyProfile | None:
        rows = [
            e
            for (acc, _), e in self._events.items()
            if acc == account_id and e.manufacturer == company_name
        ]
        if not rows:
            return None
        distribution: dict[str, int] = {}
        total = 0.0
        for e in rows:
            distribution[e.rs_level] = distribution.get(e.rs_level, 0) + 1
            total += e.total_score
        rows.sort(key=lambda e: e.publish_date, reverse=True)
        return CompanyProfile(
            company_name=company_name,
            event_count=len(rows),
            avg_score=round(total / len(rows), 2),
            level_distribution=distribution,
            latest_events=rows[:10],
        )

    def list_alerts(
        self,
        account_id: str,
        page: int,
        per_page: int,
        status: str | None = None,
    ) -> tuple[list[AlertRecord], int]:
        rows = [
            a
            for (acc, _), a in self._alerts.items()
            if acc == account_id and (status is None or a.status == status)
        ]
        rows.sort(key=lambda a: a.triggered_at, reverse=True)
        start = (page - 1) * per_page
        return rows[start : start + per_page], len(rows)

    def get_alert(self, account_id: str, alert_id: str) -> AlertRecord | None:
        return self._alerts.get((account_id, alert_id))
