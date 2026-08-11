"""T6 测试：CausalKnowledge 拆分为 CausalGraphStore + CausalReasoning + CausalPort"""

from typing import Any

import pytest

from whyfxpg.adapters.causal import InMemoryCausalAdapter
from whyfxpg.core.causal_knowledge import CausalKnowledge
from whyfxpg.core.db import get_db_connection
from whyfxpg.core.stores import CausalGraphStore, UnitOfWork
from whyfxpg.ports.causal_port import CausalPort
from whyfxpg.services.causal_reasoning import CausalReasoning


@pytest.fixture
def ck(initialized_db: str) -> CausalKnowledge:
    return CausalKnowledge(initialized_db)


@pytest.fixture
def uow(initialized_db: str) -> UnitOfWork:  # type: ignore[misc]
    with UnitOfWork(initialized_db) as uow:
        yield uow


@pytest.fixture
def store(uow: UnitOfWork) -> CausalGraphStore:
    return CausalGraphStore(uow)


# ────────────────────────────────────────────────────────────────
# CausalGraphStore
# ────────────────────────────────────────────────────────────────


def test_causal_graph_store_schema_and_crud(store: CausalGraphStore) -> None:
    store.ensure_schema()

    node_id = store.add_node(
        "component_type:电容器",
        "component_type",
        "电容器",
        risk_score=0.7,
        properties={"note": "测试"},
        source="test",
    )
    assert node_id == "component_type:电容器"

    node = store.get_node(node_id)
    assert node is not None
    assert node["node_type"] == "component_type"
    assert node["name"] == "电容器"
    assert node["risk_score"] == 0.7
    assert node["properties"] == {"note": "测试"}

    store.add_node(
        "hazard_category:电击风险",
        "hazard_category",
        "电击风险",
        risk_score=0.8,
        source="test",
    )
    edge_id = store.add_edge(
        "component_type:电容器|causes|hazard_category:电击风险",
        "component_type:电容器",
        "hazard_category:电击风险",
        "causes",
        weight=0.8,
        evidence="test",
        source="test",
    )
    assert edge_id.startswith("component_type:电容器")

    chain = store.get_causal_chain("component_type:电容器", depth=3)
    assert len(chain) == 1
    assert chain[0]["to"] == "hazard_category:电击风险"
    assert chain[0]["edge_type"] == "causes"

    stats = store.get_statistics()
    assert stats["nodes"] == 2
    assert stats["edges"] == 1

    found = store.find_nodes("component_type", "%")
    assert len(found) == 1


# ────────────────────────────────────────────────────────────────
# CausalReasoning 纯内存
# ────────────────────────────────────────────────────────────────


def test_causal_reasoning_factor_and_explain() -> None:
    adapter = InMemoryCausalAdapter()
    adapter.add_node("country:测试国", "country", "测试国", risk_score=0.9)
    adapter.add_node("manufacturer:TEST-MFR", "manufacturer", "TEST-MFR", risk_score=0.7)
    adapter.add_node("component_type:电容器", "component_type", "电容器", risk_score=0.8)
    adapter.add_node("hazard_category:电击风险", "hazard_category", "电击风险", risk_score=0.8)
    adapter.add_edge(
        "manufacturer:TEST-MFR|uses|component_type:电容器",
        "manufacturer:TEST-MFR",
        "component_type:电容器",
        "uses",
        weight=0.6,
    )
    adapter.add_edge(
        "component_type:电容器|causes|hazard_category:电击风险",
        "component_type:电容器",
        "hazard_category:电击风险",
        "causes",
        weight=0.8,
    )

    event: dict[str, Any] = {
        "manufacturer": "TEST-MFR",
        "country": "测试国",
        "hazard_type": "电击风险",
        "product_category": "普通机电",
    }
    factor = adapter.factor(event)
    assert 0.5 <= factor <= 2.0

    explanation = adapter.explain(event)
    assert "测试国" in explanation or "电容器" in explanation or "TEST-MFR" in explanation

    cf = adapter.counterfactual(event, {"component_type": "电阻"})
    assert "original_factor" in cf
    assert "counterfactual_factor" in cf


def test_causal_reasoning_downstream_risk() -> None:
    adapter = InMemoryCausalAdapter()
    adapter.add_node("component_type:电池模组", "component_type", "电池模组", risk_score=0.9)
    adapter.add_node("hazard_category:火灾风险", "hazard_category", "火灾风险", risk_score=0.9)
    adapter.add_edge(
        "component_type:电池模组|causes|hazard_category:火灾风险",
        "component_type:电池模组",
        "hazard_category:火灾风险",
        "causes",
        weight=0.9,
    )
    reasoning = CausalReasoning()
    downstream = reasoning.compute_downstream_risk("component_type:电池模组", adapter.graph_view)
    assert downstream > 0.5


