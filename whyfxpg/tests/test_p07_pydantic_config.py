"""P07: Pydantic 配置 Schema 校验测试。

覆盖 AC-1~AC-5：
- 三个 Pydantic 模型存在（RiskModelConfig/DimensionConfig/AlertRuleConfig）
- YAML 通过 Pydantic 校验加载；结构性错误拒绝启动（ConfigValidationError）
- 环境变量覆盖（RISK_MODEL__<PATH>，嵌套 __ 分隔）
- 字段级降级（单字段失败用默认值，不影响启动）
- risk_scorer.assess() 走 Pydantic 加载路径
"""

from pathlib import Path

import pytest
import yaml

from whyfxpg.config.pydantic_loader import ConfigValidationError, load_risk_model
from whyfxpg.config.pydantic_models import (
    AlertRuleConfig,
    DimensionConfig,
    RiskModelConfig,
)
from whyfxpg.core.risk_scorer import RiskScorer

MINIMAL_RISK_MODEL = {
    "version": "1.0",
    "severity_levels": {
        "灾难性": {"score": 100},
        "严重": {"default": 95},
        "中等": {"default": 60},
        "轻微": {"default": 15},
    },
    "probability_levels": {"可能": {"default": 95}, "不太可能": {"default": 60}},
    "country_factors": {"unknown": 1.0, "高风险国": 1.3},
    "product_factors": {"unknown": 1.0},
    "history_factor": {"formula": "1 + 0.1 * min(event_count_12m, 5)", "max": 1.5, "min": 1.0},
    "evidence_factors": {"unknown": 0.9},
    "risk_level_thresholds": {"S": 85, "M": 70, "L": 50, "A": 0},
}


def _write_risk_model(path: Path, data: dict) -> Path:
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return path


# ──────────────────────────────────────────────────────────────
# AC-1: 三个 Pydantic 模型
# ──────────────────────────────────────────────────────────────


def test_pydantic_models_defined() -> None:
    assert RiskModelConfig.model_fields["severity_levels"] is not None
    assert DimensionConfig.model_fields["weight"] is not None
    assert AlertRuleConfig.model_fields["enabled"] is not None


def test_pydantic_models_from_dict() -> None:
    cfg = RiskModelConfig.from_dict(MINIMAL_RISK_MODEL)
    assert cfg.severity_levels["中等"].default == 60
    dim = DimensionConfig.from_dict({"dimension_id": "d1", "weight": 2.0})
    assert dim.weight == 2.0
    rule = AlertRuleConfig.from_dict({"rule_id": "r1", "action": ["feishu"]})
    assert rule.action == ["feishu"]


# ──────────────────────────────────────────────────────────────
# AC-2: 校验通过加载 / 结构性错误拒绝启动
# ──────────────────────────────────────────────────────────────


def test_load_valid_yaml(tmp_path: Path) -> None:
    path = _write_risk_model(tmp_path / "risk_model.yaml", MINIMAL_RISK_MODEL)
    cfg = load_risk_model(path)
    assert cfg.version == "1.0"
    assert cfg.severity_levels["灾难性"].score == 100
    assert cfg.country_factors["高风险国"] == 1.3


def test_load_rejects_missing_severity_levels(tmp_path: Path) -> None:
    bad = {k: v for k, v in MINIMAL_RISK_MODEL.items() if k != "severity_levels"}
    path = _write_risk_model(tmp_path / "risk_model.yaml", bad)
    with pytest.raises(ConfigValidationError) as exc:
        load_risk_model(path)
    assert "severity_levels" in str(exc.value)


def test_load_rejects_empty_version(tmp_path: Path) -> None:
    bad = dict(MINIMAL_RISK_MODEL, version="")
    path = _write_risk_model(tmp_path / "risk_model.yaml", bad)
    with pytest.raises(ConfigValidationError) as exc:
        load_risk_model(path)
    assert "version" in str(exc.value)


# ──────────────────────────────────────────────────────────────
# AC-3: 环境变量覆盖
# ──────────────────────────────────────────────────────────────


def test_env_override_nested_field(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = _write_risk_model(tmp_path / "risk_model.yaml", MINIMAL_RISK_MODEL)
    monkeypatch.setenv("RISK_MODEL__HISTORY_FACTOR__MAX", "1.8")
    monkeypatch.setenv("RISK_MODEL__HISTORY_FACTOR__MIN", "1.1")
    cfg = load_risk_model(path)
    assert cfg.history_factor.max == 1.8
    assert cfg.history_factor.min == 1.1


def test_env_override_top_level_field(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = _write_risk_model(tmp_path / "risk_model.yaml", MINIMAL_RISK_MODEL)
    monkeypatch.setenv("RISK_MODEL__SCORE_FORMULA", "log")
    cfg = load_risk_model(path)
    assert cfg.score_formula == "log"


def test_env_override_json_value(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """数值/布尔/列表按 JSON 解析。"""
    path = _write_risk_model(tmp_path / "risk_model.yaml", MINIMAL_RISK_MODEL)
    monkeypatch.setenv("RISK_MODEL__RISK_LEVEL_THRESHOLDS__S", "90")
    cfg = load_risk_model(path)
    assert cfg.risk_level_thresholds["S"] == 90


# ──────────────────────────────────────────────────────────────
# AC-4: 降级策略
# ──────────────────────────────────────────────────────────────


def test_missing_field_uses_default(tmp_path: Path) -> None:
    """字段缺失 → 使用模型默认值，不拒绝启动。"""
    data = {k: v for k, v in MINIMAL_RISK_MODEL.items() if k != "description"}
    path = _write_risk_model(tmp_path / "risk_model.yaml", data)
    cfg = load_risk_model(path)
    assert cfg.description == ""


def test_wrong_type_field_falls_back_to_default(tmp_path: Path) -> None:
    """单字段类型错误 → 降级用默认值，不影响整体启动。"""
    bad = dict(MINIMAL_RISK_MODEL, country_factors="not-a-dict")
    path = _write_risk_model(tmp_path / "risk_model.yaml", bad)
    cfg = load_risk_model(path)
    assert cfg.country_factors == {}
    assert cfg.severity_levels["中等"].default == 60  # 其余字段正常


# ──────────────────────────────────────────────────────────────
# AC-5: risk_scorer 使用 Pydantic 模型
# ──────────────────────────────────────────────────────────────


def test_scorer_accepts_pydantic_model(tmp_path: Path) -> None:
    path = _write_risk_model(tmp_path / "risk_model.yaml", MINIMAL_RISK_MODEL)
    cfg = load_risk_model(path)
    scorer = RiskScorer(cfg)
    result = scorer.score(
        {"severity_level": "严重", "country": "高风险国", "product_category": "unknown"},
        historical_counts={"country_history_count": 0, "product_history_count": 0},
        causal_factor=1.0,
    )
    assert result.rs_level in ("S", "M", "L", "A")
    assert result.total_score > 0


def test_assess_uses_pydantic_loader(tmp_path: Path) -> None:
    """assess() 静态接口经 Pydantic 校验加载（不再直接读 YAML）。"""
    path = _write_risk_model(tmp_path / "risk_model.yaml", MINIMAL_RISK_MODEL)
    result = RiskScorer.assess(
        event={"severity_level": "严重", "country": "高风险国"},
        historical_counts={"country_history_count": 0, "product_history_count": 0},
        config_path=str(path),
    )
    assert result.rs_level in ("S", "M", "L", "A")
