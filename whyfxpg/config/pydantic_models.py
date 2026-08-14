"""Pydantic 配置模型（P07）。

用 Pydantic v2 BaseModel 定义业务配置的强类型 Schema，替代裸 dict 访问：

- ``RiskModelConfig``：风险模型配置（severity/probability 等级、各类系数、阈值）
- ``DimensionConfig``：风险维度配置（dimensions.yaml）
- ``AlertRuleConfig``：预警规则配置（alert_rules.yaml）

设计决策：
- 所有字段提供默认值 → 字段缺失时**降级**用默认值（AC-4），不影响整体启动；
- ``RiskModelConfig`` 提供 ``after`` 校验：关键字段（version/severity_levels）
  为空时**拒绝启动**（AC-2），抛出带明确字段路径的 ValueError；
- 提供 ``from_dict`` 兼容接口，与既有 dataclass 版调用方式一致。
"""

from typing import Any

from pydantic import BaseModel, Field, model_validator

# ──────────────────────────────────────────────────────────────
# 风险模型（risk_model.yaml）
# ──────────────────────────────────────────────────────────────


class LevelConfig(BaseModel):
    """severity_levels / probability_levels 中的单个等级配置。"""

    score: int | None = None
    min: int = 0
    max: int = 100
    default: int = 0
    description: str = ""


class RiskMatrixConfig(BaseModel):
    columns: list[str] = Field(default_factory=list)
    rows: dict[str, list[str]] = Field(default_factory=dict)


class HistoryFactorConfig(BaseModel):
    formula: str = "1"
    max: float = 1.0
    min: float = 1.0


class RecencyDecayConfig(BaseModel):
    """时效衰减配置（P1b-05）。"""

    half_life_days: int = 90
    window_days: int = 0  # 0 = 不限制
    enabled: bool = True

    model_config = {"extra": "ignore"}  # 忽略 YAML 中未声明的额外字段


class RiskModelConfig(BaseModel):
    """风险模型配置（对应 Config/risk_model.yaml）。"""

    version: str = "1.0"
    domain_id: str = "default"
    version_id: str = ""
    model_name: str = ""
    description: str = ""
    updated_at: str = ""
    updated_by: str = ""

    severity_levels: dict[str, LevelConfig] = Field(default_factory=dict)
    probability_levels: dict[str, LevelConfig] = Field(default_factory=dict)
    risk_matrix: RiskMatrixConfig = Field(default_factory=RiskMatrixConfig)

    country_factors: dict[str, float] = Field(default_factory=dict)
    product_factors: dict[str, float] = Field(default_factory=dict)
    product_category_keywords: dict[str, list[str]] = Field(default_factory=dict)

    history_factor: HistoryFactorConfig = Field(default_factory=HistoryFactorConfig)
    recency_decay: RecencyDecayConfig = Field(default_factory=RecencyDecayConfig)
    evidence_factors: dict[str, float] = Field(default_factory=dict)
    risk_level_thresholds: dict[str, int] = Field(default_factory=dict)
    score_formula: str = "base"

    @model_validator(mode="after")
    def _check_critical_fields(self) -> "RiskModelConfig":
        """关键字段缺失 → 拒绝启动（AC-2）。"""
        if not self.version:
            raise ValueError("risk_model: 缺少必填字段 'version'")
        if not self.severity_levels:
            raise ValueError("risk_model: 缺少必填字段 'severity_levels'（至少一个严重度等级）")
        return self

    @classmethod
    def from_dict(cls, data: Any) -> "RiskModelConfig":
        """从 dict 构造（兼容既有调用方式）。"""
        if not isinstance(data, dict):
            data = {}
        return cls.model_validate(data)


# ──────────────────────────────────────────────────────────────
# 风险维度（dimensions.yaml）
# ──────────────────────────────────────────────────────────────


class DimensionConfig(BaseModel):
    """风险维度配置。"""

    dimension_id: str = ""
    domain_id: str = "default"
    version_id: str = ""
    name: str = ""
    description: str = ""
    dimension_type: str = "categorical"  # categorical | numeric | temporal
    source_field: str = ""  # risk_events 中用于计算该维度的字段
    weight: float = 1.0
    aggregation: str = "count"  # count | sum | distinct | max | custom
    parameters: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Any) -> "DimensionConfig":
        if not isinstance(data, dict):
            data = {}
        return cls.model_validate(data)


# ──────────────────────────────────────────────────────────────
# 预警规则（alert_rules.yaml）
# ──────────────────────────────────────────────────────────────


class AlertRuleConfig(BaseModel):
    """预警规则配置。"""

    rule_id: str = ""
    domain_id: str = "default"
    version_id: str = ""
    name: str = ""
    enabled: bool = True
    description: str = ""
    condition: dict[str, Any] = Field(default_factory=dict)
    severity: str = "medium"
    action: list[str] = Field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Any) -> "AlertRuleConfig":
        if not isinstance(data, dict):
            data = {}
        return cls.model_validate(data)
