"""Domain registry service: load and switch between industry domains.

A DomainProfile bundles taxonomy, dimensions, risk model, rule packs, keyword
sets, and country-factor overrides. Switching domains changes the active profile
so downstream modules can adapt their behavior without code changes.
"""

from pathlib import Path
from typing import Any

import yaml

from whyfxpg.config.models import (
    AlertRule,
    KeywordsConfig,
    KeywordSet,
    RiskDimension,
    RiskModelConfig,
    TaxonomyNode,
)
from whyfxpg.core.config_loader import DEFAULT_CONFIG_DIR, load_yaml
from whyfxpg.core.domain_profile import DomainProfile, RulePack, Taxonomy


def _resolve_path(value: Any, config_dir: Path) -> Path | None:
    if not value:
        return None
    path = Path(value)
    if not path.is_absolute():
        path = config_dir / path
    return path


def _load_taxonomy(path: Path | None, domain_id: str) -> Taxonomy:
    if not path or not path.exists():
        return Taxonomy(taxonomy_id=f"{domain_id}_taxonomy", domain_id=domain_id)
    payload = load_yaml(path)
    nodes = [
        TaxonomyNode.from_dict(n)
        for n in (payload.get("nodes") or [])
        if isinstance(n, dict)
    ]
    for n in nodes:
        if not n.taxonomy_id:
            n.taxonomy_id = payload.get("taxonomy_id") or f"{domain_id}_taxonomy"
        if not n.domain_id:
            n.domain_id = domain_id
    return Taxonomy(
        taxonomy_id=payload.get("taxonomy_id") or f"{domain_id}_taxonomy",
        domain_id=domain_id,
        version_id=payload.get("version_id", ""),
        nodes=nodes,
    )


def _load_dimensions(path: Path | None, domain_id: str) -> list[RiskDimension]:
    if not path or not path.exists():
        return []
    payload = load_yaml(path)
    return [
        RiskDimension.from_dict(d)
        for d in (payload.get("dimensions") or [])
        if isinstance(d, dict)
    ]


def _load_risk_model(path: Path | None, domain_id: str) -> RiskModelConfig:
    if not path or not path.exists():
        return RiskModelConfig(domain_id=domain_id)
    payload = load_yaml(path)
    model = RiskModelConfig.from_dict(payload)
    if not model.domain_id:
        model.domain_id = domain_id
    return model


def _load_keywords(path: Path | None, domain_id: str) -> dict[str, KeywordSet]:
    if not path or not path.exists():
        return {}
    payload = load_yaml(path)
    config = KeywordsConfig.from_dict(payload)
    if not config.domain_id:
        config.domain_id = domain_id
    return config.keyword_sets


def _load_rule_packs(rule_packs_dir: Path | None, domain_id: str) -> list[RulePack]:
    if not rule_packs_dir or not rule_packs_dir.exists():
        return []
    packs: list[RulePack] = []
    for path in sorted(rule_packs_dir.glob("*.yaml")):
        try:
            payload = load_yaml(path)
            pack = RulePack.from_dict(payload)
            if not pack.domain_id:
                pack.domain_id = domain_id
            packs.append(pack)
        except Exception:  # noqa: BLE001, S112 — 刻意用法(见 TD03)
            continue
    return packs


def _merge_rules(base: list[AlertRule], child: list[AlertRule]) -> list[AlertRule]:
    result = list(base)
    index_by_id = {r.rule_id: i for i, r in enumerate(result) if r.rule_id}
    for cr in child:
        if cr.rule_id and cr.rule_id in index_by_id:
            existing = result[index_by_id[cr.rule_id]]
            merged_condition = dict(existing.condition)
            merged_condition.update(cr.condition)
            cr.condition = merged_condition
            result[index_by_id[cr.rule_id]] = cr
        else:
            result.append(cr)
            if cr.rule_id:
                index_by_id[cr.rule_id] = len(result) - 1
    return result


def _resolve_rule_pack(
    pack_id: str,
    packs_by_id: dict[str, RulePack],
    visiting: set | None = None,
) -> RulePack:
    visiting = visiting or set()
    if pack_id in visiting:
        raise ValueError(f"Circular rule-pack inheritance detected: {pack_id}")
    if pack_id not in packs_by_id:
        return RulePack(rule_pack_id=pack_id)
    pack = packs_by_id[pack_id]
    visiting.add(pack_id)
    merged_rules: list[AlertRule] = list(pack.rules)
    merged_parameters = dict(pack.parameters)
    for parent_id in pack.inherits:
        parent = _resolve_rule_pack(parent_id, packs_by_id, visiting)
        merged_rules = _merge_rules(parent.rules, merged_rules)
        merged_parameters.update(parent.parameters)
    visiting.discard(pack_id)
    return RulePack(
        rule_pack_id=pack.rule_pack_id,
        domain_id=pack.domain_id,
        version_id=pack.version_id,
        name=pack.name,
        description=pack.description,
        inherits=[],
        rules=merged_rules,
        parameters=merged_parameters,
    )


