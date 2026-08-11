-- 001: 初始业务表 + 索引
-- 监控源状态表
CREATE TABLE IF NOT EXISTS monitor_sources (
    source_id TEXT PRIMARY KEY,
    name TEXT,
    url TEXT,
    source_type TEXT,
    enabled INTEGER DEFAULT 1,
    check_interval TEXT,
    last_check_at DATETIME,
    last_hash TEXT,
    last_content_length INTEGER,
    status TEXT DEFAULT 'ok',
    error_msg TEXT
);

-- 原始采集内容表
CREATE TABLE IF NOT EXISTS raw_pages (
    page_id TEXT PRIMARY KEY,
    source_id TEXT,
    url TEXT,
    fetched_at DATETIME,
    content_type TEXT,
    content_hash TEXT,
    raw_content BLOB,
    status TEXT DEFAULT 'fetched',
    error_msg TEXT,
    FOREIGN KEY (source_id) REFERENCES monitor_sources (source_id)
);

-- 风险事件表（核心数据总线）
CREATE TABLE IF NOT EXISTS risk_events (
    event_id TEXT PRIMARY KEY,
    page_id TEXT,
    source_id TEXT,
    source_url TEXT,
    publish_date DATE,
    title TEXT,
    product_name TEXT,
    brand TEXT,
    model TEXT,
    hs_code TEXT,
    product_category TEXT,
    country TEXT,
    manufacturer TEXT,
    hazard_type TEXT,
    hazard_desc TEXT,
    severity_level TEXT,
    ss_score INTEGER,
    probability_level TEXT,
    ps_score INTEGER,
    country_factor REAL DEFAULT 1.0,
    product_factor REAL DEFAULT 1.0,
    history_factor REAL DEFAULT 1.0,
    evidence_factor REAL DEFAULT 1.0,
    causal_factor REAL DEFAULT 1.0,
    total_score REAL,
    rs_level TEXT,
    standards TEXT,
    original_text TEXT,
    extracted_at DATETIME,
    evaluated_at DATETIME,
    config_version TEXT,
    model_version TEXT,
    extraction_confidence REAL DEFAULT 0.0,
    review_status TEXT DEFAULT 'auto',
    FOREIGN KEY (page_id) REFERENCES raw_pages (page_id)
);

-- 产品风险汇总表
CREATE TABLE IF NOT EXISTS product_risk_summary (
    product_id TEXT PRIMARY KEY,
    product_name TEXT,
    brand TEXT,
    hs_code TEXT,
    product_category TEXT,
    country TEXT,
    manufacturer TEXT,
    event_count INTEGER DEFAULT 0,
    latest_ss INTEGER,
    latest_ps INTEGER,
    latest_total_score REAL,
    latest_rs_level TEXT,
    highest_hazard_type TEXT,
    last_event_date DATE,
    first_event_date DATE,
    updated_at DATETIME,
    config_version TEXT,
    model_version TEXT
);

-- 国别风险汇总表
CREATE TABLE IF NOT EXISTS country_risk_summary (
    country TEXT PRIMARY KEY,
    event_count INTEGER DEFAULT 0,
    s_count INTEGER DEFAULT 0,
    m_count INTEGER DEFAULT 0,
    l_count INTEGER DEFAULT 0,
    a_count INTEGER DEFAULT 0,
    latest_event_date DATE,
    updated_at DATETIME
);

-- 企业风险汇总表
CREATE TABLE IF NOT EXISTS enterprise_risk_summary (
    manufacturer TEXT PRIMARY KEY,
    country TEXT,
    event_count INTEGER DEFAULT 0,
    s_count INTEGER DEFAULT 0,
    m_count INTEGER DEFAULT 0,
    l_count INTEGER DEFAULT 0,
    a_count INTEGER DEFAULT 0,
    latest_event_date DATE,
    updated_at DATETIME
);

-- 预警记录表
CREATE TABLE IF NOT EXISTS alert_records (
    alert_id TEXT PRIMARY KEY,
    rule_id TEXT,
    rule_name TEXT,
    triggered_at DATETIME,
    object_type TEXT,
    object_value TEXT,
    severity TEXT,
    triggered_value TEXT,
    description TEXT,
    status TEXT DEFAULT 'pending',
    confirmed_by TEXT,
    confirmed_at DATETIME,
    notes TEXT
);

-- 人工复核表
CREATE TABLE IF NOT EXISTS manual_reviews (
    review_id TEXT PRIMARY KEY,
    event_id TEXT,
    reviewer TEXT,
    reviewed_at DATETIME,
    action TEXT,
    original_ss INTEGER,
    adjusted_ss INTEGER,
    original_ps INTEGER,
    adjusted_ps INTEGER,
    original_rs TEXT,
    adjusted_rs TEXT,
    reason TEXT,
    FOREIGN KEY (event_id) REFERENCES risk_events (event_id)
);

-- 配置版本表
CREATE TABLE IF NOT EXISTS config_versions (
    version_id TEXT PRIMARY KEY,
    created_at DATETIME,
    created_by TEXT,
    description TEXT,
    file_hashes TEXT,
    config_snapshot TEXT
);

-- 采集日志表
CREATE TABLE IF NOT EXISTS crawl_logs (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id TEXT,
    run_at DATETIME,
    status TEXT,
    pages_fetched INTEGER DEFAULT 0,
    pages_new INTEGER DEFAULT 0,
    error_msg TEXT
);

-- 初始索引
CREATE INDEX IF NOT EXISTS idx_raw_pages_source_id ON raw_pages (source_id);
CREATE INDEX IF NOT EXISTS idx_raw_pages_status ON raw_pages (status);
CREATE INDEX IF NOT EXISTS idx_risk_events_source_id ON risk_events (source_id);
CREATE INDEX IF NOT EXISTS idx_risk_events_country ON risk_events (country);
CREATE INDEX IF NOT EXISTS idx_risk_events_product_category ON risk_events (product_category);
CREATE INDEX IF NOT EXISTS idx_risk_events_hazard_type ON risk_events (hazard_type);
CREATE INDEX IF NOT EXISTS idx_risk_events_rs_level ON risk_events (rs_level);
CREATE INDEX IF NOT EXISTS idx_risk_events_publish_date ON risk_events (publish_date);
CREATE INDEX IF NOT EXISTS idx_risk_events_ss_score ON risk_events (ss_score) WHERE ss_score IS NULL;
CREATE INDEX IF NOT EXISTS idx_alert_records_status ON alert_records (status);
