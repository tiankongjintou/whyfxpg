"""WHYFXPG Web UI 页面集合。

为避免与 Streamlit 自动 multipage `pages/` 目录冲突，
本包使用 `screens/` 作为手动导航的页面模块目录。
每个模块暴露一个 `render()` 函数，由 `app.py` 根据侧边栏 radio 调用。
"""

from collections.abc import Callable

from whyfxpg.webui.screens.admin.dimension_admin import render as render_dimension_admin
from whyfxpg.webui.screens.admin.model_admin import render as render_model_admin
from whyfxpg.webui.screens.admin.rule_admin import render as render_rule_admin
from whyfxpg.webui.screens.admin.source_admin import render as render_source_admin
from whyfxpg.webui.screens.admin.taxonomy_admin import render as render_taxonomy_admin
from whyfxpg.webui.screens.alerts import render as render_alerts
from whyfxpg.webui.screens.bigscreen import render as render_bigscreen
from whyfxpg.webui.screens.causal import render as render_causal
from whyfxpg.webui.screens.notifications import render as render_notifications
from whyfxpg.webui.screens.overview import render as render_overview
from whyfxpg.webui.screens.reports import render as render_reports
from whyfxpg.webui.screens.review import render as render_review
from whyfxpg.webui.screens.risk_events import render as render_risk_events
from whyfxpg.webui.screens.sources import render as render_sources

PAGES: dict[str, Callable[[], None]] = {
    "📊 风险总览": render_overview,
    "🖥️ 风险态势大屏": render_bigscreen,
    "📋 风险事件": render_risk_events,
    "✅ 人工复核": render_review,
    "🔔 预警中心": render_alerts,
    "🔔 通知中心": render_notifications,
    "📄 报告中心": render_reports,
    "🔗 因果知识图谱": render_causal,
    "🌐 数据源监控": render_sources,
    "⚙️ 数据源管理": render_source_admin,
    "⚙️ 预警规则管理": render_rule_admin,
    "⚙️ 风险模型管理": render_model_admin,
    "⚙️ 风险维度管理": render_dimension_admin,
    "⚙️ 分类法管理": render_taxonomy_admin,
}
