"""
Report renderer port: abstract boundary for rendering a ReportModel to a file.
"""
from abc import ABC, abstractmethod
from pathlib import Path

from whyfxpg.services.report_model import ReportModel


class ReportRenderer(ABC):
    """Render a ReportModel to a target path."""

    @abstractmethod
    def render(self, report_model: ReportModel, output_path: Path) -> Path:
        """Render and return the written path."""
        raise NotImplementedError

    def __repr__(self) -> str:  # pragma: no cover
        return f"{self.__class__.__name__}()"
