"""
Source adapters package.
"""

from whyfxpg.ports.source_adapter import SourceRegistry

from .canada_health_adapter import CanadaHealthAdapter
from .http_source_adapter import HttpSourceAdapter
from .in_memory_source_adapter import InMemorySourceAdapter
from .japan_caa_adapter import JapanCAAAdapter
from .singapore_cpss_adapter import SingaporeCPSSAdapter

# 注册内置适配器（确保注册表非空）
try:
    SourceRegistry.register(CanadaHealthAdapter())
except ValueError:
    pass  # 已注册
try:
    SourceRegistry.register(JapanCAAAdapter())
except ValueError:
    pass
try:
    SourceRegistry.register(SingaporeCPSSAdapter())
except ValueError:
    pass

__all__ = [
    "CanadaHealthAdapter",
    "HttpSourceAdapter",
    "InMemorySourceAdapter",
    "JapanCAAAdapter",
    "SingaporeCPSSAdapter",
    "SourceRegistry",
]
