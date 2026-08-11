"""
报告生成模块 (M6)

功能：
- 读取数据库中风险事件、汇总、预警等数据
- 生成 Word 综合报告和 Excel 明细表

本模块现在作为 orchestrator：数据组装由 ``ReportBuilder`` 负责，
文件渲染由 ``ReportRenderer`` 端口负责（Word/Excel/InMemory 适配器）。
"""

from datetime import datetime
from pathlib import Path
from typing import Any

from whyfxpg.adapters.reports import ExcelReportRenderer, WordReportRenderer
from whyfxpg.ports.report_renderer import ReportRenderer
from whyfxpg.services.llm_service import LLMService
from whyfxpg.services.report_builder import ReportBuilder
from whyfxpg.services.report_model import ReportModel


class ReportGenerator:

    def __init__(
        self,
        db_path: str | None = None,
        output_dir: str | None = None,
        llm_service: LLMService | None = None,
        builder: ReportBuilder | None = None,
        word_renderer: ReportRenderer | None = None,
        excel_renderer: ReportRenderer | None = None,
    ):
        self.db_path = db_path
        if output_dir is None:
            self.output_dir = Path(__file__).resolve().parent.parent / "reports"
        else:
            self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self._builder = builder
        self._word_renderer = word_renderer
        self._excel_renderer = excel_renderer
        self._llm_service = llm_service

    @property
    def llm_service(self) -> LLMService:
        if self._llm_service is None:
            self._llm_service = LLMService()
        return self._llm_service

    @property
    def builder(self) -> ReportBuilder:
        if self._builder is None:
            self._builder = ReportBuilder(
                db_path=self.db_path,
                llm_service=self._llm_service,
            )
        return self._builder

    @property
    def word_renderer(self) -> ReportRenderer:
        if self._word_renderer is None:
            self._word_renderer = WordReportRenderer()
        return self._word_renderer

    @property
    def excel_renderer(self) -> ReportRenderer:
        if self._excel_renderer is None:
            self._excel_renderer = ExcelReportRenderer(db_path=self.db_path)
        return self._excel_renderer

    def generate_executive_summary(self, data: dict[str, Any]) -> str:
        """
        使用 LLM 生成报告执行摘要。
        综合风险事件统计、等级分布、高风险预警，生成 200 字以内的
        自然语言摘要，替代静态模板文字。
        """
        try:
            return self.llm_service.executive_summary(data)
        except Exception as e:  # noqa: BLE001 — 外部调用/配置解析兜底,刻意吞异常
            return f"（执行摘要生成失败：{e}）"

    def fetch_data(self) -> dict[str, Any]:
        """从数据库获取报告数据（返回旧版 dict，兼容已有调用）。"""
        model = self.builder.build()
        return {
            "total_events": model.total_events,
            "level_counts": model.level_counts,
            "top_events": model.top_events,
            "top_products": model.top_products,
            "top_countries": model.top_countries,
            "pending_alerts": model.pending_alerts,
        }

    def _default_word_filename(self) -> str:
        return f"进口机电产品风险评估报告_{datetime.now().strftime('%Y%m%d%H%M%S')}.docx"  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计

    def _default_excel_filename(self) -> str:
        return f"进口机电产品风险明细_{datetime.now().strftime('%Y%m%d%H%M%S')}.xlsx"  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计

    def generate_word(self, filename: str | None = None) -> Path:
        """生成 Word 综合报告。"""
        if filename is None:
            filename = self._default_word_filename()
        model = self.builder.build()
        output_path = self.output_dir / "word" / filename
        return self.word_renderer.render(model, output_path)

    def generate_excel(self, filename: str | None = None) -> Path:
        """生成 Excel 明细表。"""
        if filename is None:
            filename = self._default_excel_filename()
        # Excel 渲染目前不关心 summary，所以直接构建空模型即可。
        model = ReportModel()
        output_path = self.output_dir / "excel" / filename
        return self.excel_renderer.render(model, output_path)

    def run(self) -> dict[str, Any]:
        """模块主入口"""
        try:
            word_path = self.generate_word()
            excel_path = self.generate_excel()
            return {
                "module": "report_generator",
                "status": "success",
                "records_processed": 0,
                "records_created": 2,
                "errors": [],
                "message": f"生成报告：{word_path}, {excel_path}",
                "word_path": str(word_path),
                "excel_path": str(excel_path),
            }
        except Exception as e:  # noqa: BLE001 — 外部调用/配置解析兜底,刻意吞异常
            return {
                "module": "report_generator",
                "status": "error",
                "records_processed": 0,
                "records_created": 0,
                "errors": [str(e)],
                "message": f"报告生成失败: {e!s}",
            }


if __name__ == "__main__":
    from whyfxpg.core.db import init_db

    init_db()
    gen = ReportGenerator()
    print(gen.run())
