"""风险态势大屏页面（v2：基于 DashboardBuilderService 的可配置渲染）。"""

from typing import Any

import pandas as pd
import streamlit as st

from whyfxpg.services.dashboard_builder import (
    DashboardBuilderService,
    build_default_dashboard_service,
)
from whyfxpg.webui.dashboard_models import (
    DashboardContext,
    DashboardViewModel,
    ExportFormat,
    WidgetLayout,
    WidgetViewModel,
)


def _get_builder_service():
    """Wire the production dashboard service for this screen."""
    return build_default_dashboard_service()


def _metric_value(data: Any) -> int:
    """Coerce widget data to a scalar for st.metric."""
    try:
        return int(data) if data is not None else 0
    except (TypeError, ValueError):
        return 0


def _render_widget(
    widget: WidgetViewModel,
    service: DashboardBuilderService,
    view_model: DashboardViewModel,
) -> None:
    """Render a single widget based on its type."""
    st.subheader(widget.title)
    data = widget.data

    if widget.type == "metric":
        st.metric(label=widget.title, value=_metric_value(data))
        return

    if isinstance(data, dict):
        data = pd.DataFrame(
            list(data.items()), columns=["key", "value"]
        )

    if not isinstance(data, pd.DataFrame) or data.empty:
        st.caption("暂无数据")
        return

    if widget.type == "line":
        chart_data = data.copy()
        if "date" in chart_data.columns:
            chart_data = chart_data.set_index("date")
        st.line_chart(chart_data, width='stretch')

    elif widget.type == "bar":
        chart_data = data.copy()
        non_numeric = [c for c in chart_data.columns if not pd.api.types.is_numeric_dtype(chart_data[c])]
        if len(non_numeric) == 1:
            chart_data = chart_data.set_index(non_numeric[0])
        st.bar_chart(chart_data, width='stretch')

    elif widget.type == "table":
        st.dataframe(data, width='stretch')
        _maybe_render_drill_down(widget, service, view_model)

    elif widget.type == "event_stream" or widget.type == "pie" or widget.type == "heatmap":
        st.dataframe(data, width='stretch')

    else:
        st.caption(f"不支持的 widget 类型: {widget.type}")


def _maybe_render_drill_down(
    widget: WidgetViewModel,
    service: DashboardBuilderService,
    view_model: DashboardViewModel,
) -> None:
    """If a table widget declares a drill-down dimension, render a selector."""
    if widget.drill_down is None:
        return
    if view_model.context is None:
        return
    dimension = widget.drill_down.dimension
    if dimension not in widget.data.columns:
        return

    values = sorted(widget.data[dimension].dropna().unique().tolist())
    if not values:
        return

    col1, col2 = st.columns([0.7, 0.3])
    with col1:
        selected = st.selectbox(
            f"下钻 {dimension}",
            ["全部"] + [str(v) for v in values],
            key=f"drill_select_{widget.widget_id}",
        )
    with col2:
        st.write("")
        st.write("")
        if st.button("应用", key=f"drill_apply_{widget.widget_id}"):
            if selected == "全部":
                new_filters = dict(view_model.context.filters)
                new_filters.pop(dimension, None)
            else:
                new_filters = dict(view_model.context.filters)
                new_filters[dimension] = selected
            st.session_state["bigscreen_filters"] = new_filters
            st.rerun()


def _group_widgets_by_row(
    widgets: list[WidgetViewModel],
) -> dict[int, list[WidgetViewModel]]:
    """Group widgets by layout row, assigning a fallback row when absent."""
    rows: dict[int, list[WidgetViewModel]] = {}
    for index, widget in enumerate(widgets):
        layout = getattr(widget, "layout", None) or WidgetLayout(row=index, col=0, col_span=1)
        rows.setdefault(layout.row, []).append(widget)
    return rows


def render() -> None:
    """Render the configurable risk big-screen dashboard."""
    st.title("🖥️ 进口机电产品风险态势大屏")
    from whyfxpg.webui.screens._page_guide import page_guide
    page_guide(
        "🖥️ 风险态势大屏",
        "实时展示全系统风险监测核心指标与趋势，支持按维度下钻筛选和 Excel 导出。",
        [
            "大屏数据每 60 秒自动刷新，无需手动操作；也可点击「导出 Excel」保存当前视图",
            "点击表格 widget 的「下钻」下拉框可按特定维度深入查看数据分布",
            "存在筛选条件时左上角会显示筛选标签，点击「清除筛选」可恢复全局视图",
        ],
    )
    st.caption("实时风险监测与趋势分析")

    service = _get_builder_service()
    template = service.load_template("default")

    filters = st.session_state.get("bigscreen_filters", None)
    if filters is None:
        filters = {}
    context = DashboardContext(filters=filters)
    view_model = service.build(template, context)

    # Action bar: active filters + export
    header_cols = st.columns([0.75, 0.25])
    with header_cols[0]:
        if filters:
            filter_text = " | ".join(f"{k}={v}" for k, v in filters.items())
            st.info(f"当前下钻筛选: {filter_text}")
            if st.button("清除筛选", key="bigscreen_clear_filters"):
                st.session_state["bigscreen_filters"] = {}
                st.rerun()
    with header_cols[1]:
        st.write("")
        st.write("")
        if st.button("导出 Excel", key="bigscreen_export"):
            try:
                path = service.export(view_model, ExportFormat.EXCEL)
                st.success(f"已导出: {path}")
            except NotImplementedError as exc:
                st.error(str(exc))

    rows = _group_widgets_by_row(view_model.widgets)
    for row_index in sorted(rows):
        row_widgets = rows[row_index]
        total_span = sum(((w.layout.col_span if w.layout else 1) or 1) for w in row_widgets)
        cols = st.columns(total_span)
        col_pointer = 0
        for widget in row_widgets:
            span = (widget.layout.col_span if widget.layout else 1) or 1
            with cols[col_pointer]:
                _render_widget(widget, service, view_model)
            col_pointer += span

    st.divider()
    st.caption(f"生成时间: {view_model.generated_at}")
