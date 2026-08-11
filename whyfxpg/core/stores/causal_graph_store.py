"""Auto-split store module."""

import json
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from whyfxpg.core.stores.unit_of_work import BaseStore
from whyfxpg.migrations import MigrationRunner


class CausalGraphStore(BaseStore):
    """因果图 store，负责 causal_nodes / causal_edges / causal_paths 的 CRUD 与查询。"""

    def ensure_schema(self) -> None:
        """初始化因果知识图谱 schema（由 MigrationRunner 集中管理）。"""
        MigrationRunner(self.uow.connection).run()

    def add_node(
        self,
        node_id: str,
        node_type: str,
        name: str,
        risk_score: float = 0.5,
        properties: dict | None = None,
        source: str = "manual",
    ) -> str:
        """添加或更新因果节点（upsert）。"""
        cursor = self.uow.connection.cursor()
        cursor.execute(
            """
            INSERT INTO causal_nodes (node_id, node_type, name, properties, risk_score, source, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(node_type, name) DO UPDATE SET
                properties = excluded.properties,
                risk_score = excluded.risk_score,
                source = excluded.source,
                updated_at = excluded.updated_at
            """,
            (
                node_id,
                node_type,
                name,
                json.dumps(properties or {}, ensure_ascii=False),
                risk_score,
                source,
                datetime.now().isoformat(),  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
            ),
        )
        return node_id

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        """按 node_id 查询节点。"""
        cursor = self.uow.connection.cursor()
        cursor.execute("SELECT * FROM causal_nodes WHERE node_id = ?", (node_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return self._row_to_node(dict(row))

    def find_nodes(self, node_type: str, name_pattern: str = "%") -> list[dict[str, Any]]:
        """按类型和名称模糊搜索节点。"""
        cursor = self.uow.connection.cursor()
        cursor.execute(
            "SELECT * FROM causal_nodes WHERE node_type = ? AND name LIKE ?",
            (node_type, name_pattern),
        )
        return [self._row_to_node(dict(r)) for r in cursor.fetchall()]

    def add_edge(
        self,
        edge_id: str,
        from_node: str,
        to_node: str,
        edge_type: str,
        weight: float = 0.5,
        evidence: str = "",
        source: str = "manual",
    ) -> str:
        """添加或更新因果边（upsert）。"""
        cursor = self.uow.connection.cursor()
        cursor.execute(
            """
            INSERT INTO causal_edges (edge_id, from_node, to_node, edge_type, weight, evidence, source, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(edge_id) DO UPDATE SET
                weight = excluded.weight,
                evidence = excluded.evidence,
                source = excluded.source,
                updated_at = excluded.updated_at
            """,
            (
                edge_id,
                from_node,
                to_node,
                edge_type,
                weight,
                evidence,
                source,
                datetime.now().isoformat(),  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
            ),
        )
        return edge_id

    def get_edges(
        self,
        node_id: str,
        direction: str = "out",
        edge_types: Sequence[str] | None = None,
    ) -> list[dict[str, Any]]:
        """查询某节点的直接出边或入边。"""
        if edge_types is None:
            edge_types = ["causes", "aggravates", "supplies", "uses"]
        cursor = self.uow.connection.cursor()
        placeholders = ",".join(["?"] * len(edge_types))
        if direction == "out":
            sql = f"""
                SELECT e.*, n_from.name as from_name, n_to.name as to_name
                FROM causal_edges e
                JOIN causal_nodes n_from ON e.from_node = n_from.node_id
                JOIN causal_nodes n_to ON e.to_node = n_to.node_id
                WHERE e.from_node = ? AND e.edge_type IN ({placeholders})
            """
            params = (node_id,) + tuple(edge_types)
        else:
            sql = f"""
                SELECT e.*, n_from.name as from_name, n_to.name as to_name
                FROM causal_edges e
                JOIN causal_nodes n_from ON e.from_node = n_from.node_id
                JOIN causal_nodes n_to ON e.to_node = n_to.node_id
                WHERE e.to_node = ? AND e.edge_type IN ({placeholders})
            """
            params = (node_id,) + tuple(edge_types)
        cursor.execute(sql, params)
        return [dict(r) for r in cursor.fetchall()]

    def get_causal_chain(
        self,
        start_node: str,
        depth: int = 3,
        edge_types: Sequence[str] | None = None,
    ) -> list[dict[str, Any]]:
        """从给定节点出发，深度优先搜索因果链。"""
        if edge_types is None:
            edge_types = ["causes", "aggravates", "supplies", "uses"]
        cursor = self.uow.connection.cursor()
        placeholders = ",".join(["?"] * len(edge_types))
        sql = f"""
            SELECT e.from_node, e.to_node, e.edge_type, e.weight,
                   n_from.name as from_name, n_to.name as to_name
            FROM causal_edges e
            JOIN causal_nodes n_from ON e.from_node = n_from.node_id
            JOIN causal_nodes n_to ON e.to_node = n_to.node_id
            WHERE e.from_node = ? AND e.edge_type IN ({placeholders})
        """

        chain = []
        visited = set()
        stack = [(start_node, 0)]
        while stack:
            current, current_depth = stack.pop()
            if current in visited or current_depth > depth:
                continue
            visited.add(current)
            cursor.execute(sql, (current,) + tuple(edge_types))
            for row in cursor.fetchall():
                chain.append(
                    {
                        "from": row["from_node"],
                        "from_name": row["from_name"],
                        "edge_type": row["edge_type"],
                        "weight": row["weight"],
                        "to": row["to_node"],
                        "to_name": row["to_name"],
                        "depth": current_depth + 1,
                    }
                )
                stack.append((row["to_node"], current_depth + 1))
        return chain

    def get_statistics(self) -> dict[str, Any]:
        """获取因果知识库统计。"""
        cursor = self.uow.connection.cursor()
        stats = {}
        cursor.execute("SELECT COUNT(*) FROM causal_nodes")
        stats["nodes"] = cursor.fetchone()[0]
        cursor.execute("SELECT node_type, COUNT(*) FROM causal_nodes GROUP BY node_type")
        stats["nodes_by_type"] = {r["node_type"]: r[1] for r in cursor.fetchall()}
        cursor.execute("SELECT COUNT(*) FROM causal_edges")
        stats["edges"] = cursor.fetchone()[0]
        cursor.execute("SELECT edge_type, COUNT(*) FROM causal_edges GROUP BY edge_type")
        stats["edges_by_type"] = {r["edge_type"]: r[1] for r in cursor.fetchall()}
        cursor.execute("SELECT COUNT(*) FROM causal_paths")
        stats["paths"] = cursor.fetchone()[0]
        cursor.execute("SELECT AVG(weight) FROM causal_edges WHERE edge_type = 'causes'")
        avg = cursor.fetchone()[0]
        stats["avg_causal_weight"] = round(avg, 3) if avg else 0.0
        return stats

    @staticmethod
    def _row_to_node(row: dict[str, Any]) -> dict[str, Any]:
        if row.get("properties"):
            try:
                row["properties"] = json.loads(row["properties"])
            except Exception:  # noqa: BLE001, S110 — 刻意用法(见 TD03)
                pass
        return row

    def insert_causal_path(
        self,
        path_id: str,
        root_event_id: str,
        chain: str,
        total_weight: float,
        confidence: float,
        explanation: str,
    ) -> None:
        """插入一条因果路径记录。"""
        cursor = self.uow.connection.cursor()
        cursor.execute(
            """
            INSERT INTO causal_paths (path_id, root_event_id, chain, total_weight, confidence, explanation, generated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                path_id,
                root_event_id,
                chain,
                total_weight,
                confidence,
                explanation,
                datetime.now().isoformat(),  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
            ),
        )