# ────────────────────────────────────────────────────────────────
# CausalKnowledge facade 仍兼容旧接口
# ────────────────────────────────────────────────────────────────


def test_ck_seed_and_stats(ck: CausalKnowledge) -> None:
    result = ck.seed_initial_knowledge()
    assert result["status"] == "success"

    stats = ck.get_statistics()
    assert stats["nodes"] > 0
    assert stats["edges"] > 0

    # 二次 seed 幂等
    result2 = ck.seed_initial_knowledge()
    assert result2["status"] == "skipped"


def test_ck_add_edge_auto_creates_nodes(ck: CausalKnowledge) -> None:
    ck.seed_initial_knowledge()
    ck.add_edge(
        "component_type:新零件",
        "hazard_category:新风险",
        "causes",
        weight=0.5,
        evidence="auto create test",
    )
    assert ck.get_node("component_type:新零件") is not None
    assert ck.get_node("hazard_category:新风险") is not None


def test_ck_port_methods(ck: CausalKnowledge) -> None:
    ck.seed_initial_knowledge()
    event: dict[str, Any] = {
        "manufacturer": "Stanley Black & Decker",
        "country": "美国",
        "hazard_type": "电击风险",
        "product_category": "电动工具",
    }
    factor = ck.factor(event)
    assert 0.5 <= factor <= 2.0

    explanation = ck.explain(event)
    assert isinstance(explanation, str)
    assert len(explanation) > 0

    cf = ck.counterfactual(event, {"country": "巴基斯坦"})
    assert cf["counterfactual_factor"] >= cf["original_factor"]


# ────────────────────────────────────────────────────────────────
# RiskModel 可注入 InMemoryCausalAdapter
# ────────────────────────────────────────────────────────────────


def test_risk_model_accepts_in_memory_causal_port(
    initialized_db: str, temp_config_dir: str
) -> None:
    from whyfxpg.core.risk_model import RiskModel
    from whyfxpg.core.stores import RiskEventStore

    # 准备一个未评分事件
    conn = get_db_connection(initialized_db)
    conn.execute(
        """
        INSERT INTO risk_events (event_id, source_id, publish_date, title,
                                 product_category, country, hazard_type, manufacturer,
                                 source_url, severity_level)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "evt-001",
            "test_api",
            "2026-01-01",
            "测试召回",
            "普通机电",
            "unknown",
            "电击风险",
            "TEST-MFR",
            "http://example.com",
            "严重",
        ),
    )
    conn.commit()
    conn.close()

    adapter = InMemoryCausalAdapter()
    adapter.add_node("country:unknown", "country", "unknown", risk_score=1.0)
    adapter.add_node("manufacturer:TEST-MFR", "manufacturer", "TEST-MFR", risk_score=0.6)
    adapter.add_node("hazard_category:电击风险", "hazard_category", "电击风险", risk_score=0.8)
    adapter.add_edge(
        "manufacturer:TEST-MFR|uses|hazard_category:电击风险",
        "manufacturer:TEST-MFR",
        "hazard_category:电击风险",
        "uses",
        weight=0.5,
    )

    model = RiskModel(
        config_dir=temp_config_dir,
        db_path=initialized_db,
        causal_port=adapter,
    )
    result = model.run()
    assert result["records_processed"] == 1
    assert result["records_created"] == 1

    # 检查事件已被评分
    with UnitOfWork(initialized_db) as uow:
        store = RiskEventStore(uow)
        event = store.fetch_pending()[0] if store.fetch_pending() else None  # noqa: F841 — 刻意用法(见 TD03)
        # 已评分，fetch_pending 不返回，但已评分记录应含 ss_score
    conn = get_db_connection(initialized_db)
    row = conn.execute(
        "SELECT ss_score, ps_score, total_score, rs_level FROM risk_events WHERE event_id = ?",
        ("evt-001",),
    ).fetchone()
    conn.close()
    assert row is not None
    assert row["ss_score"] is not None
    assert row["total_score"] is not None


# ────────────────────────────────────────────────────────────────
# CausalPort 契约
# ────────────────────────────────────────────────────────────────


def test_causal_port_abc_is_satisfied_by_in_memory_adapter() -> None:
    adapter = InMemoryCausalAdapter()
    assert isinstance(adapter, CausalPort)
