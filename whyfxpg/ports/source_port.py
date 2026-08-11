"""
Source port：采集来源抽象。

把 HTTP 请求细节（requests、重试、限速）与“使用内容”的业务流程解耦，
让 Fetcher 可以注入 HttpSourceAdapter 或 InMemorySourceAdapter 测试替身。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class FetchedPage:
    """一次采集返回的原始页面数据。"""

    source_id: str
    url: str
    content: bytes
    content_type: str
    content_hash: str
    fetched_at: str = field(
        default_factory=lambda: datetime.now().isoformat()  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
    )
    request_started_at: str | None = None
    latency_ms: int | None = None
    content_length: int | None = None
    status: str = "ok"  # "ok" or "error"
    error_msg: str | None = None

    @property
    def success(self) -> bool:
        return self.status == "ok" and self.content_hash != ""


class SourcePort(ABC):
    """采集来源端口。"""

    @abstractmethod
    def fetch(self, source_id: str, cfg: dict[str, Any]) -> FetchedPage:
        """
        根据 source_id 与配置抓取原始内容。

        Args:
            source_id: 来源唯一标识。
            cfg: 来源配置，至少包含 url、headers、enabled、delay 等。

        Returns:
            FetchedPage：抓取结果；失败时 status="error" 并携带 error_msg。
        """
        ...
