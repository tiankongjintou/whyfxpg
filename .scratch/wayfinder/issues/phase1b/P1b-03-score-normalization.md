# P1b-03 — 评分归一化 0-100(§6.1-3)

**What to build:**
docs/05 §6.1 差距表遗留项:TD01 对数化后总分量纲仍为 0-10000+,
与 P0-1 阈值(S≥85/M≥70/L≥50,0-100 语义)不匹配——轻微事件(1425 分)
会被误判最高危 S 级。将总分单调归一化到 0-100,`map_to_risk_level` 改用
归一化值,阈值语义对齐。

**Blocked by:** None

**Status:** completed
**Claimed by:** reasonix-agent (2026-08-11)
**Completed:** 2026-08-11

## Resolution (2026-08-11)

- AC-1 ✅ `normalize_score(total) = 100*total/(total+3000)`，C 可经
  `normalization_constant` 配置；0→0、∞→100 渐近、单调。
- AC-2 ✅ ScoringResult 新增 `normalized_score`（round 2 位），`total_score`
  保留原量纲向后兼容。
- AC-3 ✅ `map_to_risk_level` 输入切换为归一化分；阈值 85/70/50 语义对齐
  （修复合入矛盾：此前 1425≥85 把轻微事件误判 S 级）。
- AC-4 ✅ 新增 test_normalize_score_range；4 处测试 fixture 旧阈值
  (8000/3000/1000)→(85/70/50)；test_t1_lock_fix 'S'→'A'、test_v2_integration
  'S'→'M'、test_score_computes rs_level 'M'→'L' 修正（语义变化正确体现）。
- AC-5 ✅ 全量 342 passed + ruff/mypy 全绿。
- AC-6 ✅ docs/05 差距表(风险分范围/等级阈值两行改 ✅) + 归一化公式章节。
- 附带修复：`services/__init__.py` 副作用导入导致循环导入
  (adapters.reports→ports.report_renderer→services→report_generator→
  adapters.reports partial)——清空为纯文档包，根治导入顺序脆弱性。

## Acceptance criteria

- [ ] `normalize_score(total) = 100*total/(total+C)`,C 默认 3000(可配置
      `normalization_constant`);0→0,∞→100 渐近,单调
- [ ] ScoringResult 新增 `normalized_score` 字段,total_score 保留(向后兼容)
- [ ] `map_to_risk_level` 输入语义切换为 0-100 归一化分
- [ ] 测试:normalize 单测 + 阈值断言改 0-100 量纲 + t1_lock_fix 等级修正
      (1425→A)+ v2 集成等级修正(9025→M)
- [ ] 全量 pytest + ruff + mypy 全绿
- [ ] docs/05 差距表与公式更新
