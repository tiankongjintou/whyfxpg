"""事件/预警查询端口 (P03)。

把“如何从存储查询风险事件/预警”与 API 层分离：
- API 路由只依赖 EventQueryPort，不感知 SQLite / PostgreSQL。
- 所有查询方法都带 account_id，保证租户隔离（P03 AC-9）。
- 生产用 PgEventQueryAdapter，测试用 InMemoryEventQueryAdapter。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(frozen=True)
class EventRecord:
    event_id: str
    title: str
    product_name: str
    brand: str
    manufacturer: str
    country: str
    hazard_type: str
    severity_level: str
    total_score: float
    rs_level: str
    publish_date: str


@dataclass(frozen=True)
class AlertRecord:
    alert_id: str
    rule_name: str
    severity: str
    status: str
    triggered_at: str
    description: str


@dataclass(frozen=True)
class CompanyProfile:
    company_name: str
    event_count: int
    avg_score: float
    level_distribution: dict  # {"S": n, "M": n, "L": n, "A": n}
    latest_events: list[EventRecord] = field(default_factory=list)


class EventQueryPort(ABC):
    """风险事件与预警查询端口（全部按 account_id 隔离）。"""

    @abstractmethod
    def list_events(
        self,
        account_id: str,
        page: int,
        per_page: int,
        manufacturer: str | None = None,
        country: str | None = None,
        hazard_type: str | None = None,
    ) -> tuple[list[EventRecord], int]:
        """分页查询风险事件，返回 (事件列表, 总数)。"""
        raise NotImplementedError

    @abstractmethod
    def get_event(self, account_id: str, event_id: str) -> EventRecord | None:
        """获取单个事件。"""
        raise NotImplementedError

    @abstractmethod
    def company_profile(self, account_id: str, company_name: str) -> CompanyProfile | None:
        """企业风险画像（聚合该企业全部事件）。"""
        raise NotImplementedError

    @abstractmethod
    def list_alerts(
        self,
        account_id: str,
        page: int,
        per_page: int,
        status: str | None = None,
    ) -> tuple[list[AlertRecord], int]:
        """分页查询预警，返回 (预警列表, 总数)。"""
        raise NotImplementedError

    @abstractmethod
    def get_alert(self, account_id: str, alert_id: str) -> AlertRecord | None:
        """获取单个预警。"""
        raise NotImplementedError
