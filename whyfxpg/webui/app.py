"""
WHYFXPG 海关进口机电产品风险看板
Streamlit Web 主入口

职责：
  - 设置页面全局配置
  - 渲染侧边栏导航
  - 根据用户选择的页面，调用 whyfxpg.webui.screens 中对应的 render() 函数

页面实现已拆分到 whyfxpg/webui/screens/*.py：
  - overview          风险总览仪表盘
  - bigscreen         风险态势大屏
  - risk_events       风险事件列表
  - review            人工复核界面
  - alerts            预警中心
  - reports           报告中心
  - causal            因果知识图谱
  - sources           数据源监控
"""

import sys
from datetime import datetime
from pathlib import Path

# 确保项目根目录在路径中
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st

from whyfxpg.services.notification_service import NotificationService
from whyfxpg.webui.screens import PAGES

st.set_page_config(
    page_title="产品风险评估系统",
    page_icon="🚨",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── 侧边栏 ─────────────────────────────────────────────────

st.sidebar.title("🚨 产品风险评估系统")
st.sidebar.caption("进口机电产品风险评价系统")

try:
    unread = NotificationService().unread_count()
    if unread:
        st.sidebar.error(f"🔔 未读通知：{unread} 条")
except Exception:  # noqa: BLE001, S110 — 刻意用法(见 TD03)
    pass

st.sidebar.divider()

page = st.sidebar.radio(
    "导航",
    list(PAGES.keys()),
    index=0,
)

st.sidebar.divider()
st.sidebar.caption(f"最后更新：{datetime.now().strftime('%Y-%m-%d %H:%M')}")  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计

# ── 主页面 ─────────────────────────────────────────────────

render_page = PAGES[page]
render_page()
