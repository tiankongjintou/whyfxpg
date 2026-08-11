"""人工复核页面。"""

import pandas as pd
import streamlit as st

from whyfxpg.services.review_service import ReviewService, ReviewSubmission
from whyfxpg.webui.queries import get_events


def render() -> None:
    st.title("✅ 人工复核界面")
    from whyfxpg.webui.screens._page_guide import page_guide
    page_guide(
        "✅ 人工复核",
        "对系统自动评分的风险事件进行人工审核与修正，修正数据将反馈给模型持续优化。",
        [
            "先从上方「选择事件」下拉框找到需要复核的具体事件",
            "填写「修正原因」（必填）是复核的必要步骤，请详细说明修正依据",
            "复核提交后可在下方「复核历史」查看所有已完成的修正记录",
            "复核结果会自动进入反馈学习流程，无需额外操作",
        ],
    )
    st.caption("对风险事件进行人工审核，修正评分。修正数据将用于反馈学习，持续优化模型精度。")

    service = ReviewService()
    df = get_events(limit=200)

    selected_id = st.selectbox(
        "选择事件",
        df["event_id"].tolist(),
        format_func=lambda x: (
            f"{df[df['event_id'] == x]['product_name'].values[0] if len(df[df['event_id'] == x]) > 0 else x} "
            f"({df[df['event_id'] == x]['rs_level'].values[0] if len(df[df['event_id'] == x]) > 0 else '?'})"
        ),
    )

    if selected_id:
        event = df[df["event_id"] == selected_id].iloc[0]

        st.divider()
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"**产品名称：** {event['product_name'] or '未知'}")
            st.markdown(f"**品牌：** {event['brand'] or '未知'}")
            st.markdown(f"**型号：** {event['model'] or '未知'}")
            st.markdown(f"**原产国：** {event['country'] or '未知'}")
            st.markdown(f"**制造商：** {event['manufacturer'] or '未知'}")
        with col2:
            st.markdown(f"**危害类型：** {event['hazard_type']}")
            st.markdown(f"**严重度等级：** {event['severity_level']}")
            st.markdown(f"**当前风险等级：** `{event['rs_level']}`")
            st.markdown(f"**当前风险分：** {event['total_score']:.2f}")
            if event['causal_factor']:
                st.markdown(f"**因果因子：** {event['causal_factor']:.3f}")
            else:
                st.markdown("**因果因子：** N/A")

        st.divider()
        st.subheader("📝 评分修正")

        with st.form(f"review_form_{selected_id}"):
            level_options = ["S", "M", "L", "A"]
            current_index = (
                level_options.index(event["rs_level"])
                if event["rs_level"] in level_options
                else 0
            )
            new_rs = st.selectbox("风险等级", level_options, index=current_index)
            default_ss = ReviewService.default_adjusted_ss_score(event["severity_level"])
            new_ss = st.slider(
                "严重度评分 (SS)",
                0,
                100,
                int(default_ss),
            )
            reason = st.text_area("修正原因（必填）", placeholder="请说明为何进行此次修正...")
            reviewer = st.text_input("复核人", placeholder="输入姓名")

            submitted = st.form_submit_button("💾 提交复核意见", width='stretch')

            if submitted:
                try:
                    service.submit_review(
                        ReviewSubmission(
                            event_id=selected_id,
                            reviewer=reviewer,
                            reason=reason,
                            adjusted_rs_level=new_rs,
                            adjusted_ss_score=new_ss,
                        )
                    )
                    st.success("✅ 复核意见已提交！")
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))
                except Exception as e:  # noqa: BLE001 — 外部调用/配置解析兜底,刻意吞异常
                    st.error(f"复核提交失败：{e}")

    st.divider()
    st.subheader("📜 复核历史")
    history = service.get_history(limit=50)
    if history:
        df_history = pd.DataFrame(
            [
                {
                    "复核时间": r.reviewed_at,
                    "复核人": r.reviewer,
                    "原等级": r.original_rs,
                    "新等级": r.adjusted_rs,
                    "原SS": r.original_ss,
                    "新SS": r.adjusted_ss,
                    "原因": r.reason,
                    "产品": r.product_name,
                    "国别": r.country,
                }
                for r in history
            ]
        )
        st.dataframe(df_history, width='stretch', hide_index=True)
    else:
        st.info("暂无复核记录。")
