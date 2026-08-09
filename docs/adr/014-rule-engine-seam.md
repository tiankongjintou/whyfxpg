# ADR-014: Rule Engine Seam (T16)

## Status
Accepted — implemented as part of WHYfxpg v2.

## Context
`core/alert_engine.py` implemented every rule type directly: it parsed YAML, built SQL queries, and published alerts. This made rules hard to maintain, test, or sandbox; adding a new rule type required touching the engine and the database layer. The user explicitly asked for a maintainable rule engine.

## Decision
Introduce a dedicated Rule Engine seam with three ports and two adapters:

- `RuleCompilerPort` (`whyfxpg/ports/rule_compiler.py`) — compiles an `AlertRule` into a `CompiledRule` with a `QueryPlan`, and evaluates it against a `RuleContext` to produce a `RuleOutcome`.
- `RuleRepositoryPort` (`whyfxpg/ports/rule_repository.py`) — abstracts rule persistence.
- `RuleEngine` (`whyfxpg/core/rule_engine.py`) — application service exposing `compile`, `evaluate`, `explain`, and `sandbox`.
- Adapters:
  - `SqliteRuleCompilerAdapter` — evaluates rules against the SQLite `AlertStore`.
  - `PandasRuleCompilerAdapter` — evaluates rules against an in-memory fixture (list of dicts or pandas DataFrame), used for unit tests and sandboxing.
  - `FileRuleRepositoryAdapter` — reads and writes `Config/alert_rules.yaml`.
  - `InMemoryRuleRepositoryAdapter` — for tests and ephemeral use.

The canonical rule operations are: `aggregate`, `threshold`, `trend`, `risk_level_change`, and `novel_pattern`. Legacy condition types (`count_by_dimension`, `month_over_month_growth`, `risk_level_ratio_change`) are mapped to these canonical operations.

`AlertEngine` was refactored to delegate compilation and evaluation to `RuleEngine`. It keeps the same public signature (`config_dir`, `db_path`, `publisher_factory`) and remains the pipeline entry point.

## Consequences
- Rules are now first-class objects with a compiler, repository, and explainable outcomes.
- New rule types can be added by extending the compiler adapters without changing `AlertEngine`.
- Sandbox tests can run rules against fixtures without a database.
- `alert_records` gained an `explanation_json` column (migration `005`) so rule outcomes can be persisted for auditing.
- The old rule-specific methods in `AlertEngine` (`rule_risk_level_change`, `rule_count_by_dimension`, etc.) were removed, shrinking the engine.
- Slightly more indirection: `AlertEngine` now depends on `RuleEngine` + adapters instead of `ConfigLoader` + `AlertStore` directly.

## Related Tickets
- T16 Rule Engine seam (closed)
- T15 Admin CRUD seam (dependency)
- T17 Source Monitor seam (next)
- T18 Dashboard v2 seam

## References
- `.scratch/wayfinder/research/03-capabilities-design.md` section (b)
- `whyfxpg/ports/rule_compiler.py`
- `whyfxpg/ports/rule_repository.py`
- `whyfxpg/core/rule_engine.py`
- `whyfxpg/adapters/rules/sqlite_rule_compiler.py`
- `whyfxpg/adapters/rules/pandas_rule_compiler.py`
- `whyfxpg/tests/test_rule_engine_seam.py`
