# WHYFXPG 进口机电产品风险评价系统（v2）

## 项目简介

面向海关检验监管场景的进口机电产品风险评价闭环系统。系统通过采集外部公开数据源（召回通报、产品安全预警、标准信息等），进行信息抽取、风险评分、预警和报告生成，帮助海关业务人员识别进口机电产品的潜在风险。

**v2 目标**：把 WHYfxpg 从“海关进口机电产品专用风险看板”推进为 **可跨行业、可配置、可维护、可观测的通用质量风险评估平台**，同时保持单仓库、单进程、可独立开发。

## 核心特点

- **配置化**：信息源、关键词、抽取规则、风险模型、预警规则全部 YAML 配置化，并通过 `ConfigStorePort` 统一读写。
- **Seam-first 架构**：所有外部依赖（LLM、数据源、报告渲染、大屏、归档、规则执行等）都先定义 `Port`（接口），再提供 `Adapter`（生产实现 + 测试替身），业务逻辑不依赖具体实现。
- **模块化**：`core/` 承载数据/管道/引擎，`services/` 承载业务编排，`adapters/` 承载技术实现，`webui/` 仅做展示，便于拼接替换。
- **可审计**：所有评分、预警、报告、配置版本、流水线运行均关联血缘并可归档。
- **可解释**：风险分可追溯到具体规则、因果图节点和数据依据。
- **闭环**：支持人工复核、模型回测、反馈学习、知识库更新。

## 目录结构

```
WHYfxpg/
├── config/                  # 配置文件（YAML 主存储）
├── docs/                    # 文档与 ADR
│   ├── adr/                 # 架构决策记录
│   └── agents/              # Agent 协议与 ticket 模板
├── whyfxpg/                 # 主代码包
│   ├── adapters/            # Port 的技术适配器（生产 + InMemory 测试替身）
│   ├── core/                # 数据、管道、引擎、规则、评分等核心模块
│   ├── ports/               # 领域端口（接口契约）
│   ├── services/            # 业务服务与编排层（ReportBuilder、DashboardBuilderService 等）
│   ├── webui/               # Streamlit 看板与页面
│   ├── data/                # 数据库
│   ├── reports/             # 报告输出（默认）
│   ├── logs/                # 日志
│   └── tests/               # 测试
├── scripts/                 # 工具脚本
├── .env.example             # 环境变量示例
├── pyproject.toml           # 项目配置与 pytest
└── requirements.txt         # 依赖
```

## 快速开始

1. 安装依赖
```bash
pip install -r requirements.txt
```

2. 复制环境变量文件并填写 API 密钥
```bash
cp .env.example .env
```

3. 初始化数据库
```bash
python scripts/init_db.py
```

4. 运行配置版本管理
```bash
python -m whyfxpg.core.config_version
```

5. 运行采集模块（示例）
```bash
python -m whyfxpg.core.fetcher
```

6. 运行风险评分模块
```bash
python -m whyfxpg.core.risk_model
```

7. 运行看板
```bash
streamlit run whyfxpg/webui/app.py
```

## API 快速调用

3 行代码完成风险评估（无需启动数据库或 Web 服务）：

```python
from whyfxpg import RiskScorer
r = RiskScorer.assess(
    event={'severity_level': '严重', 'country': '美国', 'product_category': '家用厨房电器'},
    historical_counts={'country_history_count': 3, 'product_history_count': 1}
)
print(r.rs_level, r.total_score)
```

## 测试与架构守护

运行全部测试（不需要真实网络/LLM/数据库，依赖通过 InMemory 适配器与临时 SQLite 替代）：

```bash
python scripts/run_tests.py
```

运行架构健康检查，确保关键 seam 没有被重新泄漏：

```bash
python scripts/check_architecture.py
```

## v2 架构：Port + Adapter

```
┌─────────────────────────────────────────────┐
│  webui/          UI 层，只调用 services/       │
├─────────────────────────────────────────────┤
│  services/       业务编排（ReportBuilder、    │
│                  DashboardBuilderService、   │
│                  FeedbackLearningService 等）│
├─────────────────────────────────────────────┤
│  core/           数据/管道/引擎/评分/规则      │
├─────────────────────────────────────────────┤
│  ports/          接口契约（LLMPort、         │
│                  SourcePort、ReportRenderer、  │
│                  ArchivePort、CausalPort 等）│
├─────────────────────────────────────────────┤
│  adapters/       技术实现 + InMemory 测试替身 │
└─────────────────────────────────────────────┘
```

每个新 Port 落地时**必须同时提供**：
1. 生产适配器（如 `openai_compat_adapter.py`）。
2. InMemory 测试替身（如 `in_memory_llm_adapter.py`）。
3. 覆盖 Port 和至少一个业务使用路径的测试。

## 端到端流水线

```
外部数据源 → SourcePort → 采集 → raw_pages
raw_pages → 信息抽取 → risk_events
risk_events → 风险评分 → 汇总表
risk_events/汇总 → 预警规则 → alert_records
事件/预警 → 报告生成 → Word/Excel
风险数据 → DashboardBuilderService → 大屏/钻取/导出
反馈 → FeedbackLearningService → 更新风险模型/因果图 → 重新评分
```

`whyfxpg/tests/test_v2_integration.py` 提供了一个完整的端到端测试：从 InMemory 数据源到报告渲染、再到 Dashboard 导出，全部使用临时资源。

## 模块说明

| 模块 | 入口 | 输入 | 输出 |
|---|---|---|---|
| 配置管理 | `whyfxpg.core.config_version` | `config/*.yaml` | `config_versions`（数据库） |
| 数据采集 | `whyfxpg.core.fetcher` | `monitor_sources` + `SourcePort` | `raw_pages`, `crawl_logs` |
| 信息抽取 | `whyfxpg.core.extract_engine` | `raw_pages` | `risk_events` |
| 风险评分 | `whyfxpg.core.risk_evaluation_runner` | `risk_events` | `risk_events` + 各类汇总表 |
| 预警生成 | `whyfxpg.core.alert_engine` | `risk_events` + 规则 | `alert_records` |
| 报告生成 | `whyfxpg.core.report_generator` | `ReportBuilder` 组装的模型 | Word/Excel 文件 |
| 看板 | `whyfxpg.webui.app` | `DashboardBuilderService` | Web 界面 |
| 流水线编排 | `whyfxpg.services.pipeline_orchestrator` | `InformationPipeline` | 归档的运行产物 |
| 反馈学习 | `whyfxpg.services.feedback_learning_service` | 人工复核结果 | 更新 `risk_model.yaml` + 因果节点 |

## 数据源

- 国家市场监管总局缺陷产品管理中心（DPAC）
- 美国 CPSC 召回
- 欧盟 RAPEX/Safety Gate
- 英国 OPSS 产品召回
- 澳大利亚产品安全（预留）
- 全国标准信息公共服务平台
- IEC 官网

## 开发说明

- 所有配置在 `config/` 目录下，通过 YAML 管理，统一经 `ConfigStorePort` 读写。
- 业务代码只依赖 `ports/`，不直接依赖 `adapters/` 的具体实现。
- 新增模块时优先定义 `Port`，再写 `InMemory` 测试替身，最后写生产适配器。
- 修改后请运行 `scripts/run_tests.py` 和 `scripts/check_architecture.py`。
- 详细开发指南见 `docs/v2-development-guide.md`。

## 许可证

内部项目
