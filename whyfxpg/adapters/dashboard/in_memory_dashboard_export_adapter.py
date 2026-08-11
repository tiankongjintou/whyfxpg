"""In-memory export adapter for unit tests."""

from pathlib import Path

from whyfxpg.ports.dashboard_export import DashboardExportPort
from whyfxpg.webui.dashboard_models import DashboardViewModel, ExportFormat


class InMemoryDashboardExportAdapter(DashboardExportPort):
    """Records export calls and returns a fake path."""

    def __init__(self) -> None:
        self.exports: list[tuple[str, ExportFormat]] = []
        self.last_path: Path = Path("memory")

    def export(self, view_model: DashboardViewModel, format: ExportFormat) -> Path:
        self.exports.append((view_model.dashboard_id, format))
        return self.last_path
