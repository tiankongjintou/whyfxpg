"""DB-backed CausalPort 适配器。"""

from typing import Any

from whyfxpg.core.stores import CausalGraphStore, UnitOfWork
from whyfxpg.ports.causal_port import CausalPort
from whyfxpg.services.causal_reasoning import CausalReasoning


class DbCausalAdapter(CausalPort):
    """基于 CausalGraphStore 的 CausalPort 实现。"""

    def __init__(self, uow: UnitOfWork):
        self._store = CausalGraphStore(uow)
        self._reasoning = CausalReasoning()

    def factor(self, event: dict[str, Any]) -> float:
        return self._reasoning.factor(event, self._store)

    def explain(self, event: dict[str, Any]) -> str:
        return self._reasoning.explain(event, self._store)

    def counterfactual(
        self,
        event: dict[str, Any],
        intervention: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        return self._reasoning.counterfactual(
            event,
            intervention or {},
            self._store,
        )
