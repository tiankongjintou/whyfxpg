"""
基础配置加载模块

功能：
- 加载所有YAML配置文件
- 提供统一配置访问接口
- 使用Pydantic进行校验（可选）

输入：config目录
输出：配置对象
"""

from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

import yaml

from whyfxpg.config.models import (
    AlertRulesConfig,
    ExtractRulesConfig,
    KeywordsConfig,
    SourcesConfig,
)
from whyfxpg.config.pydantic_loader import load_risk_model
from whyfxpg.config.pydantic_models import RiskModelConfig

if TYPE_CHECKING:
    from whyfxpg.core.domain_profile import DomainProfile

DEFAULT_CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config"


def load_yaml(path: Path) -> dict[str, Any]:
    """加载单个YAML文件"""
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


class ConfigLoader:
    """统一配置加载器"""

    def __init__(self, config_dir: str | None = None):
        self.config_dir = Path(config_dir) if config_dir else DEFAULT_CONFIG_DIR
        self._cache = {}

    def _path(self, filename: str) -> Path:
        return self.config_dir / filename

    def load(self, filename: str) -> dict[str, Any]:
        """加载指定配置文件，带缓存"""
        if filename not in self._cache:
            self._cache[filename] = load_yaml(self._path(filename))
        return self._cache[filename]

    def reload(self, filename: str) -> dict[str, Any]:
        """重新加载配置文件"""
        self._cache.pop(filename, None)
        return self.load(filename)

    def reload_all(self) -> None:
        """重新加载所有配置"""
        self._cache.clear()

    @property
    def sources(self) -> dict[str, Any]:
        return self.load("sources.yaml")

    @property
    def keywords(self) -> dict[str, Any]:
        return self.load("keywords.yaml")

    @property
    def extract_rules(self) -> dict[str, Any]:
        return self.load("extract_rules.yaml")

    @property
    def risk_model(self) -> dict[str, Any]:
        return self.load("risk_model.yaml")

    @property
    def alert_rules(self) -> dict[str, Any]:
        return self.load("alert_rules.yaml")

    @property
    def version_history(self) -> dict[str, Any]:
        return self.load("version_history.yaml")

    # ── 类型化配置访问（Phase 4D） ────────────────────────────────────

    @property
    def typed_risk_model(self) -> RiskModelConfig:
        """Pydantic 校验后的风险模型配置（P07：环境变量覆盖 + 降级 + 拒绝启动）。"""
        return load_risk_model(self._path("risk_model.yaml"))

    @property
    def typed_sources(self) -> SourcesConfig:
        return SourcesConfig.from_dict(self.load("sources.yaml"))

    @property
    def typed_alert_rules(self) -> AlertRulesConfig:
        return AlertRulesConfig.from_dict(self.load("alert_rules.yaml"))

    @property
    def typed_extract_rules(self) -> ExtractRulesConfig:
        return ExtractRulesConfig.from_dict(self.load("extract_rules.yaml"))

    @property
    def typed_keywords(self) -> KeywordsConfig:
        return KeywordsConfig.from_dict(self.load("keywords.yaml"))

    @property
    def typed_domains(self) -> list["DomainProfile"]:
        """Return all configured domain profiles."""
        from whyfxpg.services.domain_registry import DomainRegistryService

        return DomainRegistryService(self.config_dir).list()

    @property
    def typed_active_domain(self) -> Optional["DomainProfile"]:
        """Return the currently active domain profile."""
        from whyfxpg.services.domain_registry import DomainRegistryService

        return DomainRegistryService(self.config_dir).active()


# 全局配置实例
_config_loader: ConfigLoader | None = None


def get_config(config_dir: str | None = None) -> ConfigLoader:
    """获取全局配置加载器"""
    global _config_loader
    if _config_loader is None or config_dir is not None:
        _config_loader = ConfigLoader(config_dir)
    return _config_loader
