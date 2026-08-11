from typing import ClassVar

"""Widget registry for the configurable dashboard seam."""

from dataclasses import dataclass


@dataclass
class WidgetType:
    """Registered widget metadata."""

    name: str
    display_name: str
    default_title: str = ""


class WidgetRegistry:
    """Catalog of supported dashboard widget types."""

    _BUILTIN: ClassVar[list[WidgetType]] = [
        WidgetType("metric", "Metric / KPI", "指标"),
        WidgetType("pie", "Pie Chart", "饼图"),
        WidgetType("bar", "Bar Chart", "柱状图"),
        WidgetType("line", "Line Chart", "趋势图"),
        WidgetType("table", "Table", "明细表"),
        WidgetType("heatmap", "Heatmap", "热力图"),
        WidgetType("event_stream", "Event Stream", "事件流"),
    ]

    def __init__(self) -> None:
        self._types: dict[str, WidgetType] = {
            t.name: t for t in self._BUILTIN
        }

    def register(self, widget_type: WidgetType) -> None:
        """Register a new widget type."""
        self._types[widget_type.name] = widget_type

    def supports(self, type_name: str) -> bool:
        """Return True if the widget type is supported."""
        return type_name in self._types

    def list_types(self) -> list[str]:
        """Return all registered widget type names."""
        return list(self._types.keys())

    def default_title(self, type_name: str) -> str:
        """Return the default title for a widget type."""
        if type_name not in self._types:
            raise ValueError(f"Unsupported widget type: {type_name}")
        return self._types[type_name].default_title

    def metadata(self, type_name: str) -> WidgetType:
        """Return full metadata for a widget type."""
        if type_name not in self._types:
            raise ValueError(f"Unsupported widget type: {type_name}")
        return self._types[type_name]
