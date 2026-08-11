"""PostgreSQL 事件查询适配器（P03 生产实现）。

查询 risk_events / alert_records 表（Alembic 0001/0002 创建），
按 account_id 过滤实现租户隔离。连接串来自 DATABASE_URL。
"""


from sqlalchemy import create_engine, text

from whyfxpg.core.db import get_database_url
from whyfxpg.ports.event_query_port import (
    AlertRecord,
    CompanyProfile,
    EventQueryPort,
    EventRecord,
)


class PgEventQueryAdapter(EventQueryPort):
    """基于 SQLAlchemy 的 risk_events / alert_records 查询适配器。"""

    def __init__(self, database_url: str | None = None):
        self._url = database_url or get_database_url()
        self._engine = create_engine(self._url)

    def list_events(
        self,
        account_id: str,
        page: int,
        per_page: int,
        manufacturer: str | None = None,
        country: str | None = None,
        hazard_type: str | None = None,
    ) -> tuple[list[EventRecord], int]:
        where = ["account_id = :account_id"]
        params: dict = {"account_id": account_id}
        if manufacturer:
            where.append("manufacturer = :manufacturer")
            params["manufacturer"] = manufacturer
        if country:
            where.append("country = :country")
            params["country"] = country
        if hazard_type:
            where.append("hazard_type = :hazard_type")
            params["hazard_type"] = hazard_type
        clause = " AND ".join(where)
        offset = (page - 1) * per_page
        with self._engine.connect() as conn:
            total = conn.execute(
                text(f"SELECT COUNT(*) FROM risk_events WHERE {clause}"), params
            ).scalar()
            rows = conn.execute(
                text(
                    f"SELECT * FROM risk_events WHERE {clause} "
                    "ORDER BY publish_date DESC NULLS LAST LIMIT :limit OFFSET :offset"
                ),
                {**params, "limit": per_page, "offset": offset},
            ).mappings()
            events = [self._to_event(r) for r in rows]
        return events, int(total or 0)

    def get_event(self, account_id: str, event_id: str) -> EventRecord | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT * FROM risk_events "
                    "WHERE event_id = :event_id AND account_id = :account_id"
                ),
                {"event_id": event_id, "account_id": account_id},
            ).mappings().first()
        return self._to_event(row) if row else None

    def company_profile(self, account_id: str, company_name: str) -> CompanyProfile | None:
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT * FROM risk_events "
                    "WHERE manufacturer = :company AND account_id = :account_id "
                    "ORDER BY publish_date DESC NULLS LAST"
                ),
                {"company": company_name, "account_id": account_id},
            ).mappings().all()
        if not rows:
            return None
        events = [self._to_event(r) for r in rows]
        distribution: dict = {}
        total = 0.0
        for e in events:
            distribution[e.rs_level] = distribution.get(e.rs_level, 0) + 1
            total += e.total_score
        return CompanyProfile(
            company_name=company_name,
            event_count=len(events),
            avg_score=round(total / len(events), 2),
            level_distribution=distribution,
            latest_events=events[:10],
        )

    def list_alerts(
        self,
        account_id: str,
        page: int,
        per_page: int,
        status: str | None = None,
    ) -> tuple[list[AlertRecord], int]:
        where = ["account_id = :account_id"]
        params: dict = {"account_id": account_id}
        if status:
            where.append("status = :status")
            params["status"] = status
        clause = " AND ".join(where)
        offset = (page - 1) * per_page
        with self._engine.connect() as conn:
            total = conn.execute(
                text(f"SELECT COUNT(*) FROM alert_records WHERE {clause}"), params
            ).scalar()
            rows = conn.execute(
                text(
                    f"SELECT * FROM alert_records WHERE {clause} "
                    "ORDER BY triggered_at DESC NULLS LAST LIMIT :limit OFFSET :offset"
                ),
                {**params, "limit": per_page, "offset": offset},
            ).mappings()
            alerts = [self._to_alert(r) for r in rows]
        return alerts, int(total or 0)

    def get_alert(self, account_id: str, alert_id: str) -> AlertRecord | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT * FROM alert_records "
                    "WHERE alert_id = :alert_id AND account_id = :account_id"
                ),
                {"alert_id": alert_id, "account_id": account_id},
            ).mappings().first()
        return self._to_alert(row) if row else None

    @staticmethod
    def _to_event(row) -> EventRecord:
        return EventRecord(
            event_id=row["event_id"],
            title=row.get("title") or "",
            product_name=row.get("product_name") or "",
            brand=row.get("brand") or "",
            manufacturer=row.get("manufacturer") or "",
            country=row.get("country") or "",
            hazard_type=row.get("hazard_type") or "",
            severity_level=row.get("severity_level") or "",
            total_score=float(row["total_score"] or 0),
            rs_level=row.get("rs_level") or "A",
            publish_date=str(row.get("publish_date") or ""),
        )

    @staticmethod
    def _to_alert(row) -> AlertRecord:
        return AlertRecord(
            alert_id=row["alert_id"],
            rule_name=row.get("rule_name") or "",
            severity=row.get("severity") or "",
            status=row.get("status") or "",
            triggered_at=str(row.get("triggered_at") or ""),
            description=row.get("description") or "",
        )

    def close(self) -> None:
        self._engine.dispose()
