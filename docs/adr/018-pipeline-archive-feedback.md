# ADR-018: Pipeline & Archive seam + 反馈闭环

## 背景

Phase 6 的 T20 要求把“信息从采集到归档”的全链路显式化，并在人工复核后把经验自动反馈回模型。此前 WHYfxpg 的各模块（fetcher、extract_engine、risk_evaluation_runner、alert_engine、report_generator）由 `main.py` 顺序调用，没有统一的运行记录、制品归档和血缘追溯。

## 决策

1. **信息管道领域模型**（`whyfxpg/core/information_pipeline.py`）
   - 定义 9 个阶段：collection / filtering / extraction / structuring / distillation / evaluation / alerting / reporting / archive。
   - 每个阶段包含输入/输出制品类型、是否必需、最大重试次数。
   - 使用标准库 dataclasses，不依赖 Streamlit 或数据库。

2. **ArchivePort + 双适配器**（`whyfxpg/ports/archive.py`，`adapters/archive/`）
   - `ArchiveHandle` 作为制品引用句柄。
   - `FileSystemArchiveAdapter` 把制品按 `archive/<run_id>/<type>/<name>.json` 落盘，便于人工审计。
   - `InMemoryArchiveAdapter` 用于测试和轻量运行。

3. **PipelineOrchestrator**（`whyfxpg/services/pipeline_orchestrator.py`）
   - 接收阶段运行器映射 `Dict[str, StageRunner]`，按顺序执行。
   - 每个阶段记录 `pipeline_stage_runs`，支持重试。
   - 运行结束时写入 `pipeline_runs` 和审计日志，并归档运行清单（manifest）。
   - 默认阶段运行器 `build_default_stage_runners()` 复用现有 Fetcher / ExtractEngine / RiskEvaluationRunner / AlertEngine / ReportGenerator，不破坏既有 main.py。

4. **LineageService**（`whyfxpg/services/lineage_service.py`）
   - 支持按 `event_id`、`alert_id`、`review_id` 查询完整血缘链：
     `source -> crawl_log -> raw_page -> event -> score -> alerts -> reviews -> causal_paths`。
   - 替换掉 `DbSourceHealthAdapter` 中原本单薄的 `lineage()`，并保留 `webui/read_model.py` 的兼容入口。

5. **FeedbackLearningService 关闭反馈环**（`whyfxpg/services/feedback_learning_service.py`）
   - 调用现有 `FeedbackLearner.learn()` 计算 country/product/manufacturer 调整。
   - 通过 `ConfigurationAdminService` 把新配置写回 `risk_model.yaml` 并发布版本。
   - 写 `audit_log` 记录调整前后快照。
   - 根据调整维度把相关 `risk_events` 的评分重置为 NULL，触发 `RiskEvaluationRunner.run()` 重新评分。
   - `ReviewService.submit_review()` 增加可选的 `feedback_service` 钩子，复核成功后自动触发学习。

6. **数据库迁移**（`whyfxpg/migrations/007_pipeline_audit.sql`）
   - 新增 `pipeline_runs`、`pipeline_stage_runs`、`audit_log` 三张表及索引。
   - 注意：既有 T20  ticket 草稿写为 `006_pipeline_audit.sql`，但 `006_source_monitoring.sql` 已存在，因此实际使用 `007_pipeline_audit.sql`。

## 验收结果

- `pytest whyfxpg/tests/test_pipeline_archive_seam.py`：12 passed。
- 全量回归测试 `pytest whyfxpg/tests`：222 passed, 1 skipped。
- 风险事件列表页、预警中心页新增“血缘追踪”下拉选择 + JSON 展开面板。
- `ReviewService` 在注入 `FeedbackLearningService` 后可自动触发模型更新与重评分。

## 影响

- 新增代码文件 10 个，约 1.3k 行（含测试）。
- 未删除旧 `main.py` 入口；新增 orchestrator 作为可选上层封装。
- `ConfigurationAdminService` 修复了一处初始化未提交导致 `config_objects` 表缺失的隐患（`conn.commit()`）。

## 后续

- T21 拆分 `core/stores.py` 时，可把 `PipelineRunStore` / `AuditLogStore` 移入独立模块。
- T22 的端到端测试可围绕 `PipelineOrchestrator` 与默认阶段运行器编排一次完整运行。
