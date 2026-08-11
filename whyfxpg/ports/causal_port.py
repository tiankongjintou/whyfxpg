"""因果端口：RiskModel / UI 与因果知识之间的最小接口。"""

from abc import ABC, abstractmethod
from typing import Any


class CausalPort(ABC):
    """
    因果端口。

    为风险评分与解释提供只读的最小接口：
    - factor(event): 因果增强系数
    - explain(event): 因果溯源文本
    - counterfactual(event, intervention): 反事实风险变化
    """

    @abstractmethod
    def factor(self, event: dict[str, Any]) -> float:
        ...

    @abstractmethod
    def explain(self, event: dict[str, Any]) -> str:
        ...

    @abstractmethod
    def counterfactual(
        self,
        event: dict[str, Any],
        intervention: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        ...