def flatten_rule_packs(packs: list[RulePack]) -> list[AlertRule]:
    """Resolve inheritance and flatten all rule packs into a single rule list."""
    by_id = {p.rule_pack_id: p for p in packs if p.rule_pack_id}
    resolved = [_resolve_rule_pack(p.rule_pack_id, by_id) for p in packs if p.rule_pack_id]
    result: list[AlertRule] = []
    for rp in resolved:
        result = _merge_rules(result, rp.rules)
    return result


def _load_domain_profile(domain_dir: Path, config_dir: Path) -> DomainProfile:
    domain_file = domain_dir / "domain.yaml"
    payload = load_yaml(domain_file) if domain_file.exists() else {}
    domain_id = str(payload.get("domain_id") or domain_dir.name)

    taxonomy_path = _resolve_path(payload.get("taxonomy"), config_dir)
    dimensions_path = _resolve_path(payload.get("dimensions"), config_dir)
    risk_model_path = _resolve_path(payload.get("risk_model"), config_dir)
    keywords_path = _resolve_path(payload.get("keywords"), config_dir)
    rule_packs_dir = _resolve_path(payload.get("rule_packs_dir"), config_dir)

    return DomainProfile(
        domain_id=domain_id,
        name=str(payload.get("name") or domain_id),
        description=str(payload.get("description", "")),
        taxonomy=_load_taxonomy(taxonomy_path, domain_id),
        dimensions=_load_dimensions(dimensions_path, domain_id),
        risk_model=_load_risk_model(risk_model_path, domain_id),
        rule_packs=_load_rule_packs(rule_packs_dir, domain_id),
        keyword_sets=_load_keywords(keywords_path, domain_id),
        country_factor_overrides={
            str(k): float(v)
            for k, v in (payload.get("country_factor_overrides") or {}).items()
        },
    )


class DomainRegistryService:
    """Load domain profiles from config/domains/<domain>/domain.yaml and
    expose list/get/active/switch operations.
    """

    DEFAULT_DOMAIN_ID = "import_machinery"
    ACTIVE_FILE = "active_domain.yaml"

    def __init__(self, config_dir: Path | None = None):
        self.config_dir = Path(config_dir) if config_dir else DEFAULT_CONFIG_DIR
        self._profiles: dict[str, DomainProfile] = {}
        self._active_domain_id: str | None = None
        self._load()

    def _load(self) -> None:
        domains_dir = self.config_dir / "domains"
        if domains_dir.exists():
            for domain_dir in sorted(domains_dir.iterdir()):
                if not domain_dir.is_dir():
                    continue
                if not (domain_dir / "domain.yaml").exists():
                    continue
                try:
                    profile = _load_domain_profile(domain_dir, self.config_dir)
                    self._profiles[profile.domain_id] = profile
                except Exception:  # noqa: BLE001, S112 — 刻意用法(见 TD03)
                    continue

        # Determine active domain.
        active_id: str | None = None
        active_file = self.config_dir / self.ACTIVE_FILE
        if active_file.exists():
            try:
                active_id = yaml.safe_load(active_file.read_text(encoding="utf-8")).get("domain_id")
            except Exception:  # noqa: BLE001 — 外部调用/配置解析兜底,刻意吞异常
                active_id = None

        if active_id and active_id in self._profiles:
            self._active_domain_id = active_id
        elif self.DEFAULT_DOMAIN_ID in self._profiles:
            self._active_domain_id = self.DEFAULT_DOMAIN_ID
        elif self._profiles:
            self._active_domain_id = next(iter(self._profiles))

        self._update_active_flags()

    def _update_active_flags(self) -> None:
        for pid, profile in self._profiles.items():
            profile.active = pid == self._active_domain_id

    def list(self) -> list[DomainProfile]:
        """Return all loaded domain profiles."""
        return list(self._profiles.values())

    def get(self, domain_id: str) -> DomainProfile | None:
        """Return a specific domain profile."""
        return self._profiles.get(domain_id)

    def active(self) -> DomainProfile | None:
        """Return the currently active domain profile."""
        if self._active_domain_id is None:
            return None
        return self._profiles.get(self._active_domain_id)

    def active_id(self) -> str | None:
        """Return the id of the active domain."""
        return self._active_domain_id

    def switch(self, domain_id: str) -> DomainProfile:
        """Switch the active domain and persist the choice."""
        if domain_id not in self._profiles:
            raise ValueError(f"Unknown domain: {domain_id}")
        self._active_domain_id = domain_id
        active_file = self.config_dir / self.ACTIVE_FILE
        active_file.write_text(
            yaml.safe_dump({"domain_id": domain_id}),
            encoding="utf-8",
        )
        self._update_active_flags()
        return self.active()  # type: ignore[return-value]
