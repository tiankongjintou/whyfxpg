"""
内存来源适配器：用于测试或离线的 SourcePort 假实现。
"""

from collections.abc import Callable
from typing import Any

from whyfxpg.ports.source_port import FetchedPage, SourcePort


class InMemorySourceAdapter(SourcePort):
    """根据预置数据或回调函数返回 FetchedPage，避免真实网络请求。"""

    def __init__(
        self,
        pages: dict[str, FetchedPage] | None = None,
        callback: Callable[[str, dict[str, Any]], FetchedPage] | None = None,
    ):
        self.pages = pages or {}
        self.callback = callback

    def fetch(self, source_id: str, cfg: dict[str, Any]) -> FetchedPage:
        if self.callback is not None:
            return self.callback(source_id, cfg)
        if source_id in self.pages:
            return self.pages[source_id]
        raise NotImplementedError(
            f"InMemorySourceAdapter has no page for source_id={source_id!r}"
        )
