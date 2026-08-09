# ADR-003：拆分 ReportGenerator 为 ReportBuilder + ReportRenderer Port

## 状态

已接受（Accepted），2026-07-29。

## 背景

`ReportGenerator` 同时负责：

1. 从数据库读取报告所需数据（事件、汇总、国别、预警）。
2. 调用 LLM 生成执行摘要。
3. 使用 `python-docx` 排版 Word 综合报告。
4. 使用 `openpyxl` 导出 Excel 明细表。
5. 输出目录管理和文件路径生成。

这种宽度导致无法对“数据组装”和“文件渲染”分别做单元测试，也使得新增 PDF/HTML 等格式需要直接修改 `ReportGenerator`。

## 决策

拆分为三层：

| 层 | 文件 | 职责 |
|---|---|---|
| Model | `whyfxpg/services/report_model.py` | 纯数据对象 `ReportModel`，在 builder 与 renderer 之间传递。 |
| Builder | `whyfxpg/services/report_builder.py` | 读取数据库、调用 `LLMService.executive_summary()`、组装 `ReportModel`。 |
| Port | `whyfxpg/ports/report_renderer.py` | 抽象接口 `render(model, output_path) -> Path`。 |
| Adapter | `whyfxpg/adapters/reports/word_report_adapter.py` | 用 `python-docx` 生成 Word。 |
| Adapter | `whyfxpg/adapters/reports/excel_report_adapter.py` | 用 `openpyxl` 生成 Excel（按原样查询数据库多 sheet）。 |
| Adapter | `whyfxpg/adapters/reports/in_memory_report_adapter.py` | 测试 double，记录渲染调用而不写文件。 |
| Orchestrator | `whyfxpg/core/report_generator.py` | 兼容旧入口，组合 builder + 两个 renderer。 |

### 关键原则

- **Builder 与渲染分离**：数据组装不依赖任何文件格式库；渲染器只接收 `ReportModel`。
- **Port 最小化**：`ReportRenderer` 只负责“把模型写到路径”。
- **向后兼容**：保留 `ReportGenerator` 的公共方法（`generate_word`、`generate_excel`、`run`、`fetch_data`、`generate_executive_summary`），`main.py` 和 `webui/app.py` 无需修改。
- **可测试**：业务断言可通过 `InMemoryReportRenderer` 完成；文件写入仅通过小型 smoke test 验证。

## 影响

### 新增文件

- `whyfxpg/services/report_model.py`
- `whyfxpg/services/report_builder.py`
- `whyfxpg/ports/report_renderer.py`
- `whyfxpg/adapters/reports/__init__.py`
- `whyfxpg/adapters/reports/word_report_adapter.py`
- `whyfxpg/adapters/reports/excel_report_adapter.py`
- `whyfxpg/adapters/reports/in_memory_report_adapter.py`
- `whyfxpg/tests/test_report_seams.py`

### 修改文件

- `whyfxpg/core/report_generator.py`：改为 orchestrator，注入 `ReportBuilder` 与 `ReportRenderer`；默认仍使用 Word/Excel 真实适配器。

### 不变

- `main.py` 与 `webui/app.py` 对 `ReportGenerator` 的调用方式不变。
- 报告内容格式与旧版保持一致（标题、章节、表格、方法说明）。

## 测试

- 新增 8 条报告 seam 测试，覆盖 `ReportModel`、`ReportRenderer` 抽象、`InMemoryReportRenderer` 记录、`ReportBuilder` 空库行为、`ReportGenerator.run()` 通过内存 renderer 的完整路径，以及 Word/Excel 真实文件 smoke test。
- 全量 pytest 通过：60 passed。

## 后续可选

- 让 `ExcelReportRenderer` 不再直接查询数据库，而是完全基于 `ReportModel` 中的 sheet 数据（需扩展 ReportModel）。
- 新增 `PDFReportRenderer` 或 `HTMLReportRenderer` 只需实现 `ReportRenderer` 端口。
- 将 `ReportBuilder` 的数据库读取改为通过 `UnitOfWork`/`stores` 复用连接（依赖后续 Store 层深化）。
