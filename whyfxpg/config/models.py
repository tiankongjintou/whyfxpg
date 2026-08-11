"""类型化配置模型（基于标准库 dataclasses）。

将 YAML 配置从裸 dict 转换为带字段提示的结构化对象，
保留运行时回退默认值，避免 KeyError 导致的硬失败。
"""

from dataclasses import dataclass, field
from typing import Any


def _asdict(obj: Any) -> Any:
    """递归将 dataclass 实例转为 dict，跳过非导出字段（如 repr=False 的 extra 保留）。"""
    if isinstance(obj, list):
        return [_asdict(i) for i in obj]
    if isinstance(obj, dict):
        return {str(k): _asdict(v) for k, v in obj.items()}
    if hasattr(obj, "__dataclass_fields__"):
        # 手动构建，避免 dataclasses.asdict 深度递归中暴露内部锁等不可序列化对象
        return {k: _asdict(getattr(obj, k)) for k in obj.__dataclass_fields__}
    return obj
def _as_str(value: Any, default: str = "") -> str:
    return str(value) if value is not None else default


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {"true", "1", "yes", "on"}
    return bool(value)


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)]


def _as_str_dict(value: Any) -> dict[str, str]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return {str(k): str(v) for k, v in value.items()}
    return {}


def _as_str_list_dict(value: Any) -> dict[str, list[str]]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return {str(k): _as_list(v) for k, v in value.items()}
    return {}


# ──────────────────────────────────────────────────────────────
# risk_model.yaml
# ──────────────────────────────────────────────────────────────

@dataclass
class LevelConfig:
    """severity_levels / probability_levels 中的单个等级配置。"""

    score: int | None = None
    min: int = 0
    max: int = 100
    default: int = 0
    description: str = ""

    @classmethod
    def from_dict(cls, d: Any) -> "LevelConfig":
        if not isinstance(d, dict):
            d = {}
        return cls(
            score=_as_int(d.get("score"), 0) or None,
            min=_as_int(d.get("min"), 0),
            max=_as_int(d.get("max"), 100),
            default=_as_int(d.get("default"), 0),
            description=_as_str(d.get("description")),
        )


@dataclass
class RiskMatrixConfig:
    columns: list[str] = field(default_factory=list)
    rows: dict[str, list[str]] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: Any) -> "RiskMatrixConfig":
        if not isinstance(d, dict):
            d = {}
        rows = d.get("rows", {}) or {}
        return cls(
            columns=_as_list(d.get("columns")),
            rows={str(k): _as_list(v) for k, v in rows.items()},
        )


@dataclass
class HistoryFactorConfig:
    formula: str = "1"
    max: float = 1.0
    min: float = 1.0

    @classmethod
    def from_dict(cls, d: Any) -> "HistoryFactorConfig":
        if not isinstance(d, dict):
            d = {}
        return cls(
            formula=_as_str(d.get("formula"), "1"),
            max=_as_float(d.get("max"), 1.0),
            min=_as_float(d.get("min"), 1.0),
        )


