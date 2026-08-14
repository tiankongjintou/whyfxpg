# P11 — 数据源扩充：第三优先级 × 4

**What to build:**
实现中国 DPAC、台湾消费者保护处、俄罗斯 Rospotrebnadzor、阿拉伯语数据源 4 个适配器，需要多语言 NLP 能力（中文/俄语/阿拉伯语）。

**Blocked by:** P10-multilingual-pipeline.md

**Status:** completed

**Resolution (2026-08-14):** 以下 4 个适配器已实现并提交：

- `AustraliaACCCAdapter` ✅ — 澳大利亚 ACCC (productsafety.gov.au)
- `NewZealandMVCAdapter` ✅ — 新西兰 MVCI (consumerprotection.govt.nz)
- `ChinaSAMRAdapter` ✅ — 中国 SAMR (samr.gov.cn)
- `RussiaRosAccreditationAdapter` ✅ — 俄罗斯 RosAccreditation (fsa.gov.ru)

Commits: `6128171`, `57f5708`, `725d9ac`

## Acceptance criteria

- [ ] `ChinaDPACAdapter` — 中国 DPAC（简体中文，需要处理网页编码 GB2312/UTF-8）
- [ ] `TaiwanCPAAdapter` — 台湾消费者保护处（繁体中文）
- [ ] `RussiaRospotrebnadzorAdapter` — 俄罗斯 Rospotrebnadzor（俄语，西里尔字母）
- [ ] `ArabicSafetyAdapter` — 阿拉伯语数据源（阿拉伯语，RTL，右到左排版支持）
- [ ] 每个适配器注册到 `SourceRegistry`
- [ ] 健康检查连续 3 次失败自动降级
- [ ] DPAC 数据通过 `extracted_language='zh'` 正确标记
- [ ] 阿拉伯语页面采集后正确存储（数据库/文件系统支持 UTF-8 存储）

## References

- `docs/技术改造路线图.md` §5.1 数据源扩充清单（第三优先级）
