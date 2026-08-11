"""Dashboard export port: abstract export formats behind a seam."""

from abc import ABC, abstractmethod
from pathlib import Path

from whyfxpg.webui.dashboard_models import DashboardViewModel, ExportFormat


class DashboardExportPort(ABC):
    """Export a dashboard view model to a file in a given format."""

    @abstractmethod
    def export(self, view_model: DashboardViewModel, format: ExportFormat) -> Path:
        """Return the path to the exported artifact."""
        ...
