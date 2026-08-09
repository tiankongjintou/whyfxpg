# ADR-012: 抽出 ReviewService，把人工复核写入从 WebUI 分离

## 背景

Phase 4B 拆分后，`screens/review.py` 仍直接调用 `get_db_connection()`，手工完成以下操作：

1. 读取 `risk_events` 当前 ss/ps/rs；
2. 生成 UUID 并 `INSERT INTO manual_reviews`；
3. `UPDATE risk_events SET review_status = 'reviewed'`；
4. 手动 commit/close 连接。

这使得页面模块同时承担“UI 渲染”与“业务写入/事务管理”两种职责，导致：

- **测试困难**：需要 Mock Streamlit 才能验证复核逻辑；
- **事务边界暴露**：commit/close 散落在页面代码里；
- **复用受阻**：反馈学习器 `FeedbackLearner` 与 WebUI 共享同一套写入语义，但没有统一入口。

## 决策

新建领域服务 `whyfxpg.services.review_service.ReviewService`，页面只负责：

- 调用 `ReviewService.submit_review(...)`
- 将返回的 `ReviewRecord` / 历史列表渲染为 Streamlit 组件

ReviewService 负责：

- 输入校验（复核人、原因、风险等级合法性）
- 在单个 `UnitOfWork` 事务内完成读取 + 插入 + 更新
- 将数据库行映射为 `ReviewRecord` / `ReviewSubmission` dataclass

## 方案对比

| 方案 | 优点 | 缺点 |
|------|------|------|
| A. 保留 SQL 在页面里 | 改动最小 | 职责混合，测试难 |
| B. 只把 SQL 搬到 `ReviewService`，页面仍管理事务 | 写入集中 | 事务边界仍在页面 |
| **C. ReviewService 内部使用 UnitOfWork** | 事务内聚、测试方便、与现有 stores 一致 | 需要新建服务文件与测试 |

选择 **C**。

## 关键结构

```
whyfxpg/services/review_service.py
  ReviewSubmission  dataclass（页面提交）
  ReviewRecord      dataclass（返回记录）
  ReviewService
    - __init__(db_path=None)
    - submit_review(submission) -> ReviewRecord
    - get_history(limit=50) -> List[ReviewRecord]
    - default_adjusted_ss_score(severity_level) -> int

whyfxpg/webui/screens/review.py
  仅渲染表单/历史，不直接 import get_db_connection
```

## 影响

- `manual_reviews` 与 `risk_events.review_status` 的写入语义收敛到一处；
- 反馈学习器 `FeedbackLearner` 可以稳定读取由 `ReviewService` 统一写入的复核记录；
- 后续若要支持批量复核、复核撤销、复核审批流程，只需扩展 `ReviewService`。

## 风险与缓解

- **风险**：页面原有逻辑中存在 `severity_level == '高' and 90 or ...` 的默认值，抽取后可能改变默认值。
  - **缓解**：保留 `default_adjusted_ss_score()`，映射规则与原页面完全一致（高=90，中=60，其他=30）。
- **风险**：`UnitOfWork` 上下文管理器会把原连接模式改为 `row_factory=sqlite3.Row`。
  - **缓解**：服务内使用 `cursor.fetchone()` 读取列，行为与原代码一致。

## 状态

已实施：

- `whyfxpg/services/review_service.py`
- `whyfxpg/services/__init__.py` 导出 `ReviewService` / `ReviewSubmission` / `ReviewRecord`
- `whyfxpg/webui/screens/review.py` 改为调用服务
- `whyfxpg/tests/test_review_service.py` 覆盖提交、历史、校验、事件不存在等场景

## 相关

- ADR-011 WebUI 页面拆分
- `whyfxpg/core/feedback_learner.py`（读取 `manual_reviews`）
