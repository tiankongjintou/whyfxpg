"""纯风险评分策略模块 (Phase 3A seam / Phase 4D 类型化)。

设计决策：
- RiskScorer 是一个无数据库依赖的 deep module：只负责把配置 + 事件 + 历史统计
  转换成一个评分结果。
- 因果因子由调用方（RiskEvaluationRunner）注入，避免 scorer 依赖 CausalPort。
- 所有查表/计算逻辑集中在 scorer 内，避免 runner 层再次展开。
- 使用 RiskModelConfig 类型对象替代裸 dict，提供字段级类型提示。
"""

import math
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from whyfxpg.config.pydantic_models import RiskModelConfig


@dataclass(frozen=True)
class ScoringResult:
    """单次事件评分结果。"""

    ss_score: int
    ps_score: int
    probability_level: str
    country_factor: float
    product_factor: float
    history_factor: float
    evidence_factor: float
    causal_factor: float
    total_score: float
    rs_level: str


class RiskScorer:
    """风险评分策略。

    Interface（对外 seams）：
        __init__(model_cfg: RiskModelConfig | dict)
        score(event, historical_counts, causal_factor) -> ScoringResult

    Implementation：封装配置查表、历史密度映射、最终总分与等级映射。
    """

    def __init__(self, model_cfg: "RiskModelConfig"):
        self._cfg = model_cfg

    @staticmethod
    def _level_score(level_cfg, default_score: int) -> int:
        """从 LevelConfig 取 score 或 default。"""
        if level_cfg is None:
            return default_score
        if level_cfg.score is not None:
            return level_cfg.score
        if level_cfg.default:
            return level_cfg.default
        return default_score

    def severity_to_score(self, severity_level: str) -> int:
        """严重度等级转分数；不存在时回退到默认键。"""
        levels = self._cfg.severity_levels
        default_level = levels.get("中等")
        return self._level_score(
            levels.get(severity_level, default_level),
            self._level_score(default_level, 60),
        )

    def probability_to_score(self, event: dict[str, Any], history_count: int) -> int:
        """基于历史事件密度映射概率等级并返回分数。"""
        # 注意：优先尊重事件本身携带的概率等级（抽取模块提供）
        if event.get("probability_level"):
            level = event["probability_level"]
        elif history_count >= 5:
            level = "非常可能"
        elif history_count >= 2:
            level = "可能"
        elif history_count >= 1:
            level = "不太可能"
        else:
            level = "可能"  # 默认

        levels = self._cfg.probability_levels
        default_level = levels.get("可能")
        return self._level_score(
            levels.get(level, default_level),
            self._level_score(default_level, 95),
        )

    def country_factor(self, country: str) -> float:
        """国别修正系数。"""
        return self._cfg.country_factors.get(country, self._cfg.country_factors.get("unknown", 1.0))

    def product_factor(self, category: str) -> float:
        """产品修正系数。"""
        return self._cfg.product_factors.get(category, self._cfg.product_factors.get("unknown", 1.0))

    def history_factor(self, event_count_12m: int) -> float:
        """历史事件密度修正系数。"""
        formula_str = self._cfg.history_factor.formula
        safe_builtins = {"min": min, "max": max}
        try:
            value = eval(formula_str, {"__builtins__": safe_builtins}, {"event_count_12m": event_count_12m})
        except Exception:  # noqa: BLE001 — 公式来自用户配置,eval 异常必须全部兜底
            value = 1.0
        max_val = self._cfg.history_factor.max
        min_val = self._cfg.history_factor.min
        return max(min_val, min(value, max_val))

    def evidence_factor(self, source_id: str) -> float:
        """证据来源修正系数。"""
        return self._cfg.evidence_factors.get(source_id, self._cfg.evidence_factors.get("unknown", 0.9))

    def map_to_risk_level(self, total_score: float) -> str:
        """根据阈值映射风险等级。"""
        thresholds = self._cfg.risk_level_thresholds
        if total_score >= thresholds.get("S", 8000):
            return "S"
        elif total_score >= thresholds.get("M", 3000):
            return "M"
        elif total_score >= thresholds.get("L", 1000):
            return "L"
        else:
            return "A"

    def calculate_total_score(
        self,
        ss: int,
        ps: int,
        country_factor: float,
        product_factor: float,
        history_factor: float,
        evidence_factor: float,
        causal_factor: float = 1.0,
    ) -> float:
        """计算最终风险分（对数域求和，防乘法溢出）。

        公式：``log_score = Σ log(1 + factor)``，其中每个乘法项 f 的对数贡献为
        ``log(f) = log(1 + (f - 1))``（factor = f - 1 即该系数相对 1 的增量）；
        ss/ps 作为基准分直接取对数参与求和，最后 ``exp`` 还原。
        实现上用 ``math.log(f)`` 替代 ``log1p(f - 1)``，数值上更稳定
        （factor 极小不致舍入崩溃，factor = 0 时对数域自然得 0）。

        数学上与旧公式 ``ss * ps * country * product * history * evidence * causal``
        等价，但中间过程不经过乘积，极端权重下不会溢出或失真。

        边界：系数 = 1（增量 factor = 0）时 ``log(1+0)=0``，不影响计算；
        任一系数 ≤ 0（无物理意义）时整体按 0 处理，与旧公式乘以 0 一致。
        """
        if ss <= 0 or ps <= 0:
            return 0.0
        log_score = math.log(ss) + math.log(ps)
        for factor in (
            country_factor,
            product_factor,
            history_factor,
            evidence_factor,
            causal_factor,
        ):
            if factor <= 0.0:
                return 0.0
            # log(1 + (factor-1)) = log(factor);直接用 log(factor) 避免 factor≈0
            # 时 factor-1 舍入为 -1 导致 log1p 崩溃,同时数值更稳定
            log_score += math.log(factor)
        return math.exp(log_score)

    def score(
        self,
        event: dict[str, Any],
        historical_counts: dict[str, int],
        causal_factor: float,
    ) -> ScoringResult:
        """
        对单个事件进行完整评分。

        Args:
            event: 风险事件字段字典。
            historical_counts: 必须包含
                - country_history_count: 用于概率评分的事件密度计数
                - product_history_count: 用于历史密度修正的事件计数
            causal_factor: 外部因果知识增强系数（>1 表示风险传导）。
        """
        ss = self.severity_to_score(event.get("severity_level", "中等"))
        ps = self.probability_to_score(
            event, historical_counts.get("country_history_count", 0)
        )

        country_factor = self.country_factor(event.get("country", "unknown"))
        product_factor = self.product_factor(event.get("product_category", "普通机电"))
        history_factor = self.history_factor(
            historical_counts.get("product_history_count", 0)
        )
        evidence_factor = self.evidence_factor(event.get("source_id", "unknown"))

        total = self.calculate_total_score(
            ss,
            ps,
            country_factor,
            product_factor,
            history_factor,
            evidence_factor,
            causal_factor,
        )

        rs_level = self.map_to_risk_level(total)

        return ScoringResult(
            ss_score=ss,
            ps_score=ps,
            probability_level=self._probability_level_label(ps),
            country_factor=country_factor,
            product_factor=product_factor,
            history_factor=history_factor,
            evidence_factor=evidence_factor,
            causal_factor=causal_factor,
            total_score=round(total, 2),
            rs_level=rs_level,
        )

    @staticmethod
    def _probability_level_label(ps: int) -> str:
        """由概率分数反推概率等级文本（与 YAML 默认分数对应）。"""
        if ps >= 100:
            return "非常可能"
        elif ps >= 90:
            return "可能"
        elif ps >= 30:
            return "不太可能"
        else:
            return "几乎不可能"

    @staticmethod
    def assess(
        event: dict[str, Any],
        historical_counts: dict[str, int],
        causal_factor: float = 1.0,
        config_path: str = "Config/risk_model.yaml",
    ) -> "ScoringResult":
        """
        一句话风险评估接口（外部调用3行代码）。

        用法示例::
            from whyfxpg import RiskScorer
            result = RiskScorer.assess(
                event={
                    "severity_level": "严重",
                    "country": "美国",
                    "product_category": "家用厨房电器",
                },
                historical_counts={
                    "country_history_count": 3,
                    "product_history_count": 1,
                },
                causal_factor=1.0,
            )
            print(result.rs_level, result.total_score)

        Args:
            event: 风险事件字段字典，必须字段：
                - severity_level: 严重度等级（灾难性/严重/中等/轻微）
                - country: 国别
                - product_category: 产品类别
                可选字段：source_id, probability_level, publish_date
            historical_counts: 历史统计计数，必须字段：
                - country_history_count: 用于概率评分的事件密度计数
                - product_history_count: 用于历史密度修正的事件计数
            causal_factor: 因果传导系数，默认1.0
            config_path: 风险模型配置文件路径，默认 "Config/risk_model.yaml"

        Returns:
            ScoringResult: 包含 ss_score, ps_score, total_score, rs_level 等字段
        """
        from whyfxpg.config.pydantic_loader import load_risk_model

        cfg = load_risk_model(Path(config_path))
        scorer = RiskScorer(cfg)
        return scorer.score(event, historical_counts, causal_factor)
