-- 010: 添加 rescored_at 字段，用于动态评分刷新去重
-- 防止同一事件因同一个新信号被重复重算
ALTER TABLE risk_events ADD COLUMN rescored_at DATETIME;
CREATE INDEX IF NOT EXISTS idx_risk_events_rescored_at ON risk_events (rescored_at);
