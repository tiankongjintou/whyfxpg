-- 004: configuration object version registry for Admin CRUD seam

CREATE TABLE IF NOT EXISTS config_objects (
    object_type TEXT NOT NULL,           -- source | rule | model | dimension | taxonomy
    object_id   TEXT NOT NULL,
    version_id  TEXT NOT NULL,
    status      TEXT NOT NULL,           -- draft | published | deprecated
    payload     TEXT NOT NULL,           -- JSON snapshot of the object
    created_at  DATETIME NOT NULL,
    created_by  TEXT,
    published_at DATETIME,
    published_by TEXT,
    PRIMARY KEY (object_type, object_id, version_id)
);

CREATE INDEX IF NOT EXISTS idx_config_objects_lookup
ON config_objects(object_type, object_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_config_objects_version
ON config_objects(version_id);
