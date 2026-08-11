"""
🖥️ 产品风险评估系统 风险态势大屏

纯 Streamlit 原生组件实现，不依赖 plotly/pyecharts/folium 等第三方大屏库。
使用 st.metric / st.line_chart / st.bar_chart / st.dataframe 组合出
适合会议室/值班室展示的实时风险看板。

如需更炫效果，可后续替换为 streamlit-echarts / pyecharts。
"""


import pandas as pd
import streamlit as st

from whyfxpg.webui.presenters.bigscreen_presenter import (
    BigScreenPresenter,
    BigScreenViewModel,
)
from whyfxpg.webui.read_model import DashboardReadModel

COLOR_EMOJI = {
    "S": "🔴",
    "M": "🟡",
    "L": "🟢",
    "A": "🔵",
}

DEFAULT_EMOJI = "⚪"


def _color_level(level: str) -> str:
    return COLOR_EMOJI.get(level, DEFAULT_EMOJI)


def render_bigscreen(view_model: BigScreenViewModel | None = None):
    # 大屏自动刷新：每 60 秒整页 reload
    st.markdown(
        '<meta http-equiv="refresh" content="60">',
        unsafe_allow_html=True,
    )

    if view_model is None:
        view_model = BigScreenPresenter(DashboardReadModel()).present()

    st.title("🖥️ 进口机电产品风险态势大屏")
    st.caption(
        f"数据每 60 秒自动刷新 | 当前时间：{view_model.generated_at} | 来源：data/whyfxpg.db"
    )

    # ── 汇总指标 ─────────────────────────────────────────────────
    level = view_model.level_dist

    row1 = st.columns(5)
    row1[0].metric("风险事件总数", f"{view_model.total_events:,}")
    row1[1].metric("🔴 S级（高风险）", level.get("S", 0))
    row1[2].metric("🟡 M级（中等风险）", level.get("M", 0))
    row1[3].metric("📮 待处理预警", view_model.pending_alerts)
    row1[4].metric("🌍 涉及国别数", view_model.country_count)

    st.divider()

    # ── 图表区 ─────────────────────────────────────────────────────
    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("📈 近 30 天风险事件趋势")
        df_trend = view_model.trend
        if not df_trend.empty:
            df_trend = df_trend.rename(columns={"date": "日期", "cnt": "事件数"})
            df_trend["日期"] = pd.to_datetime(df_trend["日期"])
            df_trend = df_trend.set_index("日期")
            st.line_chart(df_trend, use_container_width=True)
        else:
            st.info("暂无趋势数据")

    with col_right:
        st.subheader("🧩 危害类型 Top10")
        df_hazard = view_model.hazard_distribution
        if not df_hazard.empty:
            df_hazard = df_hazard.rename(columns={"type": "危害类型", "cnt": "事件数"})
            df_hazard = df_hazard.set_index("危害类型")
            st.bar_chart(df_hazard, use_container_width=True)
        else:
            st.info("暂无危害类型数据")

    col_left2, col_right2 = st.columns(2)

    with col_left2:
        st.subheader("🌍 国别风险 Top10")
        df_country = view_model.country_summary
        if not df_country.empty:
            df_country_plot = (
                df_country[["country", "event_count"]]
                .rename(columns={"country": "国别", "event_count": "事件数"})
                .set_index("国别")
            )
            st.bar_chart(df_country_plot, use_container_width=True)
        else:
            st.info("暂无国别数据")

    with col_right2:
        st.subheader("⚖️ 风险等级分布")
        if level:
            df_level = pd.DataFrame(
                {"等级": list(level.keys()), "数量": list(level.values())}
            ).set_index("等级")
            st.bar_chart(df_level, use_container_width=True)
        else:
            st.info("暂无等级分布数据")

    st.divider()

    # ── 最新高风险 & 预警 ──────────────────────────────────────────
    col_left3, col_right3 = st.columns([3, 2])

    with col_left3:
        st.subheader("🚨 最新 S/M 级高风险事件")
        df_recent = view_model.recent_high_risk
        if not df_recent.empty:
            df_recent["等级"] = df_recent["rs_level"].map(_color_level)
            display = df_recent[[
                "等级", "publish_date", "product_name", "brand",
                "country", "hazard_type", "rs_level", "total_score",
            ]].rename(
                columns={
                    "publish_date": "发布日期",
                    "product_name": "产品",
                    "brand": "品牌",
                    "country": "国别",
                    "hazard_type": "危害类型",
                    "rs_level": "风险等级",
                    "total_score": "风险分",
                }
            )
            st.dataframe(display, use_container_width=True, hide_index=True)
        else:
            st.info("暂无 S/M 级高风险事件")

    with col_right3:
        st.subheader("🔔 最近预警")
        df_alerts = view_model.alerts
        if not df_alerts.empty:
            df_alerts = df_alerts[[
                "triggered_at", "rule_name", "severity", "status"
            ]].rename(
                columns={
                    "triggered_at": "触发时间",
                    "rule_name": "规则",
                    "severity": "严重度",
                    "status": "状态",
                }
            )
            st.dataframe(df_alerts, use_container_width=True, hide_index=True)
        else:
            st.info("暂无预警记录")

    st.divider()
    st.caption(
        "提示：本大屏使用 Streamlit 原生组件。如需 ECharts 地图/3D/轮播等特效，可后续集成 streamlit-echarts / pyecharts。"
    )
