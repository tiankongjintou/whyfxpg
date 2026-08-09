# WHYFXPG 项目开发规范

> 本文件为所有 AI 智能体提供项目级上下文，加载到每个 session 的 system prompt 中。

## 项目概述

WHYFXPG（海关进口机电产品风险评价闭环系统）是一个面向进出口合规领域的风险情报平台。
核心价值：用境外公开召回数据（CPSC/RAPEX/OPSS 等）为进出口企业提供风险评估和预警服务。

## 核心约束

- **不接入海关内部系统**：仅采集外部公开数据
- **可配置**：所有规则/阈值/关键词必须可配置，不硬编码
- **可审计**：版本 + 来源 + 操作记录缺一不可
- **可解释**：每个分数必须能还原到具体数据依据
- **多租户**：Phase 1 起必须支持多企业账户隔离

## 开发环境

- Python：3.11+
- 数据库：SQLite（Phase 0）→ PostgreSQL（Phase 1）
- 框架：FastAPI（Phase 1）
- 包管理：uv
- 测试：pytest
- 代码检查：ruff, mypy

## 当前阶段：Phase 0（2026-08 ~ 2026-09）

**目标**：核心资产封装为 Python 包，发布到 GitHub Release

**P0 任务队列**：
1. P0-1: 修复风险等级阈值 Bug（S≥8000 → S≥85）
2. P0-2: risk_events 表增加 extracted_language 字段
3. P0-3: 创建 whyfxpg Python 包，发布到 GitHub Release
4. P0-4: 封装 RiskScorer 为独立 assess() 接口
5. P0-5: 编写 whyfxpg 包 API 文档
6. P0-6: 数据源调研矩阵文档（全球召回数据源）

## 质量门禁

每次 commit 前必须通过：
```bash
pytest tests/ -v        # 全部测试通过
ruff check whyfxpg/     # 无 ERROR
mypy whyfxpg/           # 无 ERROR
```

## 文档同步规则

改了代码 → 必须同步更新 `docs/01-07` 中对应的文档。
改了 API → 必须更新 `docs/04-API接口说明书.md`。
改了数据库 schema → 必须更新 `docs/03-数据库设计说明书.md`。

## 紧急联系人

用户通过飞书接收通知。如遇严重问题（数据库崩溃、P0 安全漏洞），发飞书消息给用户。

## 禁止事项

- 不得在未告知用户的情况下删除任何文档
- 不得在未告知用户的情况下修改 `docs/07-复现与优化指南.md` 中的已知缺陷列表
- 不得在未告知用户的情况下更改项目架构方向
