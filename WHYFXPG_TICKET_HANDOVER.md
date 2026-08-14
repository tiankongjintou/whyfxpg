# WHYFXPG Ticket Handover

> 给 Codex / Claude Code / OpenCode 等外部编程 agent 使用。
> 人类在此文件中填入当前进度，agent 读取后直接开始工作。

---

## 项目根目录

```
D:\Seafile\SeaHome\TempProjects\WHYfxpg
```

---

## 必读文件（按顺序阅读）

1. **AGENTS.md** — 项目级开发约束，必须遵守
2. **CLAUDE.md** — 代码规范
3. **.scratch/wayfinder/DEV-GUIDE.md** — 开发流程和质量门禁
4. **docs/技术改造路线图.md** — 源文档，Ticket 的"What to build"均来自此文档

---

## 质量门禁（commit 前必须全部通过）

一键运行所有检查：
```bash
python scripts/quality_gate.py
```

如需跳过测试（仅检查 linter + type checker）：
```bash
python scripts/quality_gate.py --skip-tests
```

如需单独运行各项检查：
```bash
pytest tests/ -v
ruff check whyfxpg/ whyfxpg_api/
mypy whyfxpg/ whyfxpg_api/
```

---

## 文档同步规则（如果你的 ticket 涉及这些变更，必须同步更新）

| 变更类型 | 必须更新的文档 |
|---------|--------------|
| 数据库 schema 变更 | `docs/03-数据库设计说明书.md` |
| API 端点变更 | `docs/04-API接口说明书.md` |
| 核心算法变更 | `docs/05-核心算法说明书.md` |
| 新增数据源适配器 | `docs/全球数据源调研矩阵.md` |
| 部署变更 | `docs/06-开发环境与运行指南.md` |

---

## 阻塞升级规则

遇到以下情况，必须停下来发飞书消息给用户，不能自行决定：

- 工作量超过 2 人天
- Ticket 描述与实际代码/需求不一致
- 需要修改其他 ticket 的范围或 blocking edges
- 技术选型与 `docs/技术改造路线图.md` 不符
- 数据库崩溃、P0 安全漏洞、方向性问题

---

## 当前进度

> ⚠️ 由人类在分配任务前填写，agent 不修改此 section

### Phase 0 状态
- [ ] P0-1 风险等级阈值修复 ✅ 已完成
- [ ] P0-2 extracted_language 字段 ✅ 已完成
- [ ] P0-3 whyfxpg 包发布 ⚠️ 待用户手动操作（git push + GitHub Release）
- [ ] P0-4 RiskScorer assess() 接口 ✅ 已完成
- [ ] P0-5 API 文档 ✅ 已完成
- [ ] P0-6 数据源调研矩阵 ✅ 已完成

### Phase 1 状态（API 平台）
- [x] P01 SQLite → PostgreSQL 多租户迁移 ✅ 已完成（2026-08-11 reasonix-agent）
- [x] P02 FastAPI 项目骨架 + 认证中间件 ✅ 已完成（2026-08-11 reasonix-agent）
- [x] P03 核心 REST API 端点 ✅ 已完成（2026-08-11 reasonix-agent）
- [x] P04 计量计费 + 额度限流 ✅ 已完成（2026-08-11 reasonix-agent）
- [x] P05 Webhook 订阅系统 ✅ 已完成（2026-08-11 reasonix-agent）
- [x] P06 Docker 一键部署 ✅ 已完成（2026-08-11 reasonix-agent）
- [x] P07 Pydantic 配置 Schema 校验 ✅ 已完成（2026-08-11 reasonix-agent）
- [x] TD01 评分乘法溢出修复 ✅ 已完成（2026-08-11 reasonix-agent）
- [x] TD02 数据库索引补全 ✅ 已完成（2026-08-11 reasonix-agent）