@dataclass
class RiskModelConfig:
    version: str = "1.0"
    domain_id: str = ""
    version_id: str = ""
    model_name: str = ""
    description: str = ""
    updated_at: str = ""
    updated_by: str = ""

    severity_levels: dict[str, LevelConfig] = field(default_factory=dict)
    probability_levels: dict[str, LevelConfig] = field(default_factory=dict)
    risk_matrix: RiskMatrixConfig = field(default_factory=RiskMatrixConfig)

    country_factors: dict[str, float] = field(default_factory=dict)
    product_factors: dict[str, float] = field(default_factory=dict)
    product_category_keywords: dict[str, list[str]] = field(default_factory=dict)

    history_factor: HistoryFactorConfig = field(default_factory=HistoryFactorConfig)
    evidence_factors: dict[str, float] = field(default_factory=dict)
    risk_level_thresholds: dict[str, int] = field(default_factory=dict)
    score_formula: str = "base"

    @classmethod
    def from_dict(cls, d: Any) -> "RiskModelConfig":
        if not isinstance(d, dict):
            d = {}

        def _level_map(data: Any) -> dict[str, LevelConfig]:
            if not isinstance(data, dict):
                return {}
            return {str(k): LevelConfig.from_dict(v) for k, v in data.items()}

        return cls(
            version=_as_str(d.get("version"), "1.0"),
            domain_id=_as_str(d.get("domain_id"), "default"),
            version_id=_as_str(d.get("version_id")),
            model_name=_as_str(d.get("model_name")),
            description=_as_str(d.get("description")),
            updated_at=_as_str(d.get("updated_at")),
            updated_by=_as_str(d.get("updated_by")),
            severity_levels=_level_map(d.get("severity_levels")),
            probability_levels=_level_map(d.get("probability_levels")),
            risk_matrix=RiskMatrixConfig.from_dict(d.get("risk_matrix")),
            country_factors={str(k): _as_float(v, 1.0) for k, v in (d.get("country_factors") or {}).items()},
            product_factors={str(k): _as_float(v, 1.0) for k, v in (d.get("product_factors") or {}).items()},
            product_category_keywords=_as_str_list_dict(d.get("product_category_keywords")),
            history_factor=HistoryFactorConfig.from_dict(d.get("history_factor")),
            evidence_factors={str(k): _as_float(v, 1.0) for k, v in (d.get("evidence_factors") or {}).items()},
            risk_level_thresholds={str(k): _as_int(v, 0) for k, v in (d.get("risk_level_thresholds") or {}).items()},
            score_formula=_as_str(d.get("score_formula"), "base"),
        )


# ──────────────────────────────────────────────────────────────
# sources.yaml
# ──────────────────────────────────────────────────────────────

@dataclass
class SourceConfig:
    source_id: str = ""
    domain_id: str = ""
    version_id: str = ""
    name: str = ""
    url: str = ""
    fallback_url: str = ""
    source_type: str = "web"
    enabled: bool = True
    priority: int = 1
    check_interval: str = "1d"
    fetch_method: str = "static"
    parser: str = "html_list"
    keywords_ref: str = "default"
    delay: int = 2
    headers: dict[str, str] = field(default_factory=dict)
    selector: dict[str, str] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict, repr=False)

    def to_dict(self) -> dict[str, Any]:
        """递归转换为 dict，兼容当前仍使用 dict 接口的 adapter。"""
        return _asdict(self)

    @classmethod
    def from_dict(cls, source_id: str, d: Any) -> "SourceConfig":
        if not isinstance(d, dict):
            d = {}
        known = {
            "source_id", "name", "url", "fallback_url", "source_type", "enabled", "priority",
            "check_interval", "fetch_method", "parser", "keywords_ref",
            "delay", "headers", "selector",
        }
        extra = {k: v for k, v in d.items() if k not in known}
        return cls(
            source_id=source_id,
            domain_id=_as_str(d.get("domain_id"), "default"),
            version_id=_as_str(d.get("version_id")),
            name=_as_str(d.get("name")),
            url=_as_str(d.get("url")),
            fallback_url=_as_str(d.get("fallback_url")),
            source_type=_as_str(d.get("source_type"), "web"),
            enabled=_as_bool(d.get("enabled"), True),
            priority=_as_int(d.get("priority"), 1),
            check_interval=_as_str(d.get("check_interval"), "1d"),
            fetch_method=_as_str(d.get("fetch_method"), "static"),
            parser=_as_str(d.get("parser"), "html_list"),
            keywords_ref=_as_str(d.get("keywords_ref"), "default"),
            delay=_as_int(d.get("delay"), 2),
            headers=_as_str_dict(d.get("headers")),
            selector=_as_str_dict(d.get("selector")),
            extra=extra,
        )


