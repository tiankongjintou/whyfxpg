-- 002: 因果知识图谱表
CREATE TABLE IF NOT EXISTS causal_nodes (
    node_id TEXT PRIMARY KEY,
    node_type TEXT NOT NULL,
    name TEXT NOT NULL,
    properties TEXT DEFAULT '{}',
    risk_score REAL DEFAULT 0.5,
    source TEXT,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(node_type, name)
);

CREATE TABLE IF NOT EXISTS causal_edges (
    edge_id TEXT PRIMARY KEY,
    from_node TEXT NOT NULL,
    to_node TEXT NOT NULL,
    edge_type TEXT NOT NULL,
    weight REAL DEFAULT 0.5,
    evidence TEXT DEFAULT '',
    source TEXT,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (from_node) REFERENCES causal_nodes(node_id),
    FOREIGN KEY (to_node) REFERENCES causal_nodes(node_id)
);

CREATE TABLE IF NOT EXISTS causal_paths (
    path_id TEXT PRIMARY KEY,
    root_event_id TEXT,
    chain TEXT NOT NULL,
    total_weight REAL,
    confidence REAL,
    explanation TEXT,
    generated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_cn_type ON causal_nodes(node_type);
CREATE INDEX IF NOT EXISTS idx_cn_name ON causal_nodes(name);
CREATE INDEX IF NOT EXISTS idx_ce_from ON causal_edges(from_node);
CREATE INDEX IF NOT EXISTS idx_ce_to ON causal_edges(to_node);
CREATE INDEX IF NOT EXISTS idx_ce_type ON causal_edges(edge_type);
