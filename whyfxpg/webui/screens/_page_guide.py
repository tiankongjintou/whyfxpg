"""页面顶部操作指引组件 — 可折叠使用说明。"""
from __future__ import annotations

import streamlit as st


def page_guide(title: str, description: str, tips: list[str] | None = None) -> None:
    """在 st.title 之后立即调用，渲染可折叠的页面指引。

    Args:
        title: 指引小标题（如 "📊 风险总览"）
        description: 一句话页面用途说明
        tips: 可选的操作提示列表，每条以 • 开头显示
    """
    with st.expander(f"📖 {title} · 操作指引", expanded=False):
        st.markdown(f"**本页用途：**{description}")
        if tips:
            st.markdown("**操作提示：**")
            for tip in tips:
                st.markdown(f"&nbsp;&nbsp;&nbsp;• {tip}")
