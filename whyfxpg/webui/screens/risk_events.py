"""风险事件列表页面。"""

import streamlit as st

from whyfxpg.webui.queries import get_events, get_lineage


def render() -> None:
    st.title("📋 风险事件列表")
    from whyfxpg.webui.screens._page_guide import page_guide
    page_guide(
        "📋 风险事件",
        "查看系统中所有采集到的风险事件，支持按等级、国别、危害类型多维筛选。",
        [
            "使用「风险等级」「国别搜索」「危害类型搜索」三个筛选器精确定位目标事件",
            "下方的「事件血缘追踪」可查看任意事件从采集到评分的完整链路",
            "血缘 JSON 可用于追溯数据来源和评分依据",
        ],
    )
    df = get_events(limit=500)

    col1, col2, col3 = st.columns(3)
    with col1:
        rs_filter = st.multiselect("风险等级", ["S", "M", "L", "A"], default=["S", "M", "L", "A"])
    with col2:
        country_filter = st.text_input("国别搜索")
    with col3:
        hazard_filter = st.text_input("危害类型搜索")

    if rs_filter:
        df = df[df["rs_level"].isin(rs_filter)] if df is not None and not df.empty else df
    if country_filter:
        df = df[df["country"].str.contains(country_filter, na=False, case=False)] if df is not None and not df.empty else df
    if hazard_filter:
        df = df[df["hazard_type"].str.contains(hazard_filter, na=False, case=False)] if df is not None and not df.empty else df

    st.dataframe(
        df.rename(
            columns={
                "product_name": "产品",
                "brand": "品牌",
                "model": "型号",
                "country": "国别",
                "manufacturer": "制造商",
                "hazard_type": "危害类型",
                "severity_level": "严重度",
                "rs_level": "风险等级",
                "total_score": "风险分",
                "causal_factor": "因果因子",
                "extraction_confidence": "置信度",
                "review_status": "复核状态",
                "publish_date": "发布日期",
            }
        )[
            [
                "产品",
                "品牌",
                "国别",
                "制造商",
                "危害类型",
                "风险等级",
                "风险分",
                "因果因子",
                "置信度",
                "复核状态",
            ]
        ],
        width='stretch',
        hide_index=True,
    )
    st.caption(f"共 {len(df)} 条记录")

    st.divider()
    st.subheader("🔍 事件血缘追踪")
    if df is None or df.empty:
        st.info("暂无可追溯事件")
        return
    selected_event = st.selectbox(
        "选择事件查看血缘",
        options=df["event_id"].tolist(),
        format_func=lambda eid: f"{eid} - {df.loc[df['event_id'] == eid, 'product_name'].values[0]} ({df.loc[df['event_id'] == eid, 'country'].values[0]})",
    )
    if selected_event:
        lineage = get_lineage(selected_event)
        with st.expander("查看完整血缘链", expanded=True):
            st.json(lineage, expanded=False)
