# ADR-005：Fetcher 拆分 SourcePort（HTTP/内存适配器）与 PageStore

## 状态

已接受（Accepted），2026-07-29。

## 背景

`whyfxpg/core/fetcher.py` 的 `Fetcher` 类直接创建 `requests.Session`，并在 `fetch_source` / `run` 中混杂：

1. HTTP 请求与错误处理。
2. 内容哈希计算与重复检测。
3. `monitor_sources` 初始化与更新。
4. `raw_pages` 写入。
5. `crawl_logs` 写入。

这导致：

- **无法在没有网络/mock requests 的情况下测试核心采集流程**；测试必须 monkeypatch `session.get`。
- 异常处理、超时、重试逻辑与业务写入耦合，无法独立替换或升级（例如改为异步采集、RSS 适配器）。

## 决策

1. 引入 **`SourcePort` 抽象端口**（`whyfxpg/ports/source_port.py`），定义：
   - `FetchedPage` 值对象：原始字节、内容类型、内容哈希、状态、错误信息。
   - `SourcePort.fetch(source_id, cfg) -> FetchedPage`：只负责“把内容拿回来”。

2. 提供两种适配器：
   - `HttpSourceAdapter`（`whyfxpg/adapters/sources/http_source_adapter.py`）：基于 `requests.Session` 的真实网络实现。
   - `InMemorySourceAdapter`（`whyfxpg/adapters/sources/in_memory_source_adapter.py`）：测试/离线替身，支持预置 `FetchedPage` 或回调函数。

3. 把数据库写入拆分到 Store：
   - `MonitorSourceStore`：负责 `monitor_sources` 初始化、检查状态更新、`crawl_logs` 写入。
   - `RawPageStore`：负责 `raw_pages` 的重复检测与插入。

4. `Fetcher` 只保留 **orchestrator** 角色：
   - 读取配置。
   - 调用 `SourcePort.fetch`。
   - 使用 Store 写入结果。

5. 默认行为不变：
   - `Fetcher()` 仍然使用 `HttpSourceAdapter`，因此 `main.py` 的调用无需改动。
   - 测试通过 `Fetcher(config_dir, db_path, source_port=InMemorySourceAdapter(...))` 注入数据，不再 mock requests。

## 影响

- 测试不再依赖 `unittest.mock.MagicMock` 或 monkeypatch 网络层；采集流程与存储流程可分别测试。
- 新增异步、RSS、文件目录等来源时，只需实现 `SourcePort`。
- `Fetcher` 的接口签名扩展了一个可选参数 `source_port: Optional[SourcePort]`，兼容旧调用 `Fetcher(config_dir, db_path)`。

## 相关文件

- `whyfxpg/ports/source_port.py`
- `whyfxpg/adapters/sources/http_source_adapter.py`
- `whyfxpg/adapters/sources/in_memory_source_adapter.py`
- `whyfxpg/core/stores.py`（新增 `MonitorSourceStore`、`RawPageStore`）
- `whyfxpg/core/fetcher.py`（重构为 orchestrator）
- `whyfxpg/tests/test_fetcher.py`（替换为基于 SourcePort 的测试）
- `docs/wayfinder-phase2-5-map.md`
- `docs/architecture-refactor-plan.md`
