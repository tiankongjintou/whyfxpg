"""RiskScorer 时效分衰减曲线测试（P1b-05）。

测试 seam：RiskScorer.recency_decay_factor() + score() 集成。
覆盖：
- 当天事件 decay_factor ≈ 1.0
- 半衰期后天事件 decay_factor ≈ 0.5
- 3×半衰期（270天）事件 decay_factor ≈ 0.125
- 空日期/解析失败 → 1.0
- enabled=False → 1.0
- half_life≤0 → 1.0
"""

import math
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from whyfxpg.config.pydantic_models import RiskModelConfig
from whyfxpg.core.risk_scorer import RiskScorer


def _make_cfg(half_life_days: int = 90, window_days: int = 0, enabled: bool = True) -> RiskModelConfig:
    return RiskModelConfig.from_dict({
        "version": "1.0",
        "severity_levels": {
            "中等": {"default": 60},
        },
        "probability_levels": {
            "可能": {"default": 95},
        },
        "country_factors": {"测试国": 1.0},
        "product_factors": {"普通机电": 1.0},
        "history_factor": {"formula": "1", "max": 1.0, "min": 1.0},
        "recency_decay": {
            "half_life_days": half_life_days,
            "window_days": window_days,
            "enabled": enabled,
        },
        "evidence_factors": {"test_api": 1.0},
        "risk_level_thresholds": {"S": 85, "M": 70, "L": 50, "A": 0},
    })


def _make_event(publish_date: str | None = None) -> dict:
    return {
        "severity_level": "中等",
        "country": "测试国",
        "product_category": "普通机电",
        "source_id": "test_api",
        "publish_date": publish_date,
    }


# 固定参考时间：2026-08-14 12:00:00
_REF_DATE = datetime(2026, 8, 14, 12, 0, 0)  # noqa: DTZ001


