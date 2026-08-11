"""
因果知识图谱模块

功能：
- 构建并管理"供应商质量 → 零部件类型 → 制造缺陷模式 → 危害类型 → 事故严重度"因果图
- 支持反事实推理：给定一个风险事件，推理"若改变某环节，风险如何变化"
- 支持因果路径查询：查找从零部件问题到最终事故的完整因果链
- 为 risk_model 提供因果增强的国别/产品系数

设计说明：
- 使用 SQLite 自身存储因果图（无需引入 Neo4j 等重型图数据库）
- 因果强度以数值 weight 表示，范围 [0, 1]，由专家配置 + 历史数据学习共同确定
- 因果知识由业务专家初始配置，随 manual_reviews 反馈逐步修正

架构（T6 拆分后）：
- CausalGraphStore：负责 SQLite 中 causal_nodes / causal_edges / causal_paths 的 CRUD。
- CausalReasoning：纯算法，负责 factor / explain / counterfactual / downstream_risk。
- CausalKnowledge：面向业务和旧代码的 facade，组合上述两者，保持原有公开接口。
"""

import sqlite3
from contextlib import contextmanager
from typing import Any

from whyfxpg.adapters.causal import DbCausalAdapter
from whyfxpg.core.db import get_db_connection  # noqa: F401 — 测试经模块属性 monkeypatch
from whyfxpg.services.causal_reasoning import CausalReasoning

from .stores import CausalGraphStore, UnitOfWork

# ─────────────────────────────────────────────────────────────
# Schema 管理
# ─────────────────────────────────────────────────────────────

CAUSAL_NODE_TYPES = [
    "supplier",            # 供应商
    "component_type",      # 零部件类型
    "defect_pattern",      # 制造缺陷模式
    "hazard_category",   # 危害类别
    "incident_severity",   # 事故严重程度
    "standard_version",    # 标准版本
    "country",             # 国别（与 risk_events 表联动）
    "manufacturer",        # 制造商
]

CAUSAL_EDGE_TYPES = [
    "causes",              # 直接导致
    "aggravates",          # 加重
    "mitigates",           # 减轻/缓解
    "substitutes",         # 替代关系
    "supplies",            # 供应关系
    "uses",                # 使用（制造商→零部件）
]


def init_causal_schema(db_path: str | None = None) -> None:
    """初始化因果知识图谱 Schema（创建表），幂等。"""
    with UnitOfWork(db_path) as uow:
        CausalGraphStore(uow).ensure_schema()


# ─────────────────────────────────────────────────────────────
# 核心 API（Facade，保持旧签名）
# ─────────────────────────────────────────────────────────────

