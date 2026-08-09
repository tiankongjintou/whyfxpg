# WHYFXPG 开发文档清单

> 本清单面向接手 WHYFXPG 项目的开发工程师（人类或 AI Agent）。
> 所有文档按**开发者实际使用顺序**组织，从"理解项目是什么"到"上手改代码"。

---

## 必读（上手顺序）

### 1. CONTEXT.md（项目根目录）

项目级领域术语表。所有模块、类名、变量名、包名均复用此文档中的标准词汇。

```
whyfxpg/CONTEXT.md
```

**用途**：进入任何一个不熟悉的代码文件之前，先读这里。确保理解：
- 核心实体的英文代码名（如 Risk Event / Causal Factor / Industry Domain）
- 流水线各阶段的英文命名（Collection → Extraction → Evaluation → Alerting → Archiving）
- 维度与域的区别（Dimension vs Domain）
- 评分体系中各因子的含义

**关键术语速览**：

| 代码名 | 中文 | 所在层 |
|--------|------|--------|
| Risk Event | 风险事件 | 核心实体 |
| Causal Factor | 因果因子 | 评分维度 |
| Risk Score | 风险评分（0-100） | 评分输出 |
| Risk Level | 风险等级（S/M/L/A） | 评分输出 |
| Industry Domain | 行业域（机电/食品/化工...） | 配置层 |
| Domain Profile | 域配置（规则+权重+数据源+阈值） | 配置层 |
| Source Health | 源健康度 | 监控指标 |
| Pipeline Stage | 流水线阶段 | 运行层 |

---

### 2. development-report-v2.md（产品定义书）

产品的唯一权威需求来源。工程师在此文档中获取：
- 产品愿景与覆盖边界（第二章）
- 外部信号源体系与分类（第三章）
- 风险评估引擎的多维评分体系（第四章）
- 企业关联知识图谱结构与推理能力（第五章）
- 预警规则引擎的条件-动作模型（第六章）
- 闭环反馈机制（第七章）
- 核心数据库表结构（附录 A-D）

```
docs/development-report-v2.md
```

**如何读**：不是一次性通读，而是按需查阅：
- 接到新功能开发任务时 → 先在目录中找到对应章节，理解上下文再动手
- 新增数据源时 → 第三章信号源体系
- 新增评分逻辑时 → 第四章评分框架
- 新增图谱节点/边类型时 → 第五章图谱结构
- 新增预警规则类型时 → 第六章规则引擎

---

## 架构决策（按编号查阅）

### 3. ADR 目录（docs/adr/）

Architecture Decision Records — 记录**已完成的架构决策**，包含：决策背景、选项比较、最终选择理由。

工程师不应违背 ADR 中已确立的决策；如发现 ADR 不再适用，应先更新 ADR 再改代码。

| 编号 | 文件 | 核心决策结论 |
|------|------|-------------|
| 001 | `001-refactor-not-rewrite.md` | 重构而非重写，保持现有链路可运行 |
| 002 | `002-llm-port.md` | LLM 调用必须经过 `LLMPort` 接口，不直接调用 OpenAI/Anthropic |
| 003 | `003-report-renderer-port.md` | 报告渲染经过 `ReportRendererPort`，格式可替换 |
| 004 | `004-bigscreen-presenter.md` | 大屏展示数据模型与 Streamlit 渲染解耦 |
| 005 | `005-source-port.md` | 数据源接入经过 `SourcePort`，新增源不碰核心逻辑 |
| 006 | `006-causal-port.md` | 因果推理经过 `CausalPort`，引擎可独立替换 |
| 007 | `007-schema-migrations.md` | 数据库 schema 迁移规范，多域扩展后需维护迁移脚本 |
| 008 | `008-risk-scorer-runner.md` | 评分执行器标准化，评分逻辑与执行时机解耦 |
| 009 | `009-alert-publisher-port.md` | 预警发布经过 `AlertPublisherPort`，推送动作可替换 |
| 010 | `010-typed-config-models.md` | YAML 配置必须有 Pydantic/类型校验模型 |
| 011 | `011-webui-screens-split.md` | WebUI 页面拆分规范，避免单文件过大 |
| 012 | `012-review-service.md` | 人工复核服务标准化接口 |
| 013 | `013-admin-crud-port.md` | 管理后台 CRUD 统一 `CRUDServicePort` |
| 014 | `014-rule-engine-seam.md` | 规则引擎与执行引擎分离 |
| 015 | `015-source-monitor-seam.md` | 数据源健康监控与业务逻辑分离 |
| 016 | `016-dashboard-v2-seam.md` | 多域统一 Dashboard 接口 |
| 017 | `017-multi-domain.md` | 新增风险域（机电/食品/化工）的标准化扩展方式 |
| 018 | `018-pipeline-archive-feedback.md` | 流水线归档与反馈写入规范 |
| 019 | `019-close-seam-leaks.md` | 消除模块间 seam 泄漏（跨层 import 修复） |
| 020 | `020-end-to-end-integration-seam.md` | 端到端集成测试规范 |
| 021 | `021-webui-screen-import-boundary.md` | WebUI 页面间 import 依赖规范 |
| 022 | `022-basic-telemetry-observability.md` | 流水线各阶段指标采集规范 |
| 023 | `023-multi-industry-domain-templates.md` | 多行业域模板的扩展规范 |

**读取方式**：按需查阅，不需要通读。若要修改某模块，先找到对应的 ADR 了解上下文。

---

## 开发指南与运行手册

### 4. v2-development-guide.md

```
docs/v2-development-guide.md
```

包结构约定与 Port/Adapter 架构规范。
**注意**：部分内容已反映在实际代码中，建议以代码为准，文档仅作参考框架。

---

### 5. docs/agents/（Agent 协作用）

供 AI Coding Agent 使用的项目级上下文文件。

| 文件 | 用途 |
|------|------|
| `agents/domain.md` | Agent 的领域知识入口，指向 CONTEXT.md |
| `agents/issue-tracker.md` | 已知问题与状态，防止 Agent 重复引入已知缺陷 |
| `agents/ticket-template.md` | 标准任务工单格式 |

---

## 文档与代码的对应关系

```
CONTEXT.md
    └── 术语层：所有代码中的类名/变量名来自这里

development-report-v2.md
    └── 需求层：做什么（功能），做到什么程度（量化指标）

ADR 001-023
    └── 架构层：怎么做（接口设计），为什么这样选（决策理由）

v2-development-guide.md + agents/
    └── 协作层：代码组织约定，Agent 上下文约定
```

---

## 文档维护规则

1. **CONTEXT.md 是单一词汇源头**：代码中引入新术语时必须先更新此文档；已在文档中的术语不得用同义其他词替代。
2. **development-report-v2.md 是唯一需求来源**：产品功能变更必须先更新此文档，再改代码；不允许代码先行文档后补（ADR 的技术决策除外）。
3. **ADR 不可逆**：ADR 一旦确立，除非经过正式讨论更新，不得直接在代码中绕过。
4. **文档不解释实现细节**：development-report-v2.md 和 CONTEXT.md 不描述具体技术选型（Python 版本、数据库类型等），这些属于 ADR 或代码实现层。