@dataclass
class SourcesConfig:
    version: str = "1.0"
    domain_id: str = ""
    version_id: str = ""
    description: str = ""
    updated_at: str = ""
    updated_by: str = ""
    sources: dict[str, SourceConfig] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: Any) -> "SourcesConfig":
        if not isinstance(d, dict):
            d = {}
        raw_sources = d.get("sources") or {}
        return cls(
            version=_as_str(d.get("version"), "1.0"),
            domain_id=_as_str(d.get("domain_id"), "default"),
            version_id=_as_str(d.get("version_id")),
            description=_as_str(d.get("description")),
            updated_at=_as_str(d.get("updated_at")),
            updated_by=_as_str(d.get("updated_by")),
            sources={str(k): SourceConfig.from_dict(str(k), v) for k, v in raw_sources.items()},
        )

    def enabled_sources(self) -> list[SourceConfig]:
        """返回启用的来源配置列表。"""
        return [cfg for cfg in self.sources.values() if cfg.enabled]


# ──────────────────────────────────────────────────────────────
# alert_rules.yaml
# ──────────────────────────────────────────────────────────────

@dataclass
class AlertRule:
    rule_id: str = ""
    domain_id: str = ""
    version_id: str = ""
    name: str = ""
    enabled: bool = True
    description: str = ""
    condition: dict[str, Any] = field(default_factory=dict)
    severity: str = "medium"
    action: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: Any) -> "AlertRule":
        if not isinstance(d, dict):
            d = {}
        return cls(
            rule_id=_as_str(d.get("rule_id")),
            domain_id=_as_str(d.get("domain_id"), "default"),
            version_id=_as_str(d.get("version_id")),
            name=_as_str(d.get("name")),
            enabled=_as_bool(d.get("enabled"), True),
            description=_as_str(d.get("description")),
            condition=d.get("condition") or {},
            severity=_as_str(d.get("severity"), "medium"),
            action=_as_list(d.get("action")),
        )


@dataclass
class AlertRulesConfig:
    version: str = "1.0"
    domain_id: str = ""
    version_id: str = ""
    description: str = ""
    updated_at: str = ""
    updated_by: str = ""
    rules: list[AlertRule] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: Any) -> "AlertRulesConfig":
        if not isinstance(d, dict):
            d = {}
        raw_rules = d.get("rules") or []
        return cls(
            version=_as_str(d.get("version"), "1.0"),
            domain_id=_as_str(d.get("domain_id"), "default"),
            version_id=_as_str(d.get("version_id")),
            description=_as_str(d.get("description")),
            updated_at=_as_str(d.get("updated_at")),
            updated_by=_as_str(d.get("updated_by")),
            rules=[AlertRule.from_dict(r) for r in raw_rules if isinstance(r, dict)],
        )

    def enabled_rules(self) -> list[AlertRule]:
        """返回启用的规则列表。"""
        return [r for r in self.rules if r.enabled]


# ──────────────────────────────────────────────────────────────
# extract_rules.yaml
# ──────────────────────────────────────────────────────────────

@dataclass
class ExtractRule:
    rule_id: str = ""
    name: str = ""
    applies_to: list[str] = field(default_factory=list)
    field_name: str = ""
    method: str = "selector"
    selector: str = ""
    patterns: list[str] = field(default_factory=list)
    transform: str = ""
    fallback: str | None = ""
    default: str = ""
    map: dict[str, list[str]] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: Any) -> "ExtractRule":
        if not isinstance(d, dict):
            d = {}
        return cls(
            rule_id=_as_str(d.get("rule_id")),
            name=_as_str(d.get("name")),
            applies_to=_as_list(d.get("applies_to")),
            field_name=_as_str(d.get("field")),
            method=_as_str(d.get("method"), "selector"),
            selector=_as_str(d.get("selector")),
            patterns=_as_list(d.get("patterns")),
            transform=_as_str(d.get("transform")),
            fallback=d.get("fallback") if d.get("fallback") is not None else "",
            default=_as_str(d.get("default")),
            map=_as_str_list_dict(d.get("map")),
        )