class CausalKnowledge:
    """因果知识图谱引擎：对外的 facade，内部委托给 CausalGraphStore + CausalReasoning。"""

    def __init__(self, db_path: str | None = None, conn: sqlite3.Connection | None = None):
        self.db_path = db_path
        self._conn = conn
        self._reasoning = CausalReasoning()

    @classmethod
    def from_connection(cls, conn: sqlite3.Connection) -> "CausalKnowledge":
        """基于已存在的数据库连接创建引擎，不管理连接生命周期。"""
        return cls(conn=conn)

    @contextmanager
    def _uow(self):
        """提供 UnitOfWork 上下文；外部连接时不负责提交/关闭。"""
        if self._conn is not None:
            yield UnitOfWork.from_connection(self._conn)
        else:
            with UnitOfWork(self.db_path) as uow:
                yield uow

    # ── 节点操作 ────────────────────────────────────────────

    def add_node(
        self,
        node_type: str,
        name: str,
        risk_score: float = 0.5,
        properties: dict | None = None,
        source: str = "manual",
    ) -> str:
        """添加或更新因果节点（upsert）。"""
        node_id = f"{node_type}:{name}"
        with self._uow() as uow:
            CausalGraphStore(uow).add_node(
                node_id, node_type, name, risk_score, properties, source
            )
        return node_id

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        """按 node_id 查询节点。"""
        with self._uow() as uow:
            return CausalGraphStore(uow).get_node(node_id)

    def find_nodes(self, node_type: str, name_pattern: str = "%") -> list[dict[str, Any]]:
        """模糊搜索某类型节点。"""
        with self._uow() as uow:
            return CausalGraphStore(uow).find_nodes(node_type, name_pattern)

    # ── 边操作 ────────────────────────────────────────────

    def add_edge(
        self,
        from_node: str,
        to_node: str,
        edge_type: str,
        weight: float = 0.5,
        evidence: str = "",
        source: str = "manual",
    ) -> str:
        """添加因果边（upsert，同一节点对允许多条不同类型边）。"""
        edge_id = f"{from_node}|{edge_type}|{to_node}"
        with self._uow() as uow:
            store = CausalGraphStore(uow)
            # 自动补全不存在的节点，保持与旧版本行为一致
            for nid in (from_node, to_node):
                if not store.get_node(nid):
                    parts = nid.split(":", 1)
                    if len(parts) == 2:
                        store.add_node(nid, parts[0], parts[1])
            store.add_edge(
                edge_id, from_node, to_node, edge_type, weight, evidence, source
            )
        return edge_id

    def get_causal_chain(
        self,
        start_node: str,
        depth: int = 3,
        edge_types: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """从给定节点出发，深度优先搜索因果链。"""
        with self._uow() as uow:
            return CausalGraphStore(uow).get_causal_chain(start_node, depth, edge_types)

    def compute_downstream_risk(self, node_id: str) -> float:
        """计算某节点的向下游传播风险分。"""
        with self._uow() as uow:
            return self._reasoning.compute_downstream_risk(
                node_id, CausalGraphStore(uow)
            )

    # ── 因果增强风险评分 ────────────────────────────────────

    def get_causal_factor(self, event: dict[str, Any]) -> float:
        """根据事件的制造商/供应商/危害信息，计算因果增强系数。"""
        with self._uow() as uow:
            return DbCausalAdapter(uow).factor(event)

    def factor(self, event: dict[str, Any]) -> float:
        """CausalPort 兼容接口：同 get_causal_factor。"""
        return self.get_causal_factor(event)

    # ── 反事实推理 ────────────────────────────────────────

    def counterfactual_risk(
        self,
        event: dict[str, Any],
        intervention: dict[str, str],
    ) -> dict[str, Any]:
        """反事实推理：给定一个干预，计算假设性风险变化。"""
        with self._uow() as uow:
            return DbCausalAdapter(uow).counterfactual(event, intervention)

    def counterfactual(
        self,
        event: dict[str, Any],
        intervention: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """CausalPort 兼容接口：同 counterfactual_risk。"""
        return self.counterfactual_risk(event, intervention or {})

    # ── 溯源因果链 ────────────────────────────────────────

    def explain_event(self, event: dict[str, Any]) -> str:
        """生成风险事件的因果解释。"""
        with self._uow() as uow:
            return DbCausalAdapter(uow).explain(event)

    def explain(self, event: dict[str, Any]) -> str:
        """CausalPort 兼容接口：同 explain_event。"""
        return self.explain_event(event)

    # ── 知识注入 ──────────────────────────────────────────

    def seed_initial_knowledge(self) -> dict[str, Any]:
        """初始化基础因果知识（可扩展的专家知识库）。"""
        with self._uow() as uow:
            store = CausalGraphStore(uow)
            cursor = uow.connection.cursor()
            cursor.execute("SELECT COUNT(*) FROM causal_nodes")
            existing = cursor.fetchone()[0]
            if existing > 0:
                return {"status": "skipped", "message": "因果知识库已有数据，跳过初始化"}

            # 国别节点（风险评分基准）
            country_risk = {
                "美国": 0.9, "德国": 0.8, "日本": 0.8, "英国": 0.85,
                "中国": 0.75, "韩国": 0.8, "法国": 0.8, "意大利": 0.85,
                "越南": 0.95, "印度": 0.95, "巴基斯坦": 1.0,
                "孟加拉国": 1.0, "unknown": 1.0,
            }
            for country, score in country_risk.items():
                store.add_node(
                    f"country:{country}", "country", country, risk_score=score, source="initial_seed"
                )

            # 零部件 → 危害类型 因果边
            component_hazard_edges = [
                ("电容器", "电击风险", 0.8, "劣质电容器耐压不足导致漏电"),
                ("电容器", "火灾风险", 0.7, "电容器过热引发短路"),
                ("电源线", "电击风险", 0.85, "电源线绝缘层破损"),
                ("电池模组", "火灾风险", 0.9, "锂离子电池热失控"),
                ("电机轴承", "机械伤害", 0.6, "轴承磨损导致异响和过热"),
                ("外壳塑料", "火灾风险", 0.5, "非阻燃材料遇明火燃烧"),
                ("开关元件", "电击风险", 0.7, "开关绝缘距离不足"),
                ("接地保护", "电击风险", 0.9, "接地导线断裂或未连接"),
            ]
            for comp, hazard, weight, evidence in component_hazard_edges:
                comp_node = f"component_type:{comp}"
                hazard_node = f"hazard_category:{hazard}"
                store.add_node(comp_node, "component_type", comp, risk_score=weight, source="initial_seed")
                store.add_node(hazard_node, "hazard_category", hazard, risk_score=weight, source="initial_seed")
                store.add_edge(
                    f"{comp_node}|causes|{hazard_node}",
                    comp_node,
                    hazard_node,
                    "causes",
                    weight=weight,
                    evidence=evidence,
                    source="initial_seed",
                )

            # 制造商示例节点
            sample_manufacturers = [
                ("Stanley Black & Decker", 0.7, "全球知名工具制造商，有质量管理体系"),
                ("美的集团", 0.6, "中国家电龙头，有完善的质量控制"),
                ("未知制造商", 1.0, "信息不足，默认最高风险"),
            ]
            for name, score, note in sample_manufacturers:
                store.add_node(
                    f"manufacturer:{name}",
                    "manufacturer",
                    name,
                    risk_score=score,
                    properties={"note": note},
                    source="initial_seed",
                )

            # 供应商节点
            sample_suppliers = [
                ("认证供应商A", 0.3, "通过ISO9001和IECQ认证"),
                ("普通供应商B", 0.6, "有部分质量报告，无国际认证"),
                ("未知供应商", 1.0, "信息不足，默认最高风险"),
            ]
            for name, score, note in sample_suppliers:
                store.add_node(
                    f"supplier:{name}",
                    "supplier",
                    name,
                    risk_score=score,
                    properties={"note": note},
                    source="initial_seed",
                )

            return {
                "status": "success",
                "message": (
                    f"初始化完成：{len(country_risk)}个国别节点，"
                    f"{len(component_hazard_edges)}条因果边，"
                    f"{len(sample_manufacturers)}个制造商，"
                    f"{len(sample_suppliers)}个供应商"
                ),
            }

    def get_statistics(self) -> dict[str, Any]:
        """获取因果知识库统计。"""
        with self._uow() as uow:
            return CausalGraphStore(uow).get_statistics()


# ─────────────────────────────────────────────────────────────
# 主入口
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from .db import init_db
    init_db()
    init_causal_schema()

    ck = CausalKnowledge()
    seed_result = ck.seed_initial_knowledge()
    print("初始化结果:", seed_result)

    stats = ck.get_statistics()
    print("因果知识库统计:", stats)

    # 测试因果链查询
    test_event = {
        "manufacturer": "Stanley Black & Decker",
        "country": "美国",
        "hazard_type": "电击风险",
        "product_category": "电动工具",
        "total_score": 8500,
    }
    factor = ck.get_causal_factor(test_event)
    print(f"\n因果修正系数: {factor}")

    explanation = ck.explain_event(test_event)
    print("\n因果解释:")
    print(explanation)

    cf = ck.counterfactual_risk(
        test_event,
        {"action": "replace_supplier", "target": "manufacturer:Stanley Black & Decker"},
    )
    import json
    print("\n反事实推理:", json.dumps(cf, ensure_ascii=False, indent=2))
