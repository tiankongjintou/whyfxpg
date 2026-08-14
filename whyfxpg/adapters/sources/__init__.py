"""
Source adapters package.
"""

from whyfxpg.ports.source_adapter import SourceRegistry

from .australia_acc_adapter import AustraliaACCCAdapter
from .brazil_anvisa_adapter import BrazilANVISAAdapter
from .canada_health_adapter import CanadaHealthAdapter
from .http_source_adapter import HttpSourceAdapter
from .in_memory_source_adapter import InMemorySourceAdapter
from .india_bis_adapter import IndiaBISAdapter
from .japan_caa_adapter import JapanCAAAdapter
from .korea_safety_adapter import KoreaSafetyAdapter
from .mexico_profeco_adapter import MexicoPROFECOAdapter
from .new_zealand_mvc_adapter import NewZealandMVCAdapter
from .saudi_sfda_adapter import SaudiSFDAAdapter
from .singapore_cpss_adapter import SingaporeCPSSAdapter

# 注册内置适配器（确保注册表非空）
_agents = [
    AustraliaACCCAdapter,
    BrazilANVISAAdapter,
    CanadaHealthAdapter,
    IndiaBISAdapter,
    JapanCAAAdapter,
    KoreaSafetyAdapter,
    MexicoPROFECOAdapter,
    NewZealandMVCAdapter,
    SaudiSFDAAdapter,
    SingaporeCPSSAdapter,
]
for _cls in _agents:
    try:
        SourceRegistry.register(_cls())
    except ValueError:
        pass  # 已注册

__all__ = [
    "AustraliaACCCAdapter",
    "BrazilANVISAAdapter",
    "CanadaHealthAdapter",
    "HttpSourceAdapter",
    "InMemorySourceAdapter",
    "IndiaBISAdapter",
    "JapanCAAAdapter",
    "KoreaSafetyAdapter",
    "MexicoPROFECOAdapter",
    "NewZealandMVCAdapter",
    "SaudiSFDAAdapter",
    "SingaporeCPSSAdapter",
    "SourceRegistry",
]
