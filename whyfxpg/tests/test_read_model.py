"""Tests for whyfxpg.webui.read_model (DashboardReadModel)."""

import sqlite3
from pathlib import Path

import pytest

from whyfxpg.webui.read_model import DashboardReadModel


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    return str(tmp_path / "test.db")


@pytest.fixture
def populated_db(db_path: str) -> str:
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE monitor_sources (
            source_id TEXT PRIMARY KEY,
            name TEXT,
            source_type TEXT,
            url TEXT,
            enabled INTEGER,
            check_interval INTEGER,
            last_check_at TEXT,
            status TEXT,
            last_content_length INTEGER,
            error_msg TEXT
        );
        INSERT INTO monitor_sources (source_id, name, source_type, url, enabled,
            check_interval, last_check_at, status, last_content_length, error_msg)
        VALUES ('s1', 'Test API', 'api', 'http://example.com', 1, 60,
            '2026-07-31 12:00:00', 'ok', 1234, NULL);
        INSERT INTO monitor_sources (source_id, name, source_type, url, enabled,
            check_interval, last_check_at, status, last_content_length, error_msg)
        VALUES ('s2', 'Old Feed', 'rss', 'http://feed.example.com', 0, 120,
            '2026-07-30 10:00:00', 'error', 0, 'timeout');
        """
    )
    conn.commit()
    conn.close()
    return db_path


def test_get_source_status_returns_all_columns(populated_db: str) -> None:
    read_model = DashboardReadModel(db_path=populated_db)
    df = read_model.get_source_status()

    assert len(df) == 2
    assert set(df.columns) >= {
        "source_id", "name", "source_type", "url", "enabled", "check_interval",
        "last_check_at", "status", "last_content_length", "error_msg",
    }
    assert list(df["name"]) == ["Test API", "Old Feed"]
    assert list(df["status"]) == ["ok", "error"]


def test_get_source_status_empty_db(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE monitor_sources (
            source_id TEXT PRIMARY KEY,
            name TEXT,
            source_type TEXT,
            url TEXT,
            enabled INTEGER,
            check_interval INTEGER,
            last_check_at TEXT,
            status TEXT,
            last_content_length INTEGER,
            error_msg TEXT
        );
        """
    )
    conn.commit()
    conn.close()

    read_model = DashboardReadModel(db_path=db_path)
    df = read_model.get_source_status()
    assert df.empty
