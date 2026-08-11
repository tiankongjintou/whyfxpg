"""Tests for FileConfigStoreAdapter."""

import pytest
import yaml

from whyfxpg.adapters.config.file_config_store import FileConfigStoreAdapter
from whyfxpg.migrations import MigrationRunner
from whyfxpg.ports.config_store import ConfigRecord
from whyfxpg.services.admin.configuration_admin_service import (
    ConfigDraft,
    ConfigurationAdminService,
)


@pytest.fixture
def temp_config_dir(tmp_path):
    return tmp_path / "config"


def test_source_crud(temp_config_dir):
    # Seed the legacy sources.yaml
    sources_path = temp_config_dir / "sources.yaml"
    sources_path.parent.mkdir(parents=True, exist_ok=True)
    sources_path.write_text(
        yaml.safe_dump(
            {"sources": {"legacy": {"name": "Legacy", "url": "https://legacy.example"}}},
            allow_unicode=True,
        )
    )

    adapter = FileConfigStoreAdapter(config_dir=temp_config_dir)
    items = adapter.list("source")
    assert len(items) == 1
    assert items[0].object_id == "legacy"

    record = ConfigRecord(
        object_type="source",
        object_id="new_src",
        status="draft",
        payload={"name": "New", "url": "https://new.example"},
        version_id="v1",
        created_at=items[0].created_at,
        created_by="test",
    )
    adapter.write(record)

    items = adapter.list("source")
    assert len(items) == 2
    ids = {i.object_id for i in items}
    assert ids == {"legacy", "new_src"}

    adapter.delete("source", "legacy")
    items = adapter.list("source")
    assert [i.object_id for i in items] == ["new_src"]


def test_rule_crud(temp_config_dir):
    rules_path = temp_config_dir / "alert_rules.yaml"
    rules_path.parent.mkdir(parents=True, exist_ok=True)
    rules_path.write_text(
        yaml.safe_dump({"rules": [{"rule_id": "r1", "name": "R1"}]}, allow_unicode=True)
    )

    adapter = FileConfigStoreAdapter(config_dir=temp_config_dir)
    items = adapter.list("rule")
    assert len(items) == 1

    adapter.write(
        ConfigRecord(
            object_type="rule",
            object_id="r2",
            status="draft",
            payload={"name": "R2"},
            version_id="v2",
            created_at=items[0].created_at,
            created_by="test",
        )
    )
    items = adapter.list("rule")
    assert len(items) == 2

    # Update existing rule
    adapter.write(
        ConfigRecord(
            object_type="rule",
            object_id="r1",
            status="published",
            payload={"name": "R1 updated"},
            version_id="v3",
            created_at=items[0].created_at,
            created_by="test",
        )
    )
    r1 = adapter.read("rule", "r1")
    assert r1 is not None
    assert r1.payload["name"] == "R1 updated"

    # Versions snapshot
    versions = adapter.versions("rule", "r1")
    assert len(versions) >= 1
    assert versions[0].version_id == "v3"


def test_model_crud(temp_config_dir):
    adapter = FileConfigStoreAdapter(config_dir=temp_config_dir)
    # Empty model file should be absent
    assert adapter.list("model") == []

    adapter.write(
        ConfigRecord(
            object_type="model",
            object_id="m1",
            status="published",
            payload={"model_name": "m1", "description": "desc"},
            version_id="mv1",
            created_at=__import__("datetime").datetime.now(),
            created_by="test",
        )
    )
    m1 = adapter.read("model", "m1")
    assert m1 is not None
    assert m1.payload["description"] == "desc"

    # Ensure file was written and contains model_name
    model_path = temp_config_dir / "risk_model.yaml"
    assert model_path.exists()
    data = yaml.safe_load(model_path.read_text(encoding="utf-8"))
    assert data["model_name"] == "m1"


def test_dimension_and_taxonomy_crud(temp_config_dir):
    adapter = FileConfigStoreAdapter(config_dir=temp_config_dir)

    adapter.write(
        ConfigRecord(
            object_type="dimension",
            object_id="dim_country",
            status="draft",
            payload={"name": "Country", "source_field": "country"},
            version_id="dv1",
            created_at=__import__("datetime").datetime.now(),
            created_by="test",
        )
    )
    dims = adapter.list("dimension")
    assert len(dims) == 1
    assert dims[0].payload["name"] == "Country"

    adapter.write(
        ConfigRecord(
            object_type="taxonomy",
            object_id="hs_1234",
            status="published",
            payload={"name": "HS 1234"},
            version_id="tv1",
            created_at=__import__("datetime").datetime.now(),
            created_by="test",
        )
    )
    tax = adapter.list("taxonomy")
    assert len(tax) == 1


def test_dashboard_template_crud(temp_config_dir):
    adapter = FileConfigStoreAdapter(config_dir=temp_config_dir)
    adapter.write(
        ConfigRecord(
            object_type="dashboard_template",
            object_id="default",
            status="published",
            payload={
                "name": "Default",
                "widgets": [
                    {
                        "widget_id": "kpi",
                        "type": "metric",
                        "query": "summary.total_events",
                        "title": "Total",
                    }
                ],
            },
            version_id="dv1",
            created_at=__import__("datetime").datetime.now(),
            created_by="test",
        )
    )
    templates = adapter.list("dashboard_template")
    assert len(templates) == 1
    assert templates[0].payload["name"] == "Default"

    # Update existing template
    adapter.write(
        ConfigRecord(
            object_type="dashboard_template",
            object_id="default",
            status="published",
            payload={"name": "Default Updated", "widgets": []},
            version_id="dv2",
            created_at=__import__("datetime").datetime.now(),
            created_by="test",
        )
    )
    updated = adapter.read("dashboard_template", "default")
    assert updated is not None
    assert updated.payload["name"] == "Default Updated"


def test_versions_merge_with_db(temp_config_dir, tmp_path):
    # Use a real db file so ConfigObjectStore can be used via the service.
    import sqlite3

    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    MigrationRunner(conn).run()

    adapter = FileConfigStoreAdapter(config_dir=temp_config_dir)
    service = ConfigurationAdminService(adapter, db_conn=conn)

    service.create(
        ConfigDraft(
            object_type="source",
            object_id="s",
            payload={"name": "S"},
        )
    )
    service.publish("source", "s")
    versions = service.versions("source", "s")
    assert len(versions) >= 1
    published_versions = [v for v in versions if v.status == "published"]
    assert len(published_versions) == 1
    assert published_versions[0].payload["name"] == "S"
    conn.close()
