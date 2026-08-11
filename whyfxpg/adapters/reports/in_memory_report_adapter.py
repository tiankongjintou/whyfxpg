"""
In-memory report renderer: records the rendered model and path, useful for tests.
"""
from pathlib import Path

from whyfxpg.ports.report_renderer import ReportRenderer
from whyfxpg.services.report_model import ReportModel


class InMemoryReportRenderer(ReportRenderer):
    """Test double that records render calls without writing files."""

    def __init__(self) -> None:
        self.last_model: ReportModel | None = None
        self.last_path: Path | None = None
        self.call_count: int = 0

    def render(self, report_model: ReportModel, output_path: Path) -> Path:
        self.last_model = report_model
        self.last_path = Path(output_path)
        self.call_count += 1
        return self.last_path
