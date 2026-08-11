"""003: 为已有 risk_events 表添加 causal_factor 列（仅当不存在时）。"""
import sqlite3


def run(conn: sqlite3.Connection) -> None:
    cursor = conn.execute("PRAGMA table_info(risk_events)")
    columns = {row[1] for row in cursor.fetchall()}
    if "causal_factor" not in columns:
        conn.execute("ALTER TABLE risk_events ADD COLUMN causal_factor REAL DEFAULT 1.0")
