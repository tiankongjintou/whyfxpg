# ADR-017: Multi-domain Seam (T19)

## Status
Accepted — implemented as part of WHYfxpg v2.

## Context
The system was built around a single domain: imported mechanical and electrical products. To make WHYfxpg usable for other customs product domains (chemicals, food, toys, etc.) without forking the codebase, the domain-specific parts—taxonomy, dimensions, risk model, rule packs, keyword sets, country factors—need to be bundled into a switchable profile.

## Decision
Introduce a `DomainProfile` and a `DomainRegistryService` that loads profiles from `Config/domains/<domain_id>/domain.yaml`.

### Domain model (`whyfxpg/core/domain_profile.py`)
A `DomainProfile` is a plain dataclass that owns:
- `taxonomy` (`Taxonomy`) — a list of `TaxonomyNode` objects with parent references;
- `dimensions` (`List[RiskDimension]`) — domain-specific risk dimensions with source fields, weights, and aggregation functions;
- `risk_model` (`RiskModelConfig`) — the scoring model for the domain;
- `rule_packs` (`List[RulePack]`) — sets of alert rules that can inherit from each other and override parameters;
- `keyword_sets` (`Dict[str, KeywordSet]`) — extraction keywords for the domain;
- `country_factor_overrides` (`Dict[str, float]`) — per-domain country adjustments.

`RulePack` supports inheritance: a child pack can reference parent packs and override individual rule `condition` dictionaries. `flatten_rule_packs()` resolves inheritance and returns a single list of `AlertRule`.

### Ports and adapters
- `TaxonomyPort` (`whyfxpg/ports/taxonomy.py`) with `list_children`, `search`, and `map_event`. Adapters:
  - `LocalYamlTaxonomyAdapter` loads a taxonomy from `taxonomy.yaml`;
  - `InMemoryTaxonomyAdapter` is used in unit tests.
- `DimensionPort` (`whyfxpg/ports/dimension.py`) with `list_dimensions`, `weight_of`, and `aggregate`. Adapters:
  - `FixedDimensionsAdapter` loads dimensions from `dimensions.yaml`;
  - `InMemoryDimensionAdapter` is used in unit tests.

### Registry service (`whyfxpg/services/domain_registry.py`)
`DomainRegistryService` scans `Config/domains/*/domain.yaml`, builds a `DomainProfile` for each domain, and exposes `list`, `get`, `active`, and `switch`. The active domain is persisted in `Config/active_domain.yaml`. The default domain is `import_machinery`, so existing behavior is unchanged.

### UI integration
`webui/screens/overview.py` renders a domain selector at the top of the overview page. Selecting a domain calls `DomainRegistryService.switch(domain_id)` and triggers a rerun. The active profile is also available through `ConfigLoader.typed_active_domain` for downstream modules.

### ConfigLoader extension
`ConfigLoader` gained `typed_domains` and `typed_active_domain` properties that delegate to `DomainRegistryService`.

### Default domain configuration
Added `Config/domains/import_machinery/`:
- `domain.yaml` — profile manifest referencing existing top-level `risk_model.yaml` and `keywords.yaml`;
- `taxonomy.yaml` — HS-code-style taxonomy for mechanical/electrical products;
- `dimensions.yaml` — country, hazard_type, severity_level, rs_level, total_score dimensions;
- `rule_packs/base.yaml` and `rule_packs/import_machinery.yaml` — demonstrates inheritance and threshold override.

## Consequences
- New industries can be added by creating a new directory under `Config/domains/` without touching Python code.
- Rule thresholds and dimensions can differ per domain while reusing the same `RuleEngine`, `RiskScorer`, and UI code.
- `TaxonomyPort` and `DimensionPort` make it possible to plug in external standards (HS, IEC, UNSPSC) later by adding adapters.
- The default `import_machinery` domain preserves existing behavior.
- Downstream queries (e.g. `get_summary`, `get_events`) do not yet filter by `domain_id` because the schema currently has no `domain_id` column. That integration is left for T20/T21 when the information pipeline is made explicit.

## Related Tickets
- T19 Multi-domain seam (closed)
- T15 Admin CRUD seam (config store foundation)
- T16 RuleEngine seam (rule pack inheritance builds on AlertRule)
- T18 Dashboard v2 seam (dashboard context can carry `domain_id`)
- T20 Pipeline & Archive seam (next)
- T21 Close Leaks (future: store `domain_id` on events and queries)

## References
- `whyfxpg/core/domain_profile.py`
- `whyfxpg/services/domain_registry.py`
- `whyfxpg/ports/taxonomy.py`
- `whyfxpg/ports/dimension.py`
- `whyfxpg/adapters/taxonomy/__init__.py`
- `whyfxpg/adapters/dimensions/__init__.py`
- `whyfxpg/core/config_loader.py`
- `whyfxpg/webui/screens/overview.py`
- `Config/domains/import_machinery/`
