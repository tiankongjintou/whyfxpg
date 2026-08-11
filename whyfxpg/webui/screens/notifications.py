"""通知中心页面。"""

import streamlit as st

from whyfxpg.services.notification_service import NotificationService


def render() -> None:
    st.title("🔔 通知中心")
    from whyfxpg.webui.screens._page_guide import page_guide
    page_guide(
        "🔔 通知中心",
        "展示流水线运行异常、数据源连接失败等需要人工关注的系统事件通知。",
        [
            "系统自动推送流水线异常、数据源断开等关键事件通知，无需手动订阅",
            "点击「标为已读」将通知移出未读列表；点击「忽略」则永久屏蔽该类通知",
            "如持续收到同一通知，说明底层问题未解决，建议检查对应数据源或流水线状态",
        ],
    )
    st.caption("展示流水线失败、数据源异常等需要人工关注的系统事件。")

    svc = NotificationService()
    notifications = svc.list_unread(limit=100)

    st.metric("未读通知", len(notifications))
    st.divider()

    if not notifications:
        st.success("当前没有未读通知。")
        return

    for n in notifications:
        with st.container(border=True):
            cols = st.columns([0.15, 0.6, 0.25])
            severity_emoji = {"error": "🔴", "warning": "🟡", "info": "🔵"}.get(n.severity, "⚪")
            cols[0].markdown(f"{severity_emoji} **{n.notification_type}**")
            cols[1].markdown(f"**{n.title}**  \n" + (n.message or ""))
            cols[2].caption(f"{n.created_at}")
            btn_cols = st.columns([0.5, 0.5])
            if btn_cols[0].button("标为已读", key=f"read_{n.notification_id}"):
                svc.mark_read(n.notification_id)
                st.rerun()
            if btn_cols[1].button("忽略", key=f"dismiss_{n.notification_id}"):
                svc.mark_dismissed(n.notification_id)
                st.rerun()
