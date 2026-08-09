# ADR-019: Close remaining Phase 2–5 seam leaks

## Status

Accepted (2026-08-04)

## Context

The architecture audit identified several high-leverage leaks:

1. `core/stores.py` had grown to ~750 LOC and mixed alert/risk-event/summary/causal/raw-page persistence.
2. `webui/screens/causal.py` directly imported `init_db`, `CausalKnowledge`, and ran schema creation on render.
3. `adapters/llm/openai_compat_adapter.py` still fell back to the old `core.llm_client` singleton.
4. `core/feedback_learner.py` produced adjustments but the surrounding loop did not persist them through an audited seam or invalidate affected event scores.
5. `adapters/reports/excel_report_adapter.py` queried the database directly instead of rendering from `ReportModel`.

## Decision

### 1. Split `core/stores.py` into a narrow sub-package

- Moved all persistence logic into `whyfxpg/core/stores/`: `unit_of_work.py`, `alert_store.py`, `risk_event_store.py`, `summary_store.py`, `causal_graph_store.py`, `raw_page_store.py`, `archive_store.py` (`AuditLogStore` + `PipelineRunStore`), `rule_store.py`, `source_store.py`, `domain_config_store.py`.
- Kept backward-compatible re-exports via `core/stores/__init__.py` so existing callers did not break.
- Added read-only configuration seams (`RuleStore`, `DomainConfigStore`) that hide the loader details from application services.

### 2. Causal UI leak closure

- Created `whyfxpg/services/causal_service.py` as the UI-facing facade.
- Rewrote `webui/screens/causal.py` to import only from `whyfxpg.services`.
- `CausalService` delegates to `CausalPort`/`CausalKnowledge`; screens no longer create schemas or touch `core.db`.

### 3. LLM singleton removal

- Created `adapters/llm/_provider_config.py` to centralise `.env` provider resolution.
- Rewrote `adapters/llm/openai_compat_adapter.py` to call the configured endpoint directly with `httpx`.
- Deleted `whyfxpg/core/llm_client.py`.
- Updated `conftest.py` to disable live LLM calls by monkeypatching `OpenAICompatAdapter` instead of the old singleton.

### 4. Feedback-learning persistence

- `services/feedback_learning_service.py` wraps `FeedbackLearner`.
- Country/product adjustments are persisted back to the default `risk_model.yaml` through `ConfigurationAdminService` (audited config-object seam).
- Manufacturer adjustments update causal node scores.
- Affected risk-event scores are invalidated and `RiskEvaluationRunner` re-evaluates them.

### 5. Excel renderer decoupled from DB

- `adapters/reports/excel_report_adapter.py` now renders exclusively from `ReportModel` fields.
- `ReportBuilder` remains the only place that queries the database to assemble the model.

### 6. Architecture health check

- Added `scripts/check_architecture.py` to guard the refactored seams:
  - `core/stores.py` and `core/llm_client.py` are gone.
  - `adapters/multimodal.py` exists and does not reference `llm_client`.
  - `services/causal_service.py` exists.
  - `webui/screens/causal.py` imports only from `whyfxpg.services`.
  - `adapters/reports/` does not import `get_db_connection` directly.
  - `adapters/` and `services/` are non-empty.

## Consequences

- The `core/` package still contains other modules; those are being migrated incrementally, but the critical store/llm leaks are closed.
- `webui/screens/reports.py`, `bigscreen.py` and `admin/common.py` still reach into `core`/`adapters` directly. These are tracked as warnings by `check_architecture.py` and are candidates for the next cleanup pass.
- All tests pass (223 passed, 1 skipped) after the changes.

## References

- `whyfxpg/core/stores/`
- `whyfxpg/services/causal_service.py`
- `whyfxpg/adapters/llm/openai_compat_adapter.py`
- `whyfxpg/services/feedback_learning_service.py`
- `whyfxpg/adapters/reports/excel_report_adapter.py`
- `scripts/check_architecture.py`
