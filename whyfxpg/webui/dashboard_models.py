"""Domain models for the configurable dashboard seam.

All models are plain dataclasses so they can be built and asserted in unit
 tests without importing Streamlit.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class ExportFormat(Enum):
    """Supported dashboard export formats."""

    EXCEL = "excel"
    PDF = "pdf"
    PPT = "ppt"


@dataclass
class DrillFilter:
    """A filter produced by drilling down into a widget."""

    widget_id: str
    dimension: str
    value: Any


@dataclass
class WidgetLayout:
    """Optional placement hint for a dashboard renderer."""

    row: int = 0
    col: int = 0
    col_span: int = 1


@dataclass
class DrillDownSpec:
    """Describes which dimension a widget can drill into."""

    dimension: str
    target_dashboard: str = "default"


@dataclass
class WidgetSpec:
    """Declarative widget definition inside a template."""

    widget_id: str
    type: str
    query: str
    title: str | None = None
    params: dict[str, Any] = field(default_factory=dict)
    layout: WidgetLayout | None = None
    drill_down: DrillDownSpec | None = None


@dataclass
class DashboardTemplate:
    """A reusable dashboard layout composed of widgets."""

    dashboard_id: str
    name: str
    widgets: list[WidgetSpec]
    description: str = ""


@dataclass
class DashboardContext:
    """Runtime filters and options passed to the dashboard builder."""

    filters: dict[str, Any] = field(default_factory=dict)
    db_path: str | None = None
    snapshot_id: str | None = None

    def with_filter(self, filter_: DrillFilter) -> "DashboardContext":
        """Return a new context with the drill-down filter applied."""
        new_filters = dict(self.filters)
        new_filters[filter_.dimension] = filter_.value
        return DashboardContext(
            filters=new_filters,
            db_path=self.db_path,
            snapshot_id=self.snapshot_id,
        )


@dataclass
class WidgetViewModel:
    """A widget that is ready to render."""

    widget_id: str
    type: str
    title: str
    query: str
    data: Any
    drill_down: DrillDownSpec | None = None
    layout: WidgetLayout | None = None


@dataclass
class DashboardViewModel:
    """The fully built dashboard, consumed by the Streamlit renderer."""

    dashboard_id: str
    name: str
    widgets: list[WidgetViewModel]
    filters: dict[str, Any] = field(default_factory=dict)
    generated_at: str = field(
        default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S")  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
    )
    template: DashboardTemplate | None = None
    context: DashboardContext | None = None
