"""RiskScorer 纯评分策略测试。

测试 seam：RiskScorer.score(event, historical_counts, causal_factor)。
输入事件 + 历史统计 + 因果因子，输出 ScoringResult。
无需数据库，因此全部使用内存 fixture。
"""

import math

import pytest

from whyfxpg.config.pydantic_models import RiskModelConfig
from whyfxpg.core.risk_scorer import RiskScorer, ScoringResult


@pytest.fixture
def model_cfg() -> RiskModelConfig:
    return RiskModelConfig.from_dict(
        {
            "version": "1.0",
            "severity_levels": {
                "灾难性": {"score": 100},
                "严重": {"default": 95},
                "中等": {"default": 60},
                "轻微": {"default": 15},
            },
            "probability_levels": {
                "非常可能": {"score": 100},
                "可能": {"default": 95},
                "不太可能": {"default": 60},
                "几乎不可能": {"default": 15},
            },
            "country_factors": {"unknown": 1.0, "测试国": 1.0, "高风险国": 1.3},
            "product_factors": {"unknown": 1.0, "普通机电": 1.0, "儿童相关产品": 1.3},
            "history_factor": {"formula": "1 + 0.1 * min(event_count_12m, 5)", "max": 1.5, "min": 1.0},
            "evidence_factors": {"test_api": 1.0, "news": 0.9, "unknown": 0.9},
            "risk_level_thresholds": {"S": 8000, "M": 3000, "L": 1000, "A": 0},
        }
    )


@pytest.fixture
def scorer(model_cfg: RiskModelConfig) -> RiskScorer:
    return RiskScorer(model_cfg)


def test_severity_to_score_returns_exact_score(scorer: RiskScorer) -> None:
    assert scorer.severity_to_score("中等") == 60
    assert scorer.severity_to_score("灾难性") == 100


def test_severity_to_score_falls_back_to_default(scorer: RiskScorer) -> None:
    # 配置中不存在的等级，回退到默认键
    assert scorer.severity_to_score("不存在") == 60


def test_probability_to_score_by_history_density(scorer: RiskScorer) -> None:
    event = {"country": "测试国"}
    assert scorer.probability_to_score(event, history_count=0) == 95
    assert scorer.probability_to_score(event, history_count=1) == 60
    assert scorer.probability_to_score(event, history_count=2) == 95
    assert scorer.probability_to_score(event, history_count=5) == 100


def test_country_factor_and_product_factor_lookups(scorer: RiskScorer) -> None:
    assert scorer.country_factor("高风险国") == 1.3
    assert scorer.country_factor("未知国") == 1.0
    assert scorer.product_factor("儿童相关产品") == 1.3
    assert scorer.product_factor("未知类别") == 1.0


def test_history_factor_caps_at_max(scorer: RiskScorer) -> None:
    assert scorer.history_factor(0) == 1.0
    assert scorer.history_factor(3) == 1.3
    assert scorer.history_factor(10) == 1.5


def test_evidence_factor_lookup(scorer: RiskScorer) -> None:
    assert scorer.evidence_factor("test_api") == 1.0
    assert scorer.evidence_factor("unknown") == 0.9


def test_map_to_risk_level_thresholds(scorer: RiskScorer) -> None:
    assert scorer.map_to_risk_level(9000) == "S"
    assert scorer.map_to_risk_level(5000) == "M"
    assert scorer.map_to_risk_level(1500) == "L"
    assert scorer.map_to_risk_level(500) == "A"


def test_score_computes_total_and_risk_level(scorer: RiskScorer) -> None:
    event = {
        "severity_level": "中等",
        "country": "测试国",
        "product_category": "普通机电",
        "source_id": "test_api",
    }
    result = scorer.score(
        event,
        historical_counts={"country_history_count": 0, "product_history_count": 0},
        causal_factor=1.0,
    )

    assert isinstance(result, ScoringResult)
    assert result.ss_score == 60
    assert result.ps_score == 95
    assert result.country_factor == 1.0
    assert result.product_factor == 1.0
    assert result.history_factor == 1.0
    assert result.evidence_factor == 1.0
    assert result.causal_factor == 1.0
    assert result.total_score == pytest.approx(60 * 95 * 1.0 * 1.0 * 1.0 * 1.0)
    assert result.rs_level == "M"
    assert result.probability_level == "可能"


