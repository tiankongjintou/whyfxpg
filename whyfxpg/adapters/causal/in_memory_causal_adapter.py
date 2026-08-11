"""内存因果图适配器，用于测试与小型 fixture 场景。"""

from collections.abc import Sequence
from typing import Any

from whyfxpg.ports.causal_port import CausalPort
from whyfxpg.services.causal_reasoning import CausalReasoning, GraphView


class InMemoryGraphView(GraphView):
    """实现 GraphView 协议的内存视图（无 DB 依赖）。"""

    def __init__(
        self,
        nodes: dict[str, dict[str, Any]] | None = None,
        edges: list[dict[str, Any]] | None = None,
    ):
        self.nodes = nodes or {}
        self.edges = edges or []

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        return self.nodes.get(node_id)

    def get_causal_chain(
        self,
        start_node: str,
        depth: int = 3,
        edge_types: Sequence[str] | None = None,
    ) -> list[dict[str, Any]]:
        if edge_types is None:
            edge_types = ["causes", "aggravates", "supplies", "uses"]
        chain = []
        visited = set()
        stack = [(start_node, 0)]
        while stack:
            current, current_depth = stack.pop()
            if current in visited or current_depth > depth:
                continue
            visited.add(current)
            for e in self.edges:
                if e["from"] == current and e["edge_type"] in edge_types:
                    to_name = self.nodes.get(e["to"], {}).get("name", e["to"])
                    from_name = self.nodes.get(current, {}).get("name", current)
                    chain.append(
                        {
                            "from": current,
                            "from_name": from_name,
                            "edge_type": e["edge_type"],
                            "weight": e["weight"],
                            "to": e["to"],
                            "to_name": to_name,
                            "depth": current_depth + 1,
                        }
                    )
                    stack.append((e["to"], current_depth + 1))
        return chain


class InMemoryCausalAdapter(CausalPort):
    """内存版 CausalPort 实现，无需数据库。"""

    def __init__(
        self,
        nodes: dict[str, dict[str, Any]] | None = None,
        edges: list[dict[str, Any]] | None = None,
    ):
        self._view = InMemoryGraphView(nodes, edges)
        self._reasoning = CausalReasoning()

    @property
    def graph_view(self) -> InMemoryGraphView:
        """暴露底层 GraphView，供 CausalReasoning 等纯算法模块使用。"""
        return self._view

    def factor(self, event: dict[str, Any]) -> float:
        return self._reasoning.factor(event, self._view)

    def explain(self, event: dict[str, Any]) -> str:
        return self._reasoning.explain(event, self._view)

    def counterfactual(
        self,
        event: dict[str, Any],
        intervention: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        return self._reasoning.counterfactual(
            event,
            intervention or {},
            self._view,
        )

    def add_node(self, node_id: str, node_type: str, name: str, **kwargs) -> None:
        self._view.nodes[node_id] = {
            "node_id": node_id,
            "node_type": node_type,
            "name": name,
            **kwargs,
        }

    def add_edge(
        self,
        edge_id: str,
        from_node: str,
        to_node: str,
        edge_type: str,
        weight: float = 0.5,
        evidence: str = "",
        source: str = "",
    ) -> None:
        self._view.edges.append(
            {
                "from": from_node,
                "to": to_node,
                "edge_type": edge_type,
                "weight": weight,
                "edge_id": edge_id,
                "evidence": evidence,
                "source": source,
            }
        )
