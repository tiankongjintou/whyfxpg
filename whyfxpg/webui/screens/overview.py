"""风险总览仪表盘页面。"""


import streamlit as st

from whyfxpg.services.domain_registry import DomainRegistryService
from whyfxpg.webui.queries import get_country_summary, get_events, get_summary
from whyfxpg.webui.screens._page_guide import page_guide


def _render_domain_selector() -> DomainRegistryService:
    """Render the domain selector and return the registry service."""
    service = DomainRegistryService()
    domains = service.list()
    if not domains:
        return service

    options = {p.domain_id: f"{p.name} ({p.domain_id})" for p in domains}
    active_id = service.active_id()
    current_index = list(options.keys()).index(active_id) if active_id in options else 0

    selected = st.selectbox(
        "选择评估领域",
        options=options,
        index=current_index,
        key="overview_domain_selector",
    )
    if selected != active_id:
        service.switch(selected)
        st.session_state["active_domain_id"] = selected
        st.rerun()

    active = service.active()
    if active:
        st.caption(f"当前领域：{active.name} — {active.description}")
    return service


def render() -> None:
    st.title("📊 风险总览仪表盘")
    page_guide(
        "📊 风险总览",
        "概览全系统风险事件分布与整体健康状态，支持按领域切换查看不同行业的风险数据。",
        [
            "使用左上角「选择评估领域」切换不同行业域，数据随之变化",
            "表格默认显示全部等级事件，可配合风险等级下拉框快速筛选高危事件（S/M级）",
            "点击顶部「🔄 刷新」按钮可更新最新数据",
        ],
    )
    _render_domain_selector()
    summary = get_summary()
    level = summary["level_dist"]

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("风险事件总数", f"{summary['total_events']:,}")
    col2.metric("🔴 S级（高风险）", level.get("S", 0))
    col3.metric("🟡 M级（中等）", level.get("M", 0))
    col4.metric("📮 待处理预警", summary["pending_alerts"])

    col5, col6, col7, col8 = st.columns(4)
    col5.metric("🟢 L级（低风险）", level.get("L", 0))
    col6.metric("🔵 A级（可接受）", level.get("A", 0))
    col7.metric("✅ 已复核事件", summary["reviewed_count"])
    col8.metric("✅ 已处理预警", summary["processed_alerts"])

    st.divider()
    st.subheader("🌍 国别风险分布（Top 20）")
    df_country = get_country_summary()
    if df_country is not None and not df_country.empty:
        st.dataframe(
            df_country.rename(
                columns={
                    "country": "国别",
                    "event_count": "事件数",
                    "s_count": "S",
                    "m_count": "M",
                    "l_count": "L",
                    "a_count": "A",
                    "latest_event_date": "最新事件",
                }
            ),
            width='stretch',
            hide_index=True,
        )
    else:
        st.info("暂无国别数据，请先运行数据采集和评分流程。")

    st.divider()
    st.subheader("⚠️ S/M级高风险事件")
    df_events = get_events(limit=50)
    high_risk = df_events[df_events["rs_level"].isin(["S", "M"])] if df_events is not None and not df_events.empty else df_events
    if high_risk is not None and not high_risk.empty:
        display_cols = [
            "product_name",
            "brand",
            "country",
            "hazard_type",
            "rs_level",
            "total_score",
            "causal_factor",
        ]
        st.dataframe(
            high_risk[display_cols].rename(
                columns={
                    "product_name": "产品",
                    "brand": "品牌",
                    "country": "国别",
                    "hazard_type": "危害类型",
                    "rs_level": "风险等级",
                    "total_score": "风险分",
                    "causal_factor": "因果因子",
                }
            ),
            width='stretch',
            hide_index=True,
        )
    else:
        st.info("暂无 S/M 级高风险事件。")
