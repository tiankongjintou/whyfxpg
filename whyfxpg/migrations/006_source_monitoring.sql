-- T17: Source monitoring observability columns and snapshot table.

-- Extend crawl_logs with timing and size so we can compute latency/freshness.
ALTER TABLE crawl_logs ADD COLUMN request_started_at DATETIME;
ALTER TABLE crawl_logs ADD COLUMN latency_ms INTEGER;
ALTER TABLE crawl_logs ADD COLUMN content_length INTEGER;

-- Periodic health snapshot table for trend charts and historical audit.
CREATE TABLE IF NOT EXISTS source_health_snapshots (
    snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id TEXT NOT NULL,
    captured_at DATETIME NOT NULL,
    health_score REAL DEFAULT 0.0,
    freshness_score REAL DEFAULT 0.0,
    latency_ms INTEGER,
    coverage_score REAL DEFAULT 0.0,
    error_rate REAL DEFAULT 0.0,
    status TEXT DEFAULT 'unknown',
    details_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_crawl_logs_source_run ON crawl_logs (source_id, run_at);
CREATE INDEX IF NOT EXISTS idx_source_health_snapshots_source_captured ON source_health_snapshots (source_id, captured_at);
