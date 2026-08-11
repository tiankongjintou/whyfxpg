"""数据源监控页面。"""

import streamlit as st

from whyfxpg.webui.queries import (
    get_health_trend,
    get_lineage,
    get_source_health,
    get_source_metrics,
    get_source_status,
)


def _status_color(status: str) -> str:
    return {
        "ok": "🟢",
        "degraded": "🟡",
        "stale": "🟠",
        "error": "🔴",
    }.get(status, "⚪")


def render() -> None:
    st.title("🌐 数据源监控")
    from whyfxpg.webui.screens._page_guide import page_guide
    page_guide(
        "🌐 数据源监控",
        "实时监控各外部数据源（监管机构官网、召回数据库等）的连接状态、健康评分与数据新鲜度。",
        [
            "「运行状态」表格展示所有已配置数据源的实时状态，红色表示连接异常需处理",
            "「健康评分」表格显示各数据源的综合评分，包含新鲜度、延迟、覆盖率等维度",
            "选中具体数据源后可查看其历史健康趋势折线图，横轴为时间，纵轴为各项评分",
            "如持续出现错误，可检查该数据源 URL 是否有效、网络是否可达",
        ],
    )

    status_df = get_source_status()
    health_df = get_source_health()

    st.subheader("运行状态")
    st.dataframe(
        status_df.rename(
            columns={
                "name": "名称",
                "source_type": "类型",
                "url": "链接",
                "enabled": "启用",
                "check_interval": "检查间隔",
                "last_check_at": "上次检查",
                "status": "状态",
                "last_content_length": "内容长度",
                "error_msg": "错误信息",
            }
        ),
        width='stretch',
        hide_index=True,
    )

    st.subheader("健康评分")
    if health_df is not None and not health_df.empty:
        health_df["状态图标"] = health_df["status"].map(_status_color)
        st.dataframe(
            health_df[
                [
                    "状态图标",
                    "source_id",
                    "health_score",
                    "freshness_score",
                    "latency_ms",
                    "coverage_score",
                    "error_rate",
                    "last_check_at",
                ]
            ].rename(
                columns={
                    "source_id": "来源 ID",
                    "health_score": "健康分",
                    "freshness_score": "新鲜度",
                    "latency_ms": "延迟 (ms)",
                    "coverage_score": "覆盖率",
                    "error_rate": "错误率",
                    "last_check_at": "上次检查",
                }
            ),
            width='stretch',
            hide_index=True,
        )
    else:
        st.info("暂无数据源健康数据，请先运行采集。")

    st.subheader("来源详情")
    source_ids = list(health_df["source_id"].unique()) if health_df is not None and not health_df.empty else []
    if source_ids:
        selected = st.selectbox("选择数据源", source_ids)
        metrics = get_source_metrics(selected)
        st.json(metrics)

        trend_df = get_health_trend(selected)
        if trend_df is not None and not trend_df.empty:
            st.line_chart(
                trend_df.set_index("captured_at")[
                    ["health_score", "freshness_score", "coverage_score", "error_rate"]
                ]
            )
        else:
            st.info("暂无历史健康趋势数据，运行 SourceMonitorService 后会生成快照。")
    else:
        st.info("无可用数据源。")

    st.subheader("事件血缘追踪")
    event_id = st.text_input("输入事件 ID", value="")
    if event_id:
        lineage = get_lineage(event_id)
        st.json(lineage)

    if st.button("🔄 刷新数据源状态"):
        st.rerun()
