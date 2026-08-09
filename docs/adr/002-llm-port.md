# ADR-002：引入 LLMPort 与 LLMService 拆分

## 状态

已接受（Accepted），2026-07-29。

## 背景

`whyfxpg/core/llm_client.py` 同时承担以下职责：

1.  provider 配置读取（Kimi / MiniMax / Volcano 的 API key、base URL、默认模型）。
2.  HTTP 客户端与 OpenAI 兼容协议转换（包括 temperature 限制、model 默认值等）。
3.  提示词模板（实体抽取、文本分类、摘要、风险解释、执行摘要）。
4.  响应解析（JSON 提取、兜底字符串）。
5.  全局单例 `get_llm_client()`。

这导致 `ExtractEngine`、`RiskModel`、`ReportGenerator` 直接依赖 `LLMClient` 和全局单例，无法在单元测试中用 fake 替换，也无法在不修改代码的情况下切换 provider。

## 决策

采用**端口 + 适配器 + 服务**三层拆分：

| 层 | 文件 | 职责 |
|---|---|---|
| Port | `whyfxpg/ports/llm_port.py` | `LLMPort` 抽象接口：`chat_completion(messages, model, temperature, max_tokens, **kwargs) -> str`。 |
| Adapter | `whyfxpg/adapters/llm/openai_compat_adapter.py` | 复用既有 `LLMClient` 的 provider 配置与协议转换，实现 `LLMPort`。 |
| Adapter | `whyfxpg/adapters/llm/in_memory_adapter.py` | 测试/离线 fake，按 prompt 关键字返回 stub。 |
| Service | `whyfxpg/services/llm_service.py` | `LLMService`：持有默认 prompt 模板，提供语义化方法（`extract_entities`、`classify_text`、`summarize`、`risk_reasoning`、`executive_summary`）并负责响应解析与兜底。 |

### 关键原则

- **Port 最小化**：port 只暴露原始 `chat_completion`，不暴露业务语义，让不同 provider 可无缝接入。
- **Prompt 与解析在 Service**：业务 prompt 和 JSON 抽取归 `LLMService`，避免每个 adapter 复制一份模板。
- **Provider 差异在 Adapter**：Kimi 的 `temperature` 限制、各 provider 默认模型、base URL 等封装在 `OpenAICompatAdapter`（或后续更细粒度的 provider adapter）中。
- **向后兼容**：保留 `get_llm_client()` 全局单例作为 deprecated 垫片；`OpenAICompatAdapter` 默认内部使用它，现有测试的 monkeypatch 继续生效。
- **离线降级**：`LLM_ENABLED=false` 时 `LLMService` 自动使用 `InMemoryLLMAdapter`，避免测试或无密钥环境触发真实网络请求。

## 影响

### 新文件

- `whyfxpg/ports/__init__.py`
- `whyfxpg/ports/llm_port.py`
- `whyfxpg/adapters/__init__.py`
- `whyfxpg/adapters/llm/__init__.py`
- `whyfxpg/adapters/llm/openai_compat_adapter.py`
- `whyfxpg/adapters/llm/in_memory_adapter.py`
- `whyfxpg/services/__init__.py`
- `whyfxpg/services/llm_service.py`
- `whyfxpg/tests/test_llm_port.py`
- `whyfxpg/tests/test_llm_service.py`

### 修改文件

- `whyfxpg/core/extract_engine.py`：构造函数新增 `llm_service: Optional[LLMService] = None`；`_llm_extract` 改为调用 `self.llm_service.extract_entities()`。
- `whyfxpg/core/risk_model.py`：构造函数新增 `llm_service`；`llm_risk_reasoning()` 改为调用 `self.llm_service.risk_reasoning()`。
- `whyfxpg/core/report_generator.py`：构造函数新增 `llm_service`；`generate_executive_summary()` 改为调用 `self.llm_service.executive_summary()`；提示词从该函数迁移到 `LLMService`。
- `whyfxpg/tests/conftest.py`：`DummyLLMClient` 新增 `chat_completion(...)` 方法，以兼容新的 port 调用路径。

### 不变

- `whyfxpg/core/llm_client.py`：保留旧实现与 `get_llm_client()`，避免破坏尚未迁移的调用方（如 `multimodal.py`）。
- `multimodal.py` 暂不纳入 T2 范围；后续多模态重构统一处理。

## 测试

- `pytest whyfxpg/tests` 全量通过：52 个用例（含 19 个新增 LLM seam 用例）。
- `LLMService` 各方法均通过 `InMemoryLLMAdapter` 在离线环境下测试。
- `OpenAICompatAdapter` 通过注入 fake `LLMClient` 测试，避免真实 API 调用。

## 后续可选

- 将 `OpenAICompatAdapter` 进一步拆分为 `KimiLLMAdapter` / `MiniMaxLLMAdapter` / `VolcanoLLMAdapter`，如果未来 provider 差异继续扩大。
- 将 `LLMClient` 的 provider 配置逻辑逐步迁移到 adapter，最终 deprecate 全局单例。
- 为 `AlertEngine` 预留的文本分类能力提供 `LLMService.classify_text()` 注入 seam。
