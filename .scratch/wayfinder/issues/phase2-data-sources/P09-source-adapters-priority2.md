# P09 — 数据源扩充：第二优先级 × 4

**What to build:**
实现巴西 ANVISA、印度 BIS CRS、墨西哥 PROFECO、沙特 SFDA 4 个数据源适配器，需要定制解析逻辑（葡萄牙语/英语/西班牙语/阿拉伯语）。

**Blocked by:** P08-source-adapters-priority1.md

**Status:** completed

**Resolution (2026-08-14):**
- `b9b78bf` BrazilANVISAAdapter — 葡萄牙语，gov.br API + HTML fallback
- `8fa795f` IndiaBISAdapter — 英语，BIS CRS PDF + API
- `7052a0d` MexicoPROFECOAdapter — 西班牙语，PROFECO 安全预警
- `38bbf3c` SaudiSFDAAdapter — 阿拉伯语/英语双语，Saudi FDA 官网

所有 8 个 adapter 已注册到 SourceRegistry。

## Acceptance criteria

- [ ] `BrazilANVISAAdapter` — 巴西 ANVISA（葡萄牙语，gov.br 域名）
- [ ] `IndiaBISAdapter` — 印度 BIS CRS（英语，需处理 PDF 格式）
- [ ] `MexicoPROFECOAdapter` — 墨西哥 PROFECO（西班牙语）
- [ ] `SaudiSFDAAdapter` — 沙特 SFDA（阿拉伯语/英语双语，需 RTL 语言支持）
- [ ] 每个适配器注册到 `SourceRegistry`
- [ ] 健康检查连续 3 次失败自动降级
- [ ] 文档更新：`docs/全球数据源调研矩阵.md` 补充 Saudi SFDA 条目

## References

- `docs/技术改造路线图.md` §5.1 数据源扩充清单（第二优先级）
