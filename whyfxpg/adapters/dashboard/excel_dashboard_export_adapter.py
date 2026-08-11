"""Excel export adapter for the dashboard seam."""

from pathlib import Path

import pandas as pd

from whyfxpg.ports.dashboard_export import DashboardExportPort
from whyfxpg.webui.dashboard_models import (
    DashboardViewModel,
    ExportFormat,
    WidgetViewModel,
)


class ExcelDashboardExportAdapter(DashboardExportPort):
    """Export a dashboard view model to a multi-sheet Excel workbook."""

    def __init__(self, output_dir: Path | None = None):
        self.output_dir = Path(output_dir) if output_dir else Path.cwd()

    def export(self, view_model: DashboardViewModel, format: ExportFormat) -> Path:
        if format != ExportFormat.EXCEL:
            raise NotImplementedError(f"Excel adapter only supports EXCEL, got {format}")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        path = self.output_dir / f"{view_model.dashboard_id}_{view_model.generated_at.replace(':', '-').replace(' ', '_')}.xlsx"
        metrics: list[WidgetViewModel] = []
        with pd.ExcelWriter(path, engine="openpyxl") as writer:  # type: ignore[call-arg]
            for widget in view_model.widgets:
                if isinstance(widget.data, pd.DataFrame):
                    sheet = _safe_sheet_name(widget.widget_id)
                    widget.data.to_excel(writer, sheet_name=sheet, index=False)
                else:
                    metrics.append(widget)
            if metrics:
                df = pd.DataFrame(
                    [
                        {"widget_id": w.widget_id, "title": w.title, "value": str(w.data)}
                        for w in metrics
                    ]
                )
                df.to_excel(writer, sheet_name="metrics", index=False)
        return path


def _safe_sheet_name(value: str) -> str:
    """Excel sheet names must be <=31 chars and avoid forbidden characters."""
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in value)
    return safe[:31]
