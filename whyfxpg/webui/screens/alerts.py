"""预警中心页面。"""

import streamlit as st

from whyfxpg.webui.queries import get_alerts


def render() -> None:
    st.title("🔔 预警中心")
    from whyfxpg.webui.screens._page_guide import page_guide
    page_guide(
        "🔔 预警中心",
        "集中管理所有触发规则产生的预警事件，可对每条预警进行确认或忽略处理。",
        [
            "默认仅显示「待处理」状态的预警，可调整状态筛选器查看已处理的历史预警",
            "选择具体预警后可填写处理意见并点击「确认预警」或「忽略预警」",
            "底部「预警血缘追踪」可查看该预警的完整触发链路和数据来源",
        ],
    )
    df_alerts = get_alerts()

    col1, col2 = st.columns(2)
    with col1:
        status_filter = st.multiselect(
            "状态", ["pending", "confirmed", "dismissed"], default=["pending"]
        )
    with col2:
        severity_filter = st.multiselect(
            "严重度", ["high", "medium", "low"], default=["high", "medium", "low"]
        )

    if status_filter:
        df_alerts = df_alerts[df_alerts["status"].isin(status_filter)] if df_alerts is not None and not df_alerts.empty else df_alerts
    if severity_filter:
        df_alerts = df_alerts[df_alerts["severity"].isin(severity_filter)] if df_alerts is not None and not df_alerts.empty else df_alerts

    st.dataframe(
        df_alerts.rename(
            columns={
                "rule_name": "规则",
                "triggered_at": "触发时间",
                "object_type": "对象类型",
                "object_value": "对象",
                "severity": "严重度",
                "triggered_value": "触发值",
                "description": "描述",
                "status": "状态",
            }
        ),
        width='stretch',
        hide_index=True,
    )
    st.caption(f"共 {len(df_alerts)} 条预警")

    st.divider()
    st.subheader("✅ 预警复核")
    pending_df = df_alerts[df_alerts["status"] == "pending"] if df_alerts is not None and not df_alerts.empty else df_alerts
    if pending_df is None or pending_df.empty:
        st.info("当前没有待复核预警。")
    else:
        selected_alert = st.selectbox(
            "选择待复核预警",
            options=pending_df["alert_id"].tolist(),
            format_func=lambda aid: f"{aid} - {pending_df.loc[pending_df['alert_id'] == aid, 'rule_name'].values[0]} ({pending_df.loc[pending_df['alert_id'] == aid, 'object_value'].values[0]})",
        )
        with st.form(f"alert_review_form_{selected_alert}"):
            reviewer = st.text_input("复核人", key=f"alert_reviewer_{selected_alert}")
            notes = st.text_area("处理意见", key=f"alert_notes_{selected_alert}")
            col_confirm, col_dismiss = st.columns(2)
            confirm_submitted = col_confirm.form_submit_button("确认预警")
            dismiss_submitted = col_dismiss.form_submit_button("忽略预警")
            if confirm_submitted or dismiss_submitted:
                from whyfxpg.services.review_service import ReviewService

                svc = ReviewService()
                try:
                    if confirm_submitted:
                        svc.confirm_alert(selected_alert, reviewer, notes)
                        st.success("预警已确认")
                    else:
                        svc.dismiss_alert(selected_alert, reviewer, notes)
                        st.success("预警已忽略")
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))
                except Exception as e:  # noqa: BLE001 — 外部调用/配置解析兜底,刻意吞异常
                    st.error(f"处理失败：{e}")

    st.divider()
    st.subheader("🔍 预警血缘追踪")
    if df_alerts is None or df_alerts.empty:
        st.info("暂无预警记录")
        return
    selected_alert = st.selectbox(
        "选择预警查看血缘",
        options=df_alerts["alert_id"].tolist(),
        format_func=lambda aid: f"{aid} - {df_alerts.loc[df_alerts['alert_id'] == aid, 'rule_name'].values[0]} ({df_alerts.loc[df_alerts['alert_id'] == aid, 'object_value'].values[0]})",
    )
    if selected_alert:
        from whyfxpg.services.lineage_service import LineageService

        lineage = LineageService().get_lineage_by_alert(selected_alert)
        with st.expander("查看完整血缘链", expanded=True):
            st.json(lineage, expanded=False)
