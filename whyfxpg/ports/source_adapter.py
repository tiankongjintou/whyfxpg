"""
BaseSourceAdapter 抽象基类 + SourceResponse 数据模型 + SourceRegistry 注册表。

遵循 docs/技术改造路线图.md §3.3 接口定义：
- source_id / source_name 属性
- fetch(since) -> List[SourceResponse]
- parse(raw) -> RiskEvent dict
- health_check() -> bool
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, ClassVar


@dataclass
class SourceResponse:
    """一次数据源采集返回的标准化响应。"""

    source_id: str
    url: str
    raw_content: bytes | str
    title: str = ""
    published_at: str | None = None
    country: str = "CA"  # 加拿大
    language: str = "en"  # 默认英文，可为 "fr"
    hazard_type: str = ""
    severity: str = ""
    product_name: str = ""
    manufacturer: str = ""
    raw_fields: dict[str, Any] = field(default_factory=dict)
    fetched_at: str = field(
        default_factory=lambda: datetime.now().isoformat()  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
    )
    status: str = "ok"  # "ok" | "error"
    error_msg: str | None = None

    @property
    def success(self) -> bool:
        return self.status == "ok" and bool(self.raw_content)


class BaseSourceAdapter(ABC):
    """所有数据源适配器的基类（§3.3 接口定义）。"""

    @property
    @abstractmethod
    def source_id(self) -> str:
        """数据源唯一标识，如 'CPSC'、'RAPEX'、'CANADA_HEALTH'。"""
        ...

    @property
    @abstractmethod
    def source_name(self) -> str:
        """数据源显示名称（英文）。"""
        ...

    @property
    def source_name_zh(self) -> str:
        """数据源显示名称（中文）。默认返回英文名，子类可覆盖。"""
        return self.source_name

    @abstractmethod
    def fetch(self, since: datetime | None = None) -> list[SourceResponse]:
        """
        从数据源获取原始数据，返回标准化响应列表。

        Args:
            since: 可选时间戳，只返回该时间之后的数据。

        Returns:
            List[SourceResponse]：原始响应列表，即使只取到一条也返回列表。
        """
        ...

    @abstractmethod
    def parse(self, raw: SourceResponse) -> dict[str, Any]:
        """
        将 SourceResponse 解析为 RiskEvent 字典。

        Returns:
            dict：符合 risk_events 表契约的字段字典。
        """
        ...

    def health_check(self) -> bool:
        """
        健康检查，返回数据源是否可达。

        默认实现：简单网络探测（HEAD 请求到主 URL）。
        子类可覆盖以实现更复杂的状态检测。
        """
        import requests

        try:
            resp = requests.head(self._health_url(), timeout=10)
            return resp.status_code < 500
        except Exception:  # noqa: BLE001 — 外部调用兜底,刻意吞异常
            return False

    def _health_url(self) -> str:
        """返回健康检查用的 URL，子类可覆盖。"""
        return ""


class SourceRegistry:
    """
    全局数据源注册表。

    用法::

        SourceRegistry.register(CPSCAdapter())
        SourceRegistry.register(RapexAdapter())

        for adapter in SourceRegistry.all():
            events = adapter.fetch()
            for raw in events:
                event = adapter.parse(raw)
                RiskEventStore.add(event)
    """

    _adapters: ClassVar[dict[str, BaseSourceAdapter]] = {}

    @classmethod
    def register(cls, adapter: BaseSourceAdapter) -> None:
        if adapter.source_id in cls._adapters:
            raise ValueError(
                f"SourceAdapter with source_id={adapter.source_id!r} already registered"
            )
        cls._adapters[adapter.source_id] = adapter

    @classmethod
    def get(cls, source_id: str) -> BaseSourceAdapter | None:
        return cls._adapters.get(source_id)

    @classmethod
    def all(cls) -> list[BaseSourceAdapter]:
        return list(cls._adapters.values())

    @classmethod
    def unregister(cls, source_id: str) -> None:
        cls._adapters.pop(source_id, None)

    @classmethod
    def clear(cls) -> None:
        """仅用于测试。"""
        cls._adapters.clear()