### Phase 2 状态（数据源扩充）
- [ ] P08 数据源扩充：第一优先级 × 4 ✅ 已完成（2026-08-14）
- [ ] P09 数据源扩充：第二优先级 × 4 ⬜ 未开始
- [ ] P10 多语言处理架构 ⬜ 未开始
- [ ] P11 数据源扩充：第三优先级 × 4 ⬜ 未开始
- [ ] P12 跨数据源消重与关联 ⬜ 未开始

---

## 下一个可领取的 Ticket

> ⚠️ 由人类在分配任务前填写

**Frontier Tickets（无阻塞，可立即领取）：**

1. **P09** — `.scratch/wayfinder/issues/phase2-data-sources/P09-source-adapters-priority2.md`（P08 已完成，可领取）
2. **P10** — `.scratch/wayfinder/issues/phase2-data-sources/P10-multilingual-pipeline.md`（可与 P09 并行）

**Blocked Tickets（依赖未完成，不能领取）：**
- P02, P03, P04 → 等待 P01 完成
- P05 → 等待 P03 完成
- P06 → 等待 P05 完成
- P08 → 等待 P03 完成
- P09 → 等待 P08 完成
- P10 → 等待 P09 完成
- P11, P12 → 等待 P10 完成

---

## Agent 执行指令模板

当分配任务时，将以下内容复制给 agent：

```
请在 D:\Seafile\SeaHome\TempProjects\WHYfxpg 目录下完成以下 Ticket：

文件路径：<TICKET_FILE_PATH>

工作步骤：
1. 阅读 .scratch/wayfinder/DEV-GUIDE.md
2. 阅读上述 Ticket 文件
3. 阅读项目根目录的 AGENTS.md 和 CLAUDE.md
4. 阅读 Ticket 中引用的源码文件
5. 实现 Ticket 中定义的所有 acceptance criteria
6. 运行质量门禁：
   pytest tests/ -v
   ruff check whyfxpg/ whyfxpg_api/
   mypy whyfxpg/ whyfxpg_api/
7. 如有 schema 或 API 变更，同步更新对应文档
8. Git commit，格式：[P01-xxx] 或 [TD-xx]
```

---

## Ticket 文件索引

### Phase 1 — API 平台
| 文件名 | 路径 |
|--------|------|
| P01 | `.scratch/wayfinder/issues/phase1-api-platform/P01-sqlite-to-postgresql.md` |
| P02 | `.scratch/wayfinder/issues/phase1-api-platform/P02-fastapi-skeleton-auth.md` |
| P03 | `.scratch/wayfinder/issues/phase1-api-platform/P03-core-rest-api.md` |
| P04 | `.scratch/wayfinder/issues/phase1-api-platform/P04-metering-rate-limit.md` |
| P05 | `.scratch/wayfinder/issues/phase1-api-platform/P05-webhook-system.md` |
| P06 | `.scratch/wayfinder/issues/phase1-api-platform/P06-docker-deploy.md` |
| P07 | `.scratch/wayfinder/issues/phase1-api-platform/P07-pydantic-config.md` |
| TD01 | `.scratch/wayfinder/issues/phase1-api-platform/TD01-score-overflow-fix.md` |
| TD02 | `.scratch/wayfinder/issues/phase1-api-platform/TD02-database-indexes.md` |

### Phase 2 — 数据源扩充
| 文件名 | 路径 |
|--------|------|
| P08 | `.scratch/wayfinder/issues/phase2-data-sources/P08-source-adapters-priority1.md` |
| P09 | `.scratch/wayfinder/issues/phase2-data-sources/P09-source-adapters-priority2.md` |
| P10 | `.scratch/wayfinder/issues/phase2-data-sources/P10-multilingual-pipeline.md` |
| P11 | `.scratch/wayfinder/issues/phase2-data-sources/P11-source-adapters-priority3.md` |
| P12 | `.scratch/wayfinder/issues/phase2-data-sources/P12-cross-source-dedup.md` |