class TestRecencyDecayFactor:
    """单元测试 recency_decay_factor() 纯数学公式。"""

    @pytest.fixture
    def scorer(self) -> RiskScorer:
        return RiskScorer(_make_cfg(half_life_days=90, window_days=0, enabled=True))

    def test_same_day_returns_one(self, scorer: RiskScorer) -> None:
        """当天事件：days_since=0 → decay=1.0。

        用 YYYY-MM-DDTHH:MM:SS 格式确保时间与参考点完全对齐。
        """
        with patch("whyfxpg.core.risk_scorer.datetime") as mock_dt:
            mock_dt.now.return_value = _REF_DATE
            mock_dt.fromisoformat = datetime.fromisoformat
            # T12:00:00 与 _REF_DATE 完全对齐 → days_since=0 → decay=1.0
            decay = scorer.recency_decay_factor("2026-08-14T12:00:00")
        assert decay == pytest.approx(1.0, abs=0.01)  # 12h diff vs noon ref is ~0.4% decay

    def test_half_life_day_returns_half(self, scorer: RiskScorer) -> None:
        """半衰期（90天）后：decay ≈ 0.5。"""
        past = _REF_DATE - timedelta(days=90)
        with patch("whyfxpg.core.risk_scorer.datetime") as mock_dt:
            mock_dt.now.return_value = _REF_DATE
            mock_dt.fromisoformat = datetime.fromisoformat
            decay = scorer.recency_decay_factor(past.strftime("%Y-%m-%d"))
        assert decay == pytest.approx(0.5, abs=0.01)

    def test_three_x_half_life_returns_one_eighth(self, scorer: RiskScorer) -> None:
        """3×半衰期（270天）：decay ≈ 0.125。"""
        past = _REF_DATE - timedelta(days=270)
        with patch("whyfxpg.core.risk_scorer.datetime") as mock_dt:
            mock_dt.now.return_value = _REF_DATE
            mock_dt.fromisoformat = datetime.fromisoformat
            decay = scorer.recency_decay_factor(past.strftime("%Y-%m-%d"))
        assert decay == pytest.approx(0.125, abs=0.01)

    def test_future_date_capped_to_zero(self, scorer: RiskScorer) -> None:
        """未来日期：days_since<0 → 被夹断到 0 → decay=1.0。"""
        future = _REF_DATE + timedelta(days=5)
        with patch("whyfxpg.core.risk_scorer.datetime") as mock_dt:
            mock_dt.now.return_value = _REF_DATE
            mock_dt.fromisoformat = datetime.fromisoformat
            decay = scorer.recency_decay_factor(future.strftime("%Y-%m-%d"))
        assert decay == pytest.approx(1.0, abs=1e-9)

    def test_none_date_returns_one(self, scorer: RiskScorer) -> None:
        """publish_date=None → 返回 1.0（无衰减）。"""
        assert scorer.recency_decay_factor(None) == 1.0

    def test_unparseable_date_returns_one(self, scorer: RiskScorer) -> None:
        """无法解析的日期格式 → 返回 1.0。"""
        assert scorer.recency_decay_factor("not-a-date") == 1.0
        assert scorer.recency_decay_factor("2026-13-45") == 1.0

    def test_disabled_returns_one(self) -> None:
        """enabled=False → 返回 1.0。"""
        scorer = RiskScorer(_make_cfg(enabled=False))
        assert scorer.recency_decay_factor("2026-08-14") == 1.0

    def test_zero_half_life_returns_one(self) -> None:
        """half_life_days=0 → 返回 1.0。"""
        scorer = RiskScorer(_make_cfg(half_life_days=0))
        assert scorer.recency_decay_factor("2026-08-14") == 1.0

    def test_negative_half_life_returns_one(self) -> None:
        """half_life_days<0 → 返回 1.0。"""
        scorer = RiskScorer(_make_cfg(half_life_days=-10))
        assert scorer.recency_decay_factor("2026-08-14") == 1.0

    def test_window_exceeded_returns_one(self) -> None:
        """超出 window_days 窗口 → 返回 1.0。"""
        scorer = RiskScorer(_make_cfg(half_life_days=90, window_days=180, enabled=True))
        past = _REF_DATE - timedelta(days=200)  # > 180 天窗口
        with patch("whyfxpg.core.risk_scorer.datetime") as mock_dt:
            mock_dt.now.return_value = _REF_DATE
            mock_dt.fromisoformat = datetime.fromisoformat
            decay = scorer.recency_decay_factor(past.strftime("%Y-%m-%d"))
        assert decay == 1.0

    def test_window_within_returns_decay(self) -> None:
        """窗口内事件正常衰减。"""
        scorer = RiskScorer(_make_cfg(half_life_days=90, window_days=180, enabled=True))
        past = _REF_DATE - timedelta(days=90)  # 半衰期，但在窗口内
        with patch("whyfxpg.core.risk_scorer.datetime") as mock_dt:
            mock_dt.now.return_value = _REF_DATE
            mock_dt.fromisoformat = datetime.fromisoformat
            decay = scorer.recency_decay_factor(past.strftime("%Y-%m-%d"))
        assert decay == pytest.approx(0.5, abs=0.01)

    def test_window_zero_means_no_limit(self) -> None:
        """window_days=0 表示不限制，正常衰减。"""
        scorer = RiskScorer(_make_cfg(half_life_days=90, window_days=0, enabled=True))
        past = _REF_DATE - timedelta(days=365)  # 远超半衰期
        with patch("whyfxpg.core.risk_scorer.datetime") as mock_dt:
            mock_dt.now.return_value = _REF_DATE
            mock_dt.fromisoformat = datetime.fromisoformat
            decay = scorer.recency_decay_factor(past.strftime("%Y-%m-%d"))
        # decay = exp(-ln(2) * 365 / 90) ≈ 0.062
        assert decay == pytest.approx(math.exp(-math.log(2) * 365 / 90), abs=0.01)

    def test_iso_datetime_format(self, scorer: RiskScorer) -> None:
        """支持 YYYY-MM-DDTHH:MM:SS 格式。"""
        with patch("whyfxpg.core.risk_scorer.datetime") as mock_dt:
            mock_dt.now.return_value = _REF_DATE
            mock_dt.fromisoformat = datetime.fromisoformat
            decay = scorer.recency_decay_factor("2026-08-14T08:30:00")
        assert decay == pytest.approx(1.0, abs=0.01)  # noon ref - 08:30 = 3.5h = 0.146 day ≈ 0.11% decay


    def test_custom_half_life_45_days(self) -> None:
        """自定义半衰期 45 天。"""
        scorer = RiskScorer(_make_cfg(half_life_days=45, enabled=True))
        past = _REF_DATE - timedelta(days=45)
        with patch("whyfxpg.core.risk_scorer.datetime") as mock_dt:
            mock_dt.now.return_value = _REF_DATE
            mock_dt.fromisoformat = datetime.fromisoformat
            decay = scorer.recency_decay_factor(past.strftime("%Y-%m-%d"))
        assert decay == pytest.approx(0.5, abs=0.01)

    def test_missing_recency_decay_config_defaults_to_enabled(self) -> None:
        """无 recency_decay YAML 配置时，Pydantic 用 defaults 补全，decay 仍生效。

        这是正确的向后兼容行为：旧配置文件中没有 recency_decay 节，
        升级代码后自动启用衰减（而非静默失效）。
        要禁用衰减须显式设置 enabled=false。
        """
        cfg = RiskModelConfig.from_dict({
            "version": "1.0",
            "severity_levels": {"中等": {"default": 60}},
            "probability_levels": {"可能": {"default": 95}},
            "country_factors": {"测试国": 1.0},
            "product_factors": {"普通机电": 1.0},
            "history_factor": {"formula": "1", "max": 1.0, "min": 1.0},
            "evidence_factors": {"test_api": 1.0},
            "risk_level_thresholds": {"S": 85, "M": 70, "L": 50, "A": 0},
            # 注意：没有 recency_decay 节 → Pydantic 用 defaults 补全
        })
        scorer = RiskScorer(cfg)
        # 默认 half_life=90, enabled=True；用 ISO 格式时间对齐
        with patch("whyfxpg.core.risk_scorer.datetime") as mock_dt:
            mock_dt.now.return_value = _REF_DATE
            mock_dt.fromisoformat = datetime.fromisoformat
            # 半衰期 90 天 → decay ≈ 0.5
            decay = scorer.recency_decay_factor((_REF_DATE - timedelta(days=90)).strftime("%Y-%m-%dT%H:%M:%S"))
        assert decay == pytest.approx(0.5, abs=0.01)


