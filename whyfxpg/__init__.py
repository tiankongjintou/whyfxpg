# WHYfxpg — 进口机电产品风险评价系统
#
# 用法示例::
#     from whyfxpg import RiskScorer
#     result = RiskScorer.assess(event={...}, historical_counts={...})
#     print(result.rs_level, result.total_score)

from whyfxpg.core.risk_scorer import RiskScorer, ScoringResult

__all__ = ["RiskScorer", "ScoringResult"]
__version__ = "0.1.0"
