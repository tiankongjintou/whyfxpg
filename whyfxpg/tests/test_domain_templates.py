"""T28: New industry domain templates (chemical, food, toy, automotive)."""

import shutil
from pathlib import Path

import pytest

from whyfxpg.services.domain_registry import (
    DomainRegistryService,
    flatten_rule_packs,
)


@pytest.fixture
def multi_domain_config(tmp_path: Path) -> Path:
    """Copy the default and new domain templates into a temporary config dir."""
    project_root = Path(__file__).resolve().parents[2]
    src = project_root / "Config" / "domains"
    dst = tmp_path / "domains"
    for domain_id in [
        "import_machinery",
        "import_chemicals",
        "import_food",
        "import_toys",
        "import_automotive",
    ]:
        shutil.copytree(src / domain_id, dst / domain_id)
    return tmp_path


NEW_DOMAIN_IDS = [
    "import_chemicals",
    "import_food",
    "import_toys",
    "import_automotive",
]


def test_registry_loads_all_new_domains(multi_domain_config: Path) -> None:
    reg = DomainRegistryService(multi_domain_config)
    loaded_ids = {p.domain_id for p in reg.list()}
    assert "import_machinery" in loaded_ids
    for domain_id in NEW_DOMAIN_IDS:
        assert domain_id in loaded_ids
        profile = reg.get(domain_id)
        assert profile is not None
        assert profile.name
        assert len(profile.taxonomy.nodes) >= 4
        assert len(profile.dimensions) >= 7
        assert len(profile.rule_packs) == 2


def test_new_domain_taxonomies_have_domain_specific_nodes(
    multi_domain_config: Path,
) -> None:
    reg = DomainRegistryService(multi_domain_config)
    chemical = reg.get("import_chemicals")
    assert chemical is not None
    node_ids = {n.node_id for n in chemical.taxonomy.nodes}
    assert {"root", "28", "29", "32", "35", "38"} <= node_ids

    food = reg.get("import_food")
    assert food is not None
    node_ids = {n.node_id for n in food.taxonomy.nodes}
    assert {"animal", "plant", "processed", "dairy", "seafood"} <= node_ids


def test_new_domain_dimensions_include_domain_specific_fields(
    multi_domain_config: Path,
) -> None:
    reg = DomainRegistryService(multi_domain_config)
    dim_ids = {d.dimension_id for d in reg.get("import_chemicals").dimensions}  # type: ignore[union-attr]
    assert "cas_number" in dim_ids
    assert "regulatory_scope" in dim_ids

    dim_ids = {d.dimension_id for d in reg.get("import_toys").dimensions}  # type: ignore[union-attr]
    assert "age_group" in dim_ids
    assert "material_type" in dim_ids

    dim_ids = {d.dimension_id for d in reg.get("import_automotive").dimensions}  # type: ignore[union-attr]
    assert "component_category" in dim_ids
    assert "recall_scope" in dim_ids


def test_new_domain_rule_packs_merge_base_and_domain_rules(
    multi_domain_config: Path,
) -> None:
    reg = DomainRegistryService(multi_domain_config)
    for domain_id in NEW_DOMAIN_IDS:
        profile = reg.get(domain_id)
        rules = flatten_rule_packs(profile.rule_packs)  # type: ignore[union-attr]
        rule_ids = {r.rule_id for r in rules}
        assert "country_burst" in rule_ids
        assert len(rules) > 1

    chemical = reg.get("import_chemicals")
    rules = flatten_rule_packs(chemical.rule_packs)  # type: ignore[union-attr]
    assert any(r.rule_id == "banned_substance_alert" for r in rules)

    food = reg.get("import_food")
    rules = flatten_rule_packs(food.rule_packs)  # type: ignore[union-attr]
    assert any(r.rule_id == "allergen_label_risk" for r in rules)

    toys = reg.get("import_toys")
    rules = flatten_rule_packs(toys.rule_packs)  # type: ignore[union-attr]
    assert any(r.rule_id == "choking_hazard" for r in rules)

    automotive = reg.get("import_automotive")
    rules = flatten_rule_packs(automotive.rule_packs)  # type: ignore[union-attr]
    assert any(r.rule_id == "brake_system_alert" for r in rules)


def test_switching_to_new_domain(multi_domain_config: Path) -> None:
    reg = DomainRegistryService(multi_domain_config)
    assert reg.active_id() == "import_machinery"
    switched = reg.switch("import_food")
    assert switched.domain_id == "import_food"
    assert switched.active
    assert reg.active_id() == "import_food"
    assert reg.active().domain_id == "import_food"  # type: ignore[union-attr]

    # Switch back to default.
    reg.switch("import_machinery")
    assert reg.active_id() == "import_machinery"


def test_default_domain_remains_machinery(multi_domain_config: Path) -> None:
    reg = DomainRegistryService(multi_domain_config)
    assert reg.active_id() == "import_machinery"
    assert reg.active().domain_id == "import_machinery"  # type: ignore[union-attr]
