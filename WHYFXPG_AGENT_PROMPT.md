# WHYFXPG Agent 启动提示词

---

## Claude Code / Codex / OpenCode 粘贴用

```
你将在以下目录工作：
D:\Seafile\SeaHome\TempProjects\WHYfxpg

请按顺序执行：

1. 阅读项目根目录的 AGENTS.md，了解项目级开发约束
2. 阅读 .scratch/wayfinder/DEV-GUIDE.md，了解开发流程和质量门禁
3. 阅读你要完成的 ticket 文件（从以下列表中选择一个无阻塞的 ticket）：
   - P01: .scratch/wayfinder/issues/phase1-api-platform/P01-sqlite-to-postgresql.md
   - P07: .scratch/wayfinder/issues/phase1-api-platform/P07-pydantic-config.md（可与 P01 并行）
   - TD01: .scratch/wayfinder/issues/phase1-api-platform/TD01-score-overflow-fix.md（可与任何 ticket 并行）
   - TD02: .scratch/wayfinder/issues/phase1-api-platform/TD02-database-indexes.md（可与任何 ticket 并行）
4. 阅读 ticket 中引用的源码文件，理解现有实现
5. 实现 ticket 中定义的所有 acceptance criteria
6. 运行质量门禁：
   python scripts/quality_gate.py
   （如只想检查 lint/type 而跳过测试：python scripts/quality_gate.py --skip-tests）
7. 如有 schema 变更，更新 docs/03-数据库设计说明书.md
   如有 API 变更，更新 docs/04-API接口说明书.md
8. Git commit，格式：[P01-xxx] 或 [TD-xx]

遇到以下情况必须停下来发飞书消息给用户，不能自行决定：
- 工作量超过 2 人天
- ticket 描述与实际代码/需求不一致
- 需要修改其他 ticket 的范围或 blocking edges
- 技术选型与 docs/技术改造路线图.md 不符
```

---

## 注意事项

- **先选无阻塞的 ticket**：P01、P07、TD01、TD02 可以立即开始
- **不要选有依赖的 ticket**：P02/P03/P04 依赖 P01，P05 依赖 P03，以此类推
- **质量门禁必须全部通过才能 commit**
- **文档同步是强制要求**，不是可选项
