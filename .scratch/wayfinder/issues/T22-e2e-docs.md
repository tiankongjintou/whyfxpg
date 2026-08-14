# T22: End-to-End v2 Integration Tests + Documentation

**Status:** ✅ completed
**Phase:** Phase 2 maintenance
**Priority:** medium
**Created:** 2026-08-14
**ADR:** ADR-020

## Problem Statement

WHYfxpg v2 seams exist but lack:
1. End-to-end integration tests that verify all seams work together
2. Domain-switch tests that verify multi-domain isolation
3. Documentation tying seams to acceptance criteria

## Acceptance Criteria

- [x] **AC-1**: `test_v2_e2e_full_pipeline` — full pipeline config→fetch→extract→score→evaluate→alert→archive→lineage, 3+ stages, 0 real network calls
- [x] **AC-2**: `test_v2_e2e_rule_sandbox` — rule sandbox isolation, original rule set unaffected
- [x] **AC-3**: `test_v2_e2e_alert_lineage` — alert triggering + lineage trace
- [x] **AC-4**: Domain switch tests (9 tests) covering taxonomy/dimensions/rule pack switching
- [x] **AC-5**: ADR-020 end-to-end integration seam documented

## Deliverables

| File | Description | Status |
|------|-------------|--------|
| `whyfxpg/tests/test_v2_e2e.py` | 3 e2e integration tests | ✅ |
| `whyfxpg/tests/test_v2_domain_switch.py` | 9 domain switch tests | ✅ |
| `docs/adr/020-end-to-end-integration-seam.md` | ADR-020 | ✅ (prior session) |

## Test Results

```
test_v2_e2e_full_pipeline         PASSED
test_v2_e2e_rule_sandbox          PASSED
test_v2_e2e_alert_lineage         PASSED
test_domain_switch_changes_taxonomy PASSED
test_taxonomy_nodes_are_domain_scoped PASSED
test_domain_switch_changes_dimensions PASSED
test_dimension_weights_are_domain_scoped PASSED
test_domain_switch_changes_rule_packs PASSED
test_rule_packs_have_correct_domain_id PASSED
test_default_domain_unchanged_after_switch PASSED
test_inactive_profile_not_corrupted PASSED
test_switch_twice_to_same_domain_is_idempotent PASSED

12/12 passed
```

## Key Design Decisions

- All tests use InMemory adapters (no real network, no LLM calls)
- `RiskEventStore.update_scores()` used for mock scoring (no `.get()` method)
- Domain profiles read from YAML files in `config/domains/`
- Sandbox isolation verified by checking original rule set unchanged after switch
