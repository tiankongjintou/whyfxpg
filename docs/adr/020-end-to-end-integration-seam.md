# ADR-020: End-to-end v2 integration seam and documentation

## Status

Accepted (2026-08-04)

## Context

Phase 6 v2 refactored WHYfxpg into a seam-first architecture: `ports/`, `adapters/`, `core/`, `services/`, and `webui/`. Each individual seam (Admin CRUD, Rule Engine, Source Monitor, Dashboard v2, Multi-domain, Pipeline & Archive, Close Leaks) has its own tests and ADR, but there is no single place that proves the entire v2 pipeline can be wired together end-to-end without real networks, LLMs, or the production database. There is also no consolidated developer documentation describing the v2 architecture conventions.

## Decision

1. Add a single end-to-end integration test that exercises the full v2 data flow: fake source → raw page → information extraction → risk scoring → alert generation → report rendering → dashboard export → archive.
2. Provide only in-memory / temporary resources in the test so it runs offline and hermetically.
3. Update the project README to reflect the v2 seam-first architecture and update the `docs/v2-development-guide.md` with practical rules for adding ports, adapters, pipeline stages, widgets, migrations, and risk dimensions.

### End-to-end test (`whyfxpg/tests/test_v2_integration.py`)

The test wires together:

- `InMemorySourceAdapter` to simulate a recall notice source.
- `Fetcher` for collection.
- `ExtractEngine` to extract a risk event.
- `RiskEvaluationRunner` to score the event as S-level.
- `AlertEngine` to fire a high-severity alert from the rule pack.
- `ReportGenerator` with `InMemoryReportRenderer` for Word + Excel report artifacts.
- `PipelineOrchestrator` with an `InMemoryArchiveAdapter` to archive all stage outputs and the run manifest.
- `DashboardBuilderService` + `DashboardReadModelAdapter` + `InMemoryDashboardExportAdapter` to build and export a dashboard view model.

### README update

- Updated directory structure to include `ports/`, `adapters/`, `services/`, and the seam-first layer diagram.
- Added “测试与架构守护” section with commands for `scripts/run_tests.py` and `scripts/check_architecture.py`.
- Added “v2 架构：Port + Adapter” and “端到端流水线” sections.
- Updated module table to reference the orchestrator, feedback learning, and seam entries.

### Development guide (`docs/v2-development-guide.md`)

- Defined package boundaries and import rules.
- Specified the standard workflow for adding a new Port, adapter, pipeline stage, dashboard widget, risk dimension, and migration.
- Listed test strategy and pre-commit checklist.

## Consequences

- New contributors can understand the v2 architecture and conventions without reading every ADR.
- The CI-equivalent local command is now `python scripts/run_tests.py && python scripts/check_architecture.py`.
- The integration test is a regression guard: if any seam stops being wired correctly, the test fails first, before the UI or production scripts break.
- The remaining `webui/screens/*.py` leaks (bigscreen, reports, admin/common) remain tracked by `check_architecture.py` warnings and are out of scope for this ticket.

## References

- `whyfxpg/tests/test_v2_integration.py`
- `README.md`
- `docs/v2-development-guide.md`
- `scripts/run_tests.py`
- `scripts/check_architecture.py`
- `whyfxpg/services/pipeline_orchestrator.py`
- `whyfxpg/core/information_pipeline.py`
- `whyfxpg/services/dashboard_builder.py`