class TestRecencyDecayIntegration:
    """集成测试：recency_decay 因子正确乘入 score() 结果。"""

    @pytest.fixture
    def scorer(self) -> RiskScorer:
        return RiskScorer(_make_cfg(half_life_days=90, window_days=0, enabled=True))

    def test_score_includes_recency_decay_field(self, scorer: RiskScorer) -> None:
        """ScoringResult 包含 recency_decay 字段。"""
        event = _make_event("2026-08-14T12:00:00")
        with patch("whyfxpg.core.risk_scorer.datetime") as mock_dt:
            mock_dt.now.return_value = _REF_DATE
            mock_dt.fromisoformat = datetime.fromisoformat
            result = scorer.score(event, {"country_history_count": 0, "product_history_count": 0}, 1.0)
        assert hasattr(result, "recency_decay")
        assert result.recency_decay == pytest.approx(1.0, abs=1e-4)

    def test_score_decay_reduces_total(self, scorer: RiskScorer) -> None:
        """半衰期事件：decay=0.5 → total_score 应约为无衰减的一半。"""
        # 无衰减基准
        event_no_decay = _make_event(None)
        result_no_decay = scorer.score(
            event_no_decay, {"country_history_count": 0, "product_history_count": 0}, 1.0
        )

        # 半衰期衰减
        half_life_date = (_REF_DATE - timedelta(days=90)).strftime("%Y-%m-%d")
        event_decayed = _make_event(half_life_date)
        with patch("whyfxpg.core.risk_scorer.datetime") as mock_dt:
            mock_dt.now.return_value = _REF_DATE
            mock_dt.fromisoformat = datetime.fromisoformat
            result_decayed = scorer.score(
                event_decayed, {"country_history_count": 0, "product_history_count": 0}, 1.0
            )

        # decay≈0.5, total 应约为无衰减的 0.5
        assert result_decayed.total_score == pytest.approx(result_no_decay.total_score * 0.5, rel=0.02)

    def test_score_same_day_full_value(self, scorer: RiskScorer) -> None:
        """当天事件 total_score 与无衰减几乎一致（误差 < 0.1%）。"""
        event = _make_event("2026-08-14T12:00:00")  # 时间对齐
        with patch("whyfxpg.core.risk_scorer.datetime") as mock_dt:
            mock_dt.now.return_value = _REF_DATE
            mock_dt.fromisoformat = datetime.fromisoformat
            result = scorer.score(event, {"country_history_count": 0, "product_history_count": 0}, 1.0)

        # 无衰减基准（None date → decay=1.0）
        event_none = _make_event(None)
        result_none = scorer.score(event_none, {"country_history_count": 0, "product_history_count": 0}, 1.0)

        # 当天事件应与无衰减几乎相同
        assert result.total_score == pytest.approx(result_none.total_score, rel=0.001)
