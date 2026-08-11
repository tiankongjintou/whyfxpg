"""Causal service: UI-facing facade for causal knowledge operations.

Keeps the Streamlit page free from schema initialization and direct store
imports; all reads go through CausalKnowledge (which itself uses CausalPort).
"""

from typing import Any

from whyfxpg.core.causal_knowledge import CausalKnowledge


class CausalService:
    """Application service for causal graph reads used by the web UI."""

    def __init__(self, db_path: str | None = None):
        self._ck = CausalKnowledge(db_path=db_path)

    def get_statistics(self) -> dict[str, Any]:
        """Return statistics with the keys expected by the UI."""
        stats = self._ck.get_statistics()
        return {
            "total_nodes": stats.get("nodes", 0),
            "total_edges": stats.get("edges", 0),
            "avg_causal_weight": stats.get("avg_causal_weight", 0.0),
        }

    def explain_event(self, event: dict[str, Any]) -> str:
        return self._ck.explain_event(event)

    def get_causal_factor(self, event: dict[str, Any]) -> float:
        return self._ck.get_causal_factor(event)

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        return self._ck.get_node(node_id)

    def counterfactual_risk(
        self,
        event: dict[str, Any],
        intervention: dict[str, str],
    ) -> dict[str, Any]:
        return self._ck.counterfactual_risk(event, intervention)

    def seed_initial_knowledge(self) -> dict[str, Any]:
        """Admin-only: seed baseline causal knowledge."""
        return self._ck.seed_initial_knowledge()
