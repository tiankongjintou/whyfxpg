"""Report service: UI-facing seam for report listing and generation."""

from pathlib import Path

from whyfxpg.core.report_generator import ReportGenerator


class ReportService:
    """List generated reports and trigger new report generation.

    This service isolates the Streamlit pages from ``ReportGenerator``
    internals and gives tests a stable seam to inject doubles.
    """

    def __init__(
        self,
        project_root: Path | None = None,
        generator: ReportGenerator | None = None,
    ) -> None:
        if project_root is None:
            # whyfxpg/services/report_service.py -> whyfxpg -> WHYfxpg
            self.project_root = Path(__file__).resolve().parents[2]
        else:
            self.project_root = Path(project_root)
        self._generator = generator

    @property
    def reports_dir(self) -> Path:
        return self.project_root / "whyfxpg" / "reports"

    @property
    def generator(self) -> ReportGenerator:
        if self._generator is None:
            self._generator = ReportGenerator()
        return self._generator

    def list_report_files(self) -> dict[str, list[str]]:
        """Return the last 10 word and excel report filenames."""
        result: dict[str, list[str]] = {"word": [], "excel": []}
        for fmt, subdir in (("word", "word"), ("excel", "excel")):
            folder = self.reports_dir / subdir
            if folder.exists():
                ext = "docx" if fmt == "word" else "xlsx"
                files = sorted(
                    [f.name for f in folder.glob(f"*.{ext}")],
                    reverse=True,
                )
                result[fmt] = files[:10]
        return result

    def generate_report(self) -> dict[str, str]:
        """Generate a fresh Word and Excel report pair."""
        return self.generator.run()
