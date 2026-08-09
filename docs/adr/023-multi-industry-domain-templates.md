# ADR-023: Multi-industry domain templates

## Status

Accepted

## Context

WHYfxpg was originally built for customs import machinery (HS chapters 84/85). The `DomainProfile` + `DomainRegistryService` seam added in T19 proved that the domain can be swapped via YAML templates, but only one production domain (`import_machinery`) existed. To validate the seam and prepare the product for additional industries, we needed templates for chemical, food, toy, and automotive imports.

## Decision

Add four new domain templates under `Config/domains/`:

- `import_chemicals` — HS 28/29/32/35/38 related chemicals; extra dimensions `cas_number`, `regulatory_scope`.
- `import_food` — HS 1-24 food and agricultural products; extra dimensions `product_category`, `ingredient_risk`.
- `import_toys` — HS 95 toys and childcare articles; extra dimensions `age_group`, `material_type`.
- `import_automotive` — HS 87/88 vehicles and parts; extra dimensions `component_category`, `recall_scope`.

Each template follows the same structure as `import_machinery`:

```
domain.yaml
taxonomy.yaml
dimensions.yaml
rule_packs/base.yaml
rule_packs/<domain>.yaml
```

The `DomainRegistryService` auto-discovers all directories containing `domain.yaml`, so no code changes are required to load the new domains. The default active domain remains `import_machinery`.

## Consequences

- New domains can be switched via `DomainRegistryService.switch(domain_id)` without redeploying.
- Domain-specific dimensions are available for dashboards and rule evaluation without changing core logic.
- Rule packs inherit `base` and add domain-specific rules (e.g., `banned_substance_alert`, `choking_hazard`).
- The `import_machinery` domain remains the active default, keeping the running UI stable.
- No new code dependencies; only YAML files and tests added.

## Related tickets

- T19 — Multi-domain seam
- T28 — Add new industry domain templates
