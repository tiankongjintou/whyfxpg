from pathlib import Path

from whyfxpg.core.config_version import ConfigVersionManager

CONFIG_FILES = [
    "sources.yaml",
    "keywords.yaml",
    "extract_rules.yaml",
    "risk_model.yaml",
    "alert_rules.yaml",
    "version_history.yaml",
]


def test_create_version_returns_unchanged_when_same(initialized_db: str, temp_config_dir: str) -> None:
    manager = ConfigVersionManager(temp_config_dir, initialized_db)
    first = manager.create_version(author="test", description="initial")
    assert first["changed"] is True

    second = manager.create_version(author="test", description="unchanged")
    assert second["changed"] is False


def test_create_version_bumps_on_config_change(initialized_db: str, temp_config_dir: str) -> None:
    manager = ConfigVersionManager(temp_config_dir, initialized_db)
    first = manager.create_version(author="test", description="initial")
    assert first["version_id"] == "1.0"

    # 修改一个配置文件
    sources_path = Path(temp_config_dir) / "sources.yaml"
    sources_path.write_text(sources_path.read_text(encoding="utf-8") + "\n# changed", encoding="utf-8")

    second = manager.create_version(author="test", description="after change")
    assert second["changed"] is True
    assert second["version_id"] == "1.1"


def test_run_returns_success(initialized_db: str, temp_config_dir: str) -> None:
    manager = ConfigVersionManager(temp_config_dir, initialized_db)
    result = manager.run()
    assert result["module"] == "config_version"
    assert result["status"] == "success"
    assert result["version_id"] == "1.0"
