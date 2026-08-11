"""Dashboard builder service: assemble templates + data into view models."""

from pathlib import Path

import yaml

from whyfxpg.core.config_loader import DEFAULT_CONFIG_DIR
from whyfxpg.ports.config_store import ConfigStorePort
from whyfxpg.ports.dashboard_data import DashboardDataPort
from whyfxpg.ports.dashboard_export import DashboardExportPort
from whyfxpg.webui.dashboard_models import (
    DashboardContext,
    DashboardTemplate,
    DashboardViewModel,
    DrillDownSpec,
    DrillFilter,
    ExportFormat,
    WidgetLayout,
    WidgetSpec,
    WidgetViewModel,
)
from whyfxpg.webui.widget_registry import WidgetRegistry


class DashboardBuilderService:
    """Build and export dashboards from declarative templates.

    The service is the only component that knows how to turn a template
    into a view model: it validates widget types, executes queries through
    ``DashboardDataPort``, and applies drill-down filters through a fresh
    ``DashboardContext``.
    """

    def __init__(
        self,
        data_port: DashboardDataPort,
        export_port: DashboardExportPort,
        config_store: ConfigStorePort | None = None,
        widget_registry: WidgetRegistry | None = None,
        default_templates_dir: Path | None = None,
    ) -> None:
        self.data_port = data_port
        self.export_port = export_port
        self.config_store = config_store
        self.widget_registry = widget_registry or WidgetRegistry()
        self.default_templates_dir = (
            Path(default_templates_dir)
            if default_templates_dir
            else DEFAULT_CONFIG_DIR / "dashboard_templates"
        )

    # ------------------------------------------------------------------
    # Template discovery / loading
    # ------------------------------------------------------------------
    def list_templates(self) -> list[DashboardTemplate]:
        """Return all available dashboard templates."""
        templates: dict[str, DashboardTemplate] = {}
        if self.config_store:
            for record in self.config_store.list("dashboard_template"):
                try:
                    templates[record.object_id] = _record_to_template(record)
                except Exception:  # noqa: BLE001, S112 — 刻意用法(见 TD03)
                    continue
        for path in sorted(self.default_templates_dir.glob("*.yaml")):
            try:
                template = _template_from_yaml(path)
                if template.dashboard_id not in templates:
                    templates[template.dashboard_id] = template
            except Exception:  # noqa: BLE001, S112 — 刻意用法(见 TD03)
                continue
        return list(templates.values())

    def load_template(self, template_id: str) -> DashboardTemplate:
        """Load a template by id from config store or from disk."""
        if self.config_store:
            record = self.config_store.read("dashboard_template", template_id)
            if record:
                return _record_to_template(record)
        path = self.default_templates_dir / f"{template_id}.yaml"
        if not path.exists():
            raise ValueError(f"Dashboard template not found: {template_id}")
        return _template_from_yaml(path)

    # ------------------------------------------------------------------
    # Build / drill-down / export
    # ------------------------------------------------------------------
    def build(
        self,
        template: DashboardTemplate,
        context: DashboardContext | None = None,
    ) -> DashboardViewModel:
        """Build a view model by loading data for every widget."""
        context = context or DashboardContext()
        widgets: list[WidgetViewModel] = []
        for spec in template.widgets:
            if not self.widget_registry.supports(spec.type):
                raise ValueError(
                    f"Template {template.dashboard_id} uses unsupported widget type: {spec.type}"
                )
            title = spec.title or self.widget_registry.default_title(spec.type)
            data = self.data_port.load(context, spec.query)
            widgets.append(
                WidgetViewModel(
                    widget_id=spec.widget_id,
                    type=spec.type,
                    title=title,
                    query=spec.query,
                    data=data,
                    drill_down=spec.drill_down,
                    layout=spec.layout,
                )
            )
        return DashboardViewModel(
            dashboard_id=template.dashboard_id,
            name=template.name,
            widgets=widgets,
            filters=dict(context.filters),
            template=template,
            context=context,
        )

    def drill_down(
        self,
        view_model: DashboardViewModel,
        filter_: DrillFilter,
    ) -> DashboardViewModel:
        """Return a new dashboard view model with the drill-down filter applied."""
        if view_model.template is None or view_model.context is None:
            raise ValueError("Drill-down requires a view model built from a template")
        widget_ids = {w.widget_id for w in view_model.widgets}
        if filter_.widget_id not in widget_ids:
            raise ValueError(f"Unknown widget id for drill-down: {filter_.widget_id}")
        new_context = view_model.context.with_filter(filter_)
        return self.build(view_model.template, new_context)

    def export(
        self,
        view_model: DashboardViewModel,
        format: ExportFormat,
    ) -> Path:
        """Export a built dashboard to a file."""
        return self.export_port.export(view_model, format)


# ----------------------------------------------------------------------
# Production factory
# ----------------------------------------------------------------------
def build_default_dashboard_service() -> DashboardBuilderService:
    """Return a dashboard builder wired for the current runtime environment."""
    from whyfxpg.adapters.dashboard import (
        DashboardReadModelAdapter,
        ExcelDashboardExportAdapter,
    )
    from whyfxpg.webui.read_model import DashboardReadModel

    return DashboardBuilderService(
        data_port=DashboardReadModelAdapter(DashboardReadModel()),
        export_port=ExcelDashboardExportAdapter(),
    )


# ----------------------------------------------------------------------
# Serialization helpers
# ----------------------------------------------------------------------
def _record_to_template(record) -> DashboardTemplate:
    payload = record.payload or {}
    return DashboardTemplate(
        dashboard_id=record.object_id,
        name=payload.get("name", record.object_id),
        description=payload.get("description", ""),
        widgets=[_widget_from_dict(w) for w in payload.get("widgets", [])],
    )


def _template_from_yaml(path: Path) -> DashboardTemplate:
    with open(path, "r", encoding="utf-8") as f:
        payload = yaml.safe_load(f) or {}
    dashboard_id = payload.get("dashboard_id") or path.stem
    return DashboardTemplate(
        dashboard_id=dashboard_id,
        name=payload.get("name", dashboard_id),
        description=payload.get("description", ""),
        widgets=[_widget_from_dict(w) for w in payload.get("widgets", [])],
    )


def _widget_from_dict(d: dict) -> WidgetSpec:
    layout = None
    raw_layout = d.get("layout")
    if raw_layout:
        layout = WidgetLayout(**raw_layout)
    drill_down = None
    raw_drill = d.get("drill_down")
    if raw_drill:
        drill_down = DrillDownSpec(**raw_drill)
    return WidgetSpec(
        widget_id=d["widget_id"],
        type=d["type"],
        query=d["query"],
        title=d.get("title"),
        params=d.get("params", {}),
        layout=layout,
        drill_down=drill_down,
    )
