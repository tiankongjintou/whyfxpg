# ADR-021: WebUI Screens Depend Only on Services and WebUI Modules

## Status

Accepted (T23)

## Context

The v2 seam-first architecture defines that `webui/screens` (presentation layer) should not couple directly to `core` or `adapters`. Previously three screens still broke this boundary:

- `webui/screens/bigscreen.py` instantiated `DashboardReadModelAdapter` and `ExcelDashboardExportAdapter`.
- `webui/screens/reports.py` imported `ReportGenerator` from `core`.
- `webui/screens/admin/common.py` constructed `FileConfigStoreAdapter` to create the admin service.

These leaks made the screens harder to test, increased the blast radius of adapter refactors, and weakened the architecture's primary seam.

## Decision

1. All `webui/screens/*.py` modules may only import from:
   - `whyfxpg.services.*` (application services and their re-exported domain types)
   - `whyfxpg.webui.*` (presentation models, widgets, helpers, and `app.py` infrastructure)
2. Adapter wiring, `core` orchestration, and port type re-exports are kept inside `services`.
3. Services expose production factory functions (e.g., `build_default_dashboard_service`, `default_configuration_admin_service`, `ReportService`) so screens get a ready-to-use seam without internal wiring knowledge.

## Consequences

- Screens are trivial to unit-test by injecting doubles through the service API.
- Adapter swaps can be done in one place (`services`) instead of every screen.
- The architecture check (`scripts/check_architecture.py`) and the new `test_screens_only_import_services_or_webui` test guard the boundary.

## Related

- T23
- ADR-020
- `whyfxpg/services/dashboard_builder.py`, `whyfxpg/services/report_service.py`, `whyfxpg/services/admin/configuration_admin_service.py`
