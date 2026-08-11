"""Tests for whyfxpg.services.report_service."""

from pathlib import Path
from typing import Any

from whyfxpg.services.report_service import ReportService


class _FakeGenerator:
    """Double for ReportGenerator that avoids IO/DB."""

    def __init__(self, result: dict[str, Any]) -> None:
        self.result = result

    def run(self) -> dict[str, Any]:
        return self.result


def test_list_report_files(tmp_path: Path) -> None:
    service = ReportService(project_root=tmp_path)
    reports_dir = tmp_path / "whyfxpg" / "reports"
    (reports_dir / "word").mkdir(parents=True)
    (reports_dir / "excel").mkdir(parents=True)

    word_file = reports_dir / "word" / "report_20250731.docx"
    word_file.write_text("word")
    excel_file = reports_dir / "excel" / "report_20250731.xlsx"
    excel_file.write_text("excel")

    files = service.list_report_files()
    assert files["word"] == ["report_20250731.docx"]
    assert files["excel"] == ["report_20250731.xlsx"]


def test_list_report_files_returns_empty_when_missing(tmp_path: Path) -> None:
    service = ReportService(project_root=tmp_path)
    files = service.list_report_files()
    assert files == {"word": [], "excel": []}


def test_list_report_files_limits_to_latest_ten(tmp_path: Path) -> None:
    service = ReportService(project_root=tmp_path)
    word_dir = tmp_path / "whyfxpg" / "reports" / "word"
    word_dir.mkdir(parents=True)
    for i in range(12):
        (word_dir / f"report_{i:02d}.docx").write_text("word")

    files = service.list_report_files()
    assert len(files["word"]) == 10
    assert files["word"][0] == "report_11.docx"


def test_generate_report_uses_injected_generator() -> None:
    result = {"status": "success", "message": "generated"}
    service = ReportService(generator=_FakeGenerator(result))  # type: ignore[arg-type]
    assert service.generate_report() == result


def test_generate_report_defaults_to_report_generator() -> None:
    service = ReportService()
    assert service.generator is not None
    assert service._generator is service.generator
