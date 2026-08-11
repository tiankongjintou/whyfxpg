import threading

from whyfxpg.core.db import get_db_connection, init_db

TABLES = [
    "monitor_sources",
    "raw_pages",
    "risk_events",
    "product_risk_summary",
    "country_risk_summary",
    "enterprise_risk_summary",
    "alert_records",
    "manual_reviews",
    "crawl_logs",
    "config_versions",
    "config_objects",
    "source_health_snapshots",
]


def test_init_db_creates_tables(initialized_db: str) -> None:
    conn = get_db_connection(initialized_db)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    existing = {row["name"] for row in cursor.fetchall()}
    conn.close()
    for table in TABLES:
        assert table in existing, f"表 {table} 未创建"


def test_init_db_enables_wal(initialized_db: str) -> None:
    # init_db 是兼容 shim，仍会设置 WAL
    init_db(initialized_db)
    conn = get_db_connection(initialized_db)
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode")
    mode = cursor.fetchone()[0]
    conn.close()
    assert mode.lower() == "wal"


def test_get_db_connection_has_busy_timeout(initialized_db: str) -> None:
    conn = get_db_connection(initialized_db)
    cursor = conn.cursor()
    cursor.execute("PRAGMA busy_timeout")
    timeout = cursor.fetchone()[0]
    conn.close()
    assert timeout == 10000


def test_concurrent_inserts_do_not_raise(initialized_db: str) -> None:
    """并发写入同一数据库不应立即抛出 database is locked"""
    errors = []

    def worker(idx: int) -> None:
        try:
            conn = get_db_connection(initialized_db)
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO monitor_sources (source_id, name, status) VALUES (?, ?, ?)",
                (f"src_{idx}", f"Source {idx}", "ok"),
            )
            conn.commit()
            conn.close()
        except Exception as e:  # noqa: BLE001 — 外部调用/配置解析兜底,刻意吞异常
            errors.append(str(e))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"并发写入出现错误: {errors}"

    conn = get_db_connection(initialized_db)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM monitor_sources WHERE source_id LIKE 'src_%'")
    count = cursor.fetchone()[0]
    conn.close()
    assert count == 10
