-- 009: 为 risk_events 表增加 extracted_language 字段
-- 支持多语言风险信号挖掘，标识事件原文语言
-- P0-2: https://github.com/.../issues/...

ALTER TABLE risk_events ADD COLUMN extracted_language VARCHAR(10);
