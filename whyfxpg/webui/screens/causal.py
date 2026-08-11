"""因果知识图谱页面。"""

import streamlit as st

from whyfxpg.services.causal_service import CausalService
from whyfxpg.webui.queries import get_events


def render() -> None:
    st.title("🔗 因果知识图谱")
    from whyfxpg.webui.screens._page_guide import page_guide
    page_guide(
        "🔗 因果知识图谱",
        "基于供应商→零部件→制造缺陷→危害类型→事故严重度因果链的风险推理与反事实分析引擎。",
        [
            "上半部分「因果风险解释」：选择一个具体事件，查看系统如何通过因果链推导出其风险分",
            "「因果修正系数」>1 表示因果链条放大风险，<1 表示降低风险，帮助理解评分逻辑",
            "下半部分「反事实推理」：模拟干预动作后重新计算风险，用于评估改进措施的效果",
            "反事实推理对于制定供应链改进策略具有重要参考价值",
        ],
    )
    st.caption("基于'供应商 → 零部件 → 制造缺陷 → 危害类型 → 事故严重度'因果链的风险推理引擎。")

    service = CausalService()

    stats = service.get_statistics()
    col1, col2, col3 = st.columns(3)
    col1.metric("因果节点数", stats["total_nodes"])
    col2.metric("因果边数", stats["total_edges"])
    col3.metric("因果链平均权重", f"{stats.get('avg_causal_weight', 0):.3f}")

    st.divider()

    st.subheader("🔍 因果风险解释")
    df = get_events(limit=100)
    event_options = {
        f"{r['product_name'] or '?'} | {r['country']} | {r['rs_level']}": r["event_id"]
        for _, r in df.iterrows()
    }
    selected = st.selectbox("选择事件进行因果解释", list(event_options.keys()))

    if selected:
        event_id = event_options[selected]
        event = df[df["event_id"] == event_id].iloc[0]
        event_dict = event.to_dict()

        with st.expander("📖 因果解释详情", expanded=True):
            explanation = service.explain_event(event_dict)
            st.text(explanation)

        col1, col2 = st.columns(2)
        with col1:
            cf = service.get_causal_factor(event_dict)
            st.metric(
                "因果修正系数",
                f"{cf:.3f}",
                delta="↑ 风险放大" if cf > 1 else "↓ 风险缩小" if cf < 1 else "中性",
            )
        with col2:
            mfr = event.get("manufacturer", "")
            if mfr:
                node = service.get_node(f"manufacturer:{mfr}")
                if node:
                    st.metric("制造商节点风险分", f"{node.get('risk_score', 'N/A')}")

    st.divider()
    st.subheader("🔄 反事实推理")
    col1, col2 = st.columns(2)
    with col1:
        cf_action = st.selectbox("干预动作", ["replace_supplier", "upgrade_standard"])
    with col2:
        cf_event_sel = st.selectbox("选择事件", list(event_options.keys())[:20])

    if cf_event_sel and st.button("计算反事实风险"):
        eid = event_options[cf_event_sel]
        ev = df[df["event_id"] == eid].iloc[0].to_dict()
        intervention = {"action": cf_action}
        result = service.counterfactual_risk(ev, intervention)
        st.json(result)
