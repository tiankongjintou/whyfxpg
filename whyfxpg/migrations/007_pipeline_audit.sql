-- 信息管道运行审计与血缘追溯
CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id TEXT PRIMARY KEY,
    pipeline_name TEXT,
    started_at TEXT,
    completed_at TEXT,
    status TEXT,
    error_message TEXT,
    archived_path TEXT
);

CREATE TABLE IF NOT EXISTS pipeline_stage_runs (
    stage_run_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    stage_name TEXT NOT NULL,
    stage_order INTEGER NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    status TEXT,
    input_artifact_handle TEXT,
    output_artifact_handle TEXT,
    error_message TEXT,
    FOREIGN KEY (run_id) REFERENCES pipeline_runs(run_id)
);

CREATE TABLE IF NOT EXISTS audit_log (
    audit_id TEXT PRIMARY KEY,
    happened_at TEXT,
    actor TEXT,
    action TEXT,
    target_type TEXT,
    target_id TEXT,
    before_value TEXT,
    after_value TEXT,
    reason TEXT
);

CREATE INDEX IF NOT EXISTS idx_pipeline_stage_runs_run_id ON pipeline_stage_runs(run_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_target ON audit_log(target_type, target_id);
