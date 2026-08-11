"""Tests for ConfigurationAdminService and InMemoryConfigStoreAdapter."""

import sqlite3

import pytest

from whyfxpg.adapters.config.in_memory_config_store import InMemoryConfigStoreAdapter
from whyfxpg.migrations import MigrationRunner
from whyfxpg.services.admin.configuration_admin_service import (
    ConfigDraft,
    ConfigurationAdminService,
)


@pytest.fixture
def in_memory_db():
    conn = sqlite3.connect(":memory:")
    MigrationRunner(conn).run()
    return conn


@pytest.fixture
def service(in_memory_db):
    store = InMemoryConfigStoreAdapter()
    return ConfigurationAdminService(store, db_conn=in_memory_db)


def test_create_and_get(service):
    draft = ConfigDraft(
        object_type="source",
        object_id="test_source",
        payload={"name": "Test Source", "url": "https://example.com"},
    )
    record = service.create(draft)
    assert record.object_id == "test_source"
    assert record.status == "draft"

    fetched = service.get("source", "test_source")
    assert fetched is not None
    assert fetched.payload["name"] == "Test Source"


def test_create_duplicate_fails(service):
    draft = ConfigDraft(object_type="source", object_id="dup", payload={})
    service.create(draft)
    with pytest.raises(ValueError):
        service.create(draft)


def test_update(service):
    service.create(ConfigDraft(object_type="rule", object_id="r1", payload={"name": "Old"}))
    updated = service.update("rule", "r1", {"name": "New"})
    assert updated.status == "draft"
    assert updated.payload["name"] == "New"


def test_delete(service):
    service.create(ConfigDraft(object_type="dimension", object_id="d1", payload={"name": "D1"}))
    service.delete("dimension", "d1")
    assert service.get("dimension", "d1") is None


def test_publish_creates_version(service, in_memory_db):
    service.create(ConfigDraft(object_type="model", object_id="m1", payload={"model_name": "m1"}))
    published = service.publish("model", "m1", published_by="tester")
    assert published.status == "published"
    assert published.published_by == "tester"

    versions = service.versions("model", "m1")
    assert len(versions) >= 1
    assert versions[0].status == "published"


def test_rollback(service):
    service.create(ConfigDraft(object_type="taxonomy", object_id="t1", payload={"name": "A"}))
    service.update("taxonomy", "t1", {"name": "B"})
    versions = service.versions("taxonomy", "t1")
    # Find the version that originally had name A.
    version_a = next((v for v in versions if v.payload.get("name") == "A"), None)
    assert version_a is not None

    rolled = service.rollback("taxonomy", "t1", version_a.version_id)
    assert rolled.payload["name"] == "A"
    assert rolled.status == "draft"


def test_list(service):
    service.create(ConfigDraft(object_type="source", object_id="s1", payload={"name": "S1"}))
    service.create(ConfigDraft(object_type="source", object_id="s2", payload={"name": "S2"}))
    items = service.list("source")
    assert len(items) == 2


def test_invalid_object_type(service):
    with pytest.raises(ValueError):
        service.list("unknown")
