"""Tests for the Multi-domain seam (T19).

Covers TaxonomyPort, DimensionPort, RulePack merging, DomainRegistryService,
and domain-aware rule evaluation. All tests use temporary config directories
so they do not depend on the production Config folder.
"""

from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

from whyfxpg.adapters.dimensions import (
    FixedDimensionsAdapter,
    InMemoryDimensionAdapter,
)
from whyfxpg.adapters.taxonomy import InMemoryTaxonomyAdapter, LocalYamlTaxonomyAdapter
from whyfxpg.config.models import AlertRule, RiskDimension, TaxonomyNode
from whyfxpg.core.config_loader import ConfigLoader
from whyfxpg.core.domain_profile import RulePack
from whyfxpg.core.rule_engine import RuleEngine
from whyfxpg.services.domain_registry import DomainRegistryService, flatten_rule_packs


# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------
def _write_yaml(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")


@pytest.fixture
def sample_taxonomy_nodes() -> list[TaxonomyNode]:
    return [
        TaxonomyNode(node_id="root", name="Root"),
        TaxonomyNode(
            node_id="84",
            parent_id="root",
            name="机械器具",
            aliases=["机械"],
            keywords=["机械危险"],
        ),
        TaxonomyNode(
            node_id="85",
            parent_id="root",
            name="电机电气设备",
            aliases=["电气"],
            keywords=["电气危险"],
        ),
    ]


@pytest.fixture
def sample_dimensions() -> list[RiskDimension]:
    return [
        RiskDimension(
            dimension_id="country",
            name="国别",
            source_field="country",
            weight=1.0,
            aggregation="count",
        ),
        RiskDimension(
            dimension_id="total_score",
            name="风险分",
            source_field="total_score",
            weight=1.0,
            aggregation="max",
        ),
    ]


@pytest.fixture
def temp_config_with_domains(tmp_path: Path) -> Path:
    """Create a minimal multi-domain config tree under tmp_path."""
    config_dir = tmp_path / "config"

    # Shared base risk model and keywords (top-level, relative to config_dir).
    _write_yaml(
        config_dir / "risk_model.yaml",
        {
            "version": "1.0",
            "severity_levels": {"严重": {"default": 95}},
            "probability_levels": {"可能": {"default": 95}},
            "country_factors": {"德国": 1.0},
            "product_factors": {"机电": 1.0},
            "history_factor": {"formula": "1", "max": 1.0, "min": 1.0},
            "evidence_factors": {"default": 1.0},
            "risk_level_thresholds": {"S": 85, "M": 70, "L": 50, "A": 0},
        },
    )
    _write_yaml(
        config_dir / "keywords.yaml",
        {"keyword_sets": {"default": {"categories": {"机电": ["机电"]}}}},
    )

    # Domain A: import_machinery
    domain_a = config_dir / "domains" / "import_machinery"
    _write_yaml(
        domain_a / "domain.yaml",
        {
            "domain_id": "import_machinery",
            "name": "进口机电",
            "risk_model": "risk_model.yaml",
            "keywords": "keywords.yaml",
            "taxonomy": "domains/import_machinery/taxonomy.yaml",
            "dimensions": "domains/import_machinery/dimensions.yaml",
            "rule_packs_dir": "domains/import_machinery/rule_packs",
        },
    )
    _write_yaml(
        domain_a / "taxonomy.yaml",
        {
            "taxonomy_id": "im_hs",
            "nodes": [
                {"node_id": "root", "name": "机电产品"},
                {
                    "node_id": "84",
                    "parent_id": "root",
                    "name": "机械器具",
                    "aliases": ["机械"],
                    "keywords": ["机械危险"],
                },
            ],
        },
    )
    _write_yaml(
        domain_a / "dimensions.yaml",
        {
            "dimensions": [
                {
                    "dimension_id": "country",
                    "name": "国别",
                    "source_field": "country",
                    "weight": 1.0,
                    "aggregation": "count",
                }
            ]
        },
    )
    _write_yaml(
        domain_a / "rule_packs" / "base.yaml",
        {
            "rule_pack_id": "base",
            "inherits": [],
            "rules": [
                {
                    "rule_id": "country_burst",
                    "name": "国别事件聚集",
                    "condition": {
                        "type": "count_by_dimension",
                        "dimension": "country",
                        "window": "30d",
                        "threshold": 2,
                    },
                    "severity": "medium",
                }
            ],
        },
    )
    _write_yaml(
        domain_a / "rule_packs" / "import_machinery.yaml",
        {
            "rule_pack_id": "import_machinery",
            "inherits": ["base"],
            "rules": [
                {
                    "rule_id": "country_burst",
                    "name": "国别事件聚集（机电）",
                    "condition": {"threshold": 5},
                }
            ],
        },
    )

    # Domain B: toys (higher threshold, no inheritance)
    domain_b = config_dir / "domains" / "toys"
    _write_yaml(
        domain_b / "domain.yaml",
        {
            "domain_id": "toys",
            "name": "玩具",
            "risk_model": "risk_model.yaml",
            "keywords": "keywords.yaml",
            "taxonomy": "domains/toys/taxonomy.yaml",
            "dimensions": "domains/toys/dimensions.yaml",
            "rule_packs_dir": "domains/toys/rule_packs",
        },
    )
    _write_yaml(
        domain_b / "taxonomy.yaml",
        {
            "taxonomy_id": "toys",
            "nodes": [
                {"node_id": "root", "name": "玩具"},
                {
                    "node_id": "95",
                    "parent_id": "root",
                    "name": "儿童玩具",
                    "aliases": ["玩具"],
                    "keywords": ["窒息", "小零件"],
                },
            ],
        },
    )
    _write_yaml(
        domain_b / "dimensions.yaml",
        {
            "dimensions": [
                {
                    "dimension_id": "country",
                    "name": "国别",
                    "source_field": "country",
                    "weight": 2.0,
                    "aggregation": "count",
                }
            ]
        },
    )
    _write_yaml(
        domain_b / "rule_packs" / "toys.yaml",
        {
            "rule_pack_id": "toys",
            "inherits": [],
            "rules": [
                {
                    "rule_id": "country_burst",
                    "name": "国别事件聚集（玩具）",
                    "condition": {
                        "type": "count_by_dimension",
                        "dimension": "country",
                        "window": "30d",
                        "threshold": 10,
                    },
                    "severity": "high",
                }
            ],
        },
    )

    return config_dir


# ----------------------------------------------------------------------
# Taxonomy adapters
# ----------------------------------------------------------------------
def test_local_yaml_taxonomy_adapter(tmp_path: Path) -> None:
    path = tmp_path / "taxonomy.yaml"
    _write_yaml(
        path,
        {
            "taxonomy_id": "test",
            "nodes": [
                {"node_id": "root", "name": "Root"},
                {
                    "node_id": "84",
                    "parent_id": "root",
                    "name": "机械器具",
                    "aliases": ["机械"],
                    "keywords": ["机械危险"],
                },
            ],
        },
    )

    adapter = LocalYamlTaxonomyAdapter(path)
    children = adapter.list_children("root")
    assert len(children) == 1
    assert children[0].node_id == "84"

    results = adapter.search("机械")
    assert any(n.node_id == "84" for n in results)

    event = {"product_name": "机械臂", "product_category": "机械器具"}
    mapped = adapter.map_event(event)
    assert mapped is not None
    assert mapped.node_id == "84"


def test_in_memory_taxonomy_adapter(sample_taxonomy_nodes: list[TaxonomyNode]) -> None:
    adapter = InMemoryTaxonomyAdapter(sample_taxonomy_nodes)
    assert len(adapter.list_children("root")) == 2
    assert len(adapter.search("电气")) == 1
    mapped = adapter.map_event({"product_name": "电气开关"})
    assert mapped is not None
    assert mapped.node_id == "85"


# ----------------------------------------------------------------------
# Dimension adapters
# ----------------------------------------------------------------------
def test_fixed_dimensions_adapter(tmp_path: Path) -> None:
    path = tmp_path / "dimensions.yaml"
    _write_yaml(
        path,
        {
            "dimensions": [
                {
                    "dimension_id": "country",
                    "name": "国别",
                    "source_field": "country",
                    "weight": 1.5,
                    "aggregation": "count",
                },
                {
                    "dimension_id": "score",
                    "name": "分数",
                    "source_field": "score",
                    "weight": 1.0,
                    "aggregation": "max",
                },
            ]
        },
    )

    adapter = FixedDimensionsAdapter(path)
    dims = adapter.list_dimensions()
    assert len(dims) == 2
    assert adapter.weight_of("country") == 1.5
    assert adapter.weight_of("missing") == 1.0

    events = [
        {"country": "德国", "score": 90},
        {"country": "德国", "score": 80},
        {"country": "美国", "score": 70},
    ]
    assert adapter.aggregate("country", events) == {"德国": 2, "美国": 1}
    assert adapter.aggregate("score", events) == 90.0


def test_in_memory_dimension_adapter(sample_dimensions: list[RiskDimension]) -> None:
    adapter = InMemoryDimensionAdapter(sample_dimensions)
    assert len(adapter.list_dimensions()) == 2
    assert adapter.weight_of("country") == 1.0
    events = [{"country": "德国"}, {"country": "德国"}, {"country": "美国"}]
    assert adapter.aggregate("country", events) == {"德国": 2, "美国": 1}


# ----------------------------------------------------------------------
# Rule packs
# ----------------------------------------------------------------------
def test_rule_pack_merge_and_flatten() -> None:
    base = RulePack(
        rule_pack_id="base",
        rules=[
            AlertRule(
                rule_id="country_burst",
                name="Base",
                condition={
                    "type": "count_by_dimension",
                    "dimension": "country",
                    "window": "30d",
                    "threshold": 2,
                },
            )
        ],
    )
    child = RulePack(
        rule_pack_id="child",
        inherits=["base"],
        rules=[
            AlertRule(
                rule_id="country_burst",
                name="Child",
                condition={"threshold": 5},
            )
        ],
    )

    flat = flatten_rule_packs([base, child])
    assert len(flat) == 1
    assert flat[0].rule_id == "country_burst"
    assert flat[0].condition["threshold"] == 5
    assert flat[0].condition["dimension"] == "country"


# ----------------------------------------------------------------------
# Domain registry
# ----------------------------------------------------------------------
def test_domain_registry_loads_and_switches(temp_config_with_domains: Path) -> None:
    service = DomainRegistryService(config_dir=temp_config_with_domains)

    domains = service.list()
    assert len(domains) == 2
    ids = {p.domain_id for p in domains}
    assert ids == {"import_machinery", "toys"}

    # Default active domain should be import_machinery.
    assert service.active_id() == "import_machinery"
    active = service.active()
    assert active is not None
    assert active.domain_id == "import_machinery"
    assert active.taxonomy.taxonomy_id == "im_hs"

    # Switch to toys and verify persistence.
    switched = service.switch("toys")
    assert switched.domain_id == "toys"
    assert service.active_id() == "toys"

    active_file = temp_config_with_domains / "active_domain.yaml"
    assert active_file.exists()
    assert yaml.safe_load(active_file.read_text(encoding="utf-8"))["domain_id"] == "toys"


def test_domain_registry_unknown_switch_raises(temp_config_with_domains: Path) -> None:
    service = DomainRegistryService(config_dir=temp_config_with_domains)
    with pytest.raises(ValueError, match="Unknown domain"):
        service.switch("unknown")


def test_domain_switch_changes_rule_evaluation(
    monkeypatch: Any, temp_config_with_domains: Path
) -> None:
    """Switching from import_machinery (threshold 5) to toys (threshold 10)
    changes whether the same fixture triggers the country_burst rule."""
    import whyfxpg.core.rule_engine as rule_engine_module

    monkeypatch.setattr(
        rule_engine_module, "time_now", lambda: datetime(2026, 7, 15)  # noqa: DTZ001 — 刻意用法(见 TD03)
    )

    service = DomainRegistryService(config_dir=temp_config_with_domains)

    # Build a fixture with 6 events in Germany within 30 days.
    fixture = [
        {
            "event_id": f"e{i}",
            "country": "德国",
            "publish_date": "2026-07-01",
        }
        for i in range(6)
    ]

    # In import_machinery domain, threshold is 5 -> triggered.
    im_profile = service.get("import_machinery")
    im_rules = flatten_rule_packs(im_profile.rule_packs)  # type: ignore[union-attr]
    engine = RuleEngine()
    im_result = engine.sandbox(im_rules[0], fixture)
    assert im_result.outcome.triggered is True  # type: ignore[union-attr]

    # In toys domain, threshold is 10 -> not triggered.
    toys_profile = service.get("toys")
    toys_rules = flatten_rule_packs(toys_profile.rule_packs)  # type: ignore[union-attr]
    toys_result = engine.sandbox(toys_rules[0], fixture)
    assert toys_result.outcome.triggered is False  # type: ignore[union-attr]


# ----------------------------------------------------------------------
# ConfigLoader integration
# ----------------------------------------------------------------------
def test_config_loader_typed_domains(temp_config_with_domains: Path) -> None:
    loader = ConfigLoader(config_dir=str(temp_config_with_domains))
    domains = loader.typed_domains
    assert len(domains) == 2
    ids = {d.domain_id for d in domains}
    assert ids == {"import_machinery", "toys"}

    active = loader.typed_active_domain
    assert active is not None
    assert active.domain_id == "import_machinery"
