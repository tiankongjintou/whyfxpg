"""Multi-domain domain profile models.

A DomainProfile bundles everything that differs between industries:
taxonomy, dimensions, risk model, rule packs, keyword sets, and country
factor overrides. Switching domains is a runtime configuration change.
"""

from dataclasses import dataclass, field
from typing import Any

from whyfxpg.config.models import (
    AlertRule,
    KeywordSet,
    RiskDimension,
    RiskModelConfig,
    TaxonomyNode,
)


@dataclass
class Taxonomy:
    """A taxonomy as a flat list of nodes with parent references."""

    taxonomy_id: str = ""
    domain_id: str = ""
    version_id: str = ""
    nodes: list[TaxonomyNode] = field(default_factory=list)


@dataclass
class RulePack:
    """A pack of rules that can inherit from base packs and override parameters."""

    rule_pack_id: str = ""
    domain_id: str = ""
    version_id: str = ""
    name: str = ""
    description: str = ""
    inherits: list[str] = field(default_factory=list)
    rules: list[AlertRule] = field(default_factory=list)
    parameters: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, d: Any) -> "RulePack":
        if not isinstance(d, dict):
            d = {}
        return cls(
            rule_pack_id=str(d.get("rule_pack_id", "")),
            domain_id=str(d.get("domain_id", "default")),
            version_id=str(d.get("version_id", "")),
            name=str(d.get("name", "")),
            description=str(d.get("description", "")),
            inherits=[str(x) for x in d.get("inherits", []) if x],
            rules=[AlertRule.from_dict(r) for r in (d.get("rules") or []) if isinstance(r, dict)],
            parameters=d.get("parameters") or {},
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_pack_id": self.rule_pack_id,
            "domain_id": self.domain_id,
            "version_id": self.version_id,
            "name": self.name,
            "description": self.description,
            "inherits": self.inherits,
            "rules": [r.__dict__ for r in self.rules],
            "parameters": self.parameters,
        }


@dataclass
class DomainProfile:
    """Full configuration for a single risk-assessment domain."""

    domain_id: str = ""
    name: str = ""
    description: str = ""
    taxonomy: Taxonomy = field(default_factory=Taxonomy)
    dimensions: list[RiskDimension] = field(default_factory=list)
    risk_model: RiskModelConfig = field(default_factory=RiskModelConfig)
    rule_packs: list[RulePack] = field(default_factory=list)
    keyword_sets: dict[str, KeywordSet] = field(default_factory=dict)
    country_factor_overrides: dict[str, float] = field(default_factory=dict)
    active: bool = False