@dataclass
class ExtractRulesConfig:
    version: str = "1.0"
    domain_id: str = ""
    version_id: str = ""
    description: str = ""
    updated_at: str = ""
    updated_by: str = ""
    rules: list[ExtractRule] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: Any) -> "ExtractRulesConfig":
        if not isinstance(d, dict):
            d = {}
        raw_rules = d.get("rules") or []
        return cls(
            version=_as_str(d.get("version"), "1.0"),
            domain_id=_as_str(d.get("domain_id"), "default"),
            version_id=_as_str(d.get("version_id")),
            description=_as_str(d.get("description")),
            updated_at=_as_str(d.get("updated_at")),
            updated_by=_as_str(d.get("updated_by")),
            rules=[ExtractRule.from_dict(r) for r in raw_rules if isinstance(r, dict)],
        )


# ──────────────────────────────────────────────────────────────
# v2: dimensions.yaml + taxonomies.yaml
# ──────────────────────────────────────────────────────────────


@dataclass
class RiskDimension:
    dimension_id: str = ""
    domain_id: str = ""
    version_id: str = ""
    name: str = ""
    description: str = ""
    dimension_type: str = "categorical"  # categorical | numeric | temporal
    source_field: str = ""  # field in risk_events used to compute this dimension
    weight: float = 1.0
    aggregation: str = "count"  # count | sum | distinct | max | custom
    parameters: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, d: Any) -> "RiskDimension":
        if not isinstance(d, dict):
            d = {}
        return cls(
            dimension_id=_as_str(d.get("dimension_id")),
            domain_id=_as_str(d.get("domain_id"), "default"),
            version_id=_as_str(d.get("version_id")),
            name=_as_str(d.get("name")),
            description=_as_str(d.get("description")),
            dimension_type=_as_str(d.get("dimension_type"), "categorical"),
            source_field=_as_str(d.get("source_field")),
            weight=_as_float(d.get("weight"), 1.0),
            aggregation=_as_str(d.get("aggregation"), "count"),
            parameters=d.get("parameters") or {},
        )


@dataclass
class TaxonomyNode:
    taxonomy_id: str = ""  # top-level taxonomy identifier
    domain_id: str = ""
    version_id: str = ""
    node_id: str = ""  # unique node id (e.g. HS code)
    parent_id: str | None = None
    name: str = ""
    aliases: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    attributes: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, d: Any) -> "TaxonomyNode":
        if not isinstance(d, dict):
            d = {}
        return cls(
            taxonomy_id=_as_str(d.get("taxonomy_id")),
            domain_id=_as_str(d.get("domain_id"), "default"),
            version_id=_as_str(d.get("version_id")),
            node_id=_as_str(d.get("node_id")),
            parent_id=d.get("parent_id") if d.get("parent_id") is not None else None,
            name=_as_str(d.get("name")),
            aliases=_as_list(d.get("aliases")),
            keywords=_as_list(d.get("keywords")),
            attributes=d.get("attributes") or {},
        )


@dataclass
class KeywordSet:
    description: str = ""
    categories: dict[str, list[str]] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: Any) -> "KeywordSet":
        if not isinstance(d, dict):
            d = {}
        cats = d.get("categories") or {}
        return cls(
            description=_as_str(d.get("description")),
            categories=_as_str_list_dict(cats),
        )


@dataclass
class KeywordsConfig:
    version: str = "1.0"
    domain_id: str = ""
    version_id: str = ""
    description: str = ""
    updated_at: str = ""
    updated_by: str = ""
    keyword_sets: dict[str, KeywordSet] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: Any) -> "KeywordsConfig":
        if not isinstance(d, dict):
            d = {}
        sets = d.get("keyword_sets") or {}
        return cls(
            version=_as_str(d.get("version"), "1.0"),
            domain_id=_as_str(d.get("domain_id"), "default"),
            version_id=_as_str(d.get("version_id")),
            description=_as_str(d.get("description")),
            updated_at=_as_str(d.get("updated_at")),
            updated_by=_as_str(d.get("updated_by")),
            keyword_sets={str(k): KeywordSet.from_dict(v) for k, v in sets.items()},
        )
