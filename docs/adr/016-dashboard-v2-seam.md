# ADR-016: Dashboard v2 Seam (T18)

## Status
Accepted — implemented as part of WHYfxpg v2.

## Context
The existing "风险态势大屏" page was a single, hand-coded Streamlit view built on top of `BigScreenPresenter`. Every chart, metric, and table was hard-wired, which made it impossible for different domains or user roles to customise the layout, add widgets, or export the current view without editing Python code. The user asked for a configurable dashboard seam that could still reproduce the current layout as a default template.

## Decision
Introduce a declarative dashboard seam composed of domain models, two ports, adapters, a widget registry, and a builder service.

### Domain models (`whyfxpg/webui/dashboard_models.py`)
Plain dataclasses with no Streamlit dependency:
- `DashboardTemplate` / `WidgetSpec` / `WidgetLayout` / `DrillDownSpec`
- `DashboardContext` with `filters` and `with_filter()`
- `DashboardViewModel` / `WidgetViewModel`
- `DrillFilter` and `ExportFormat` enum

### Ports
- `DashboardDataPort` (`whyfxpg/ports/dashboard_data.py`) — loads data for a widget query given a context.
- `DashboardExportPort` (`whyfxpg/ports/dashboard_export.py`) — exports a built view model to a file.

### Adapters (`whyfxpg/adapters/dashboard/`)
- `DashboardReadModelAdapter` — wraps the existing `DashboardReadModel` and exposes a small query language (`summary.total_events`, `summary.level_dist.S`, `trend.days=30`, `country_summary.limit=20`, etc.). It applies context filters to returned DataFrames.
- `InMemoryDashboardDataAdapter` — dictionary-backed for unit tests.
- `ExcelDashboardExportAdapter` — writes one sheet per DataFrame widget plus a `metrics` sheet for scalar widgets.
- `InMemoryDashboardExportAdapter` — records export calls for tests.

### Widget registry (`whyfxpg/webui/widget_registry.py`)
A thin catalog of supported widget types (`metric`, `line`, `bar`, `pie`, `table`, `heatmap`, `event_stream`) with metadata and default titles. Custom types can be registered at runtime.

### Builder service (`whyfxpg/services/dashboard_builder.py`)
`DashboardBuilderService` wires the data port, export port, optional `ConfigStorePort`, and `WidgetRegistry`. It can:
- list / load dashboard templates (from `ConfigStorePort` or from `Config/dashboard_templates/*.yaml`);
- build a `DashboardViewModel` from a template and context;
- apply drill-down filters via `drill_down(view_model, filter)`;
- export a view model through the export port.

### Default template (`Config/dashboard_templates/default.yaml`)
The shipped default template reproduces the original big-screen layout using widgets with row/column layout metadata. It is loaded from disk as a static asset so the app works out of the box, while user-defined templates can be stored through `ConfigStorePort` (which was extended to support `dashboard_template` objects in `dashboard_templates.yaml`).

### UI (`whyfxpg/webui/screens/bigscreen.py`)
The screen now wires `DashboardReadModelAdapter` + `ExcelDashboardExportAdapter` into `DashboardBuilderService`, loads the default template, builds the view model, and renders each widget by type. Table widgets that declare a `drill_down` dimension expose a selector that updates `st.session_state["bigscreen_filters"]` and triggers a rebuild, filtering all DataFrame-backed widgets that share the dimension column.

### ConfigStore extension
`FileConfigStoreAdapter` now supports `object_type="dashboard_template"` with list key `dashboards` and id field `dashboard_id`, so admin pages can persist custom templates alongside sources, rules, and taxonomies.

## Consequences
- The big screen is now data-driven: new layouts or widgets can be added by editing YAML or storing a template through the admin seam, without touching rendering code.
- Drill-down filters are applied consistently across all DataFrame-backed widgets that share the drilled dimension.
- Excel export is available for any built dashboard.
- The existing presenter-based big screen was replaced; its test (`test_bigscreen_presenter.py`) remains valid because the presenter itself is unchanged, and the new screen is covered by `test_dashboard_v2_seam.py`.
- Future multi-domain support can provide per-domain templates simply by loading a different `dashboard_id`.
- KPI widgets (`metric`) do not yet recompute when context filters are applied: they continue to show global summary values. This is a documented limitation for this iteration; drill-down mainly affects tables and charts.

## Related Tickets
- T18 Dashboard v2 seam (closed)
- T15 Admin CRUD seam (ConfigStorePort extended for dashboard templates)
- T17 SourceMonitor seam (data source for monitoring widgets)
- T16 RuleEngine seam (alert data for dashboard widgets)
- T21 Close Leaks (future: remove remaining direct DB access in UI code)

## References
- `whyfxpg/webui/dashboard_models.py`
- `whyfxpg/ports/dashboard_data.py`
- `whyfxpg/ports/dashboard_export.py`
- `whyfxpg/adapters/dashboard/`
- `whyfxpg/services/dashboard_builder.py`
- `whyfxpg/webui/widget_registry.py`
- `whyfxpg/webui/screens/bigscreen.py`
- `Config/dashboard_templates/default.yaml`
- `whyfxpg/adapters/config/file_config_store.py` (dashboard_template support)
