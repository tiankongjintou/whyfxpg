"""报告中心页面。"""

import streamlit as st

from whyfxpg.services.report_service import ReportService


def render() -> None:
    st.title("📄 报告中心")
    from whyfxpg.webui.screens._page_guide import page_guide
    page_guide(
        "📄 报告中心",
        "查看历史报告文件列表，并可按需生成最新的风险评估汇总报告（Word/Excel）。",
        [
            "左侧为 Word 版报告，右侧为 Excel 版报告；首次使用需先生成报告后方有内容",
            "点击「📄 生成新报告」将根据当前数据生成包含事件统计、风险分布等内容的完整报告",
            "报告生成需要一定时间（数秒至数十秒），请耐心等待直至出现成功提示",
        ],
    )
    st.info("报告由报告服务生成，保存在 reports/ 目录下。")

    service = ReportService()
    reports = service.list_report_files()

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("📝 Word 报告")
        if reports["word"]:
            for name in reports["word"]:
                st.write(f"• {name}")
        else:
            st.info("暂无 Word 报告")
    with col2:
        st.subheader("📊 Excel 报告")
        if reports["excel"]:
            for name in reports["excel"]:
                st.write(f"• {name}")
        else:
            st.info("暂无 Excel 报告")

    st.divider()
    if st.button("📄 生成新报告"):
        with st.spinner("正在生成报告..."):
            try:
                result = service.generate_report()
                st.success(f"报告生成完成：{result.get('message', '')}")
                st.rerun()
            except Exception as e:  # noqa: BLE001 — 外部调用/配置解析兜底,刻意吞异常
                st.error(f"报告生成失败：{e}")
