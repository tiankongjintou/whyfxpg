"""
SourceRegistry — 数据源适配器全局注册表。

实现技术改造路线图 §3.3 的适配器统一注册与调度接口。

使用方式::

    from whyfxpg.adapters.sources.registry import SourceRegistry, JapanCAAAdapter

    # 注册（应用启动时一次性执行）
    SourceRegistry.register(JapanCAAAdapter())

    # 查询
    adapter = SourceRegistry.get("japan_caa")
    pages = adapter.fetch()
    for page in pages:
        event = adapter.parse(page)

    # 遍历所有已注册适配器
    for adapter in SourceRegistry.all():
        print(adapter.source_id, adapter.source_name)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Self

if TYPE_CHECKING:
    from .japan_caa_adapter import JapanCAAAdapter  # noqa: F401

logger = logging.getLogger(__name__)


class SourceRegistry:
    """
    数据源适配器全局注册表（单例模式）。

    线程安全（基于字典的注册表，Python GIL 保证原子性）。
    """

    _instance: SourceRegistry | None = None
    _adapters: dict[str, object] | None = None

    def __new__(cls) -> Self:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._adapters = {}
        return cls._instance

    @classmethod
    def register(cls, adapter: object, source_id: str | None = None) -> None:
        """
        注册一个适配器实例。

        Args:
            adapter: 适配器实例（必须拥有 source_id 属性）。
            source_id: 可选，强制指定 source_id；否则从 adapter.source_id 读取。
        """
        sid = source_id or getattr(adapter, "source_id", None)
        if not sid:
            raise ValueError(
                f"Adapter {adapter!r} has no 'source_id' attribute and no source_id was provided"
            )
        cls._adapters[sid] = adapter
        logger.info("Registered source adapter: %s (%s)", sid, getattr(adapter, "source_name", ""))

    @classmethod
    def get(cls, source_id: str) -> object | None:
        """根据 source_id 获取已注册的适配器。"""
        return cls._adapters.get(source_id)

    @classmethod
    def all(cls) -> list[object]:
        """返回所有已注册的适配器列表。"""
        return list(cls._adapters.values())

    @classmethod
    def unregister(cls, source_id: str) -> None:
        """注销指定 source_id 的适配器。"""
        cls._adapters.pop(source_id, None)

    @classmethod
    def clear(cls) -> None:
        """清空注册表（主要用于测试）。"""
        cls._adapters.clear()

    @classmethod
    def registered_ids(cls) -> list[str]:
        """返回所有已注册的 source_id 列表。"""
        return list(cls._adapters.keys())

    @classmethod
    def auto_register_package_adapters(cls) -> None:
        """
        自动注册 whyfxpg.adapters.sources 包内所有已知适配器。

        当前已知适配器：
          - JapanCAAAdapter (japan_caa)

        后续新增适配器只需在此方法中添加 import 和 register 调用。
        """
        # JapanCAAAdapter
        try:
            from .japan_caa_adapter import JapanCAAAdapter

            cls.register(JapanCAAAdapter())
        except Exception as e:  # noqa: BLE001
            logger.warning("Failed to auto-register JapanCAAAdapter: %s", e)

        logger.info(
            "Auto-registered adapters: %s",
            cls.registered_ids(),
        )
