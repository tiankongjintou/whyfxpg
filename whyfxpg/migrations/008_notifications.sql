-- 通知中心表：记录流水线失败、数据源异常等需要人工关注的通知。
CREATE TABLE IF NOT EXISTS notifications (
    notification_id TEXT PRIMARY KEY,
    notification_type TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'info',
    title TEXT NOT NULL,
    message TEXT,
    source_type TEXT,
    source_id TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    read_at DATETIME,
    dismissed_at DATETIME
);

CREATE INDEX IF NOT EXISTS idx_notifications_unread
ON notifications (read_at, dismissed_at, created_at DESC);