def test_score_applies_causal_factor(scorer: RiskScorer) -> None:
    event = {
        "severity_level": "中等",
        "country": "测试国",
        "product_category": "普通机电",
        "source_id": "test_api",
    }
    result = scorer.score(
        event,
        historical_counts={"country_history_count": 0, "product_history_count": 0},
        causal_factor=2.0,
    )

    assert result.causal_factor == 2.0
    assert result.total_score == pytest.approx(60 * 95 * 2.0)


def test_score_with_high_density_history_changes_probability(scorer: RiskScorer) -> None:
    event = {
        "severity_level": "中等",
        "country": "测试国",
        "product_category": "普通机电",
        "source_id": "test_api",
    }
    result = scorer.score(
        event,
        historical_counts={"country_history_count": 5, "product_history_count": 3},
        causal_factor=1.0,
    )

    assert result.ps_score == 100
    assert result.probability_level == "非常可能"
    assert result.history_factor == 1.3


def test_score_minimum_total_maps_to_level_a(scorer: RiskScorer) -> None:
    event = {
        "severity_level": "轻微",
        "country": "测试国",
        "product_category": "普通机电",
        "source_id": "test_api",
    }
    # history_count=1 使概率降为 60，总分 < 1000，落在 A 级
    result = scorer.score(
        event,
        historical_counts={"country_history_count": 1, "product_history_count": 0},
        causal_factor=1.0,
    )

    assert result.ss_score == 15
    assert result.ps_score == 60
    assert result.total_score == pytest.approx(15 * 60)
    assert result.rs_level == "A"


# ──────────────────────────────────────────────────────────────
# TD01: 对数化公式 log_score = Σlog(1+factor) 防乘法溢出
# ──────────────────────────────────────────────────────────────


def test_calculate_total_score_equivalent_to_multiplication(scorer: RiskScorer) -> None:
    """正常范围内,对数化公式与原乘法公式等效(误差 < 0.1%)。"""
    cases = [
        (60, 95, 1.0, 1.0, 1.0, 1.0),
        (100, 100, 1.3, 1.3, 1.5, 0.9),
        (15, 60, 2.0, 1.5, 1.2, 1.1),
        (95, 100, 0.8, 1.0, 1.0, 0.9),
    ]
    for ss, ps, cf, pf, hf, ef in cases:
        expected = ss * ps * cf * pf * hf * ef
        actual = scorer.calculate_total_score(ss, ps, cf, pf, hf, ef)
        assert math.isfinite(actual)
        assert math.isclose(actual, expected, rel_tol=1e-6)  # 远小于 0.1%


def test_calculate_total_score_extreme_no_intermediate_overflow(
    scorer: RiskScorer,
) -> None:
    """极端 case:中间乘积会溢出 float(1e200*1e200=inf),对数域仍稳定输出合理值。"""
    total = scorer.calculate_total_score(
        ss=10 ** 200,
        ps=10 ** 200,
        country_factor=1e-100,
        product_factor=1e-100,
        history_factor=1e-100,
        evidence_factor=1e-100,
    )
    assert math.isfinite(total)
    # 1e200 * 1e200 * (1e-100)^4 = 1.0
    assert math.isclose(total, 1.0, rel_tol=1e-6)


def test_calculate_total_score_extreme_max_weights(scorer: RiskScorer) -> None:
    """极端 case:所有因子权重最大(severity=1.5, probability=1.5, country=2.0, category=1.5)时稳定输出合理值。"""
    # 分数模型下 severity/probability 以最高分 100 表示,系数取 ticket 中的最大值
    total = scorer.calculate_total_score(
        ss=100,
        ps=100,
        country_factor=2.0,
        product_factor=1.5,
        history_factor=1.5,
        evidence_factor=1.5,
    )
    expected = 100 * 100 * 2.0 * 1.5 * 1.5 * 1.5
    assert math.isfinite(total)
    assert math.isclose(total, expected, rel_tol=1e-6)


def test_calculate_total_score_zero_factor_contribution(scorer: RiskScorer) -> None:
    """边界 case:系数=1(增量 factor=0)时 log(1+0)=0,不贡献;系数=0 时整体为 0。"""
    # 全部系数为 1 → 结果等于 ss*ps
    total = scorer.calculate_total_score(60, 95, 1.0, 1.0, 1.0, 1.0)
    assert math.isclose(total, 60 * 95, rel_tol=1e-9)
    # 任一系数为 0 → 整体 0(与旧公式乘以 0 一致)
    total_zero = scorer.calculate_total_score(60, 95, 0.0, 1.0, 1.0, 1.0)
    assert total_zero == 0.0
