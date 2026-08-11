"""
Tests for the ReportBuilder / ReportRenderer / ReportGenerator seams.

These tests do not depend on the actual Word/Excel libraries beyond the
file-writing smoke tests; all business behavior is asserted through the
in-memory renderer and the LLM service fake.
"""
from pathlib import Path

import pytest

from whyfxpg.adapters.llm import InMemoryLLMAdapter
from whyfxpg.adapters.reports import (
    ExcelReportRenderer,
    InMemoryReportRenderer,
    WordReportRenderer,
)
from whyfxpg.core.report_generator import ReportGenerator
from whyfxpg.ports.report_renderer import ReportRenderer
from whyfxpg.services.llm_service import LLMService
from whyfxpg.services.report_builder import ReportBuilder
from whyfxpg.services.report_model import ReportModel


def test_report_model_is_plain_dataclass():
    model = ReportModel(total_events=0)
    assert not model.has_data
    model.top_events = [{"id": 1}]
    assert model.has_data

    model2 = ReportModel(total_events=5, level_counts={"S": 1})
    assert model2.has_data


def test_report_renderer_port_is_abstract():
    with pytest.raises(TypeError):
        ReportRenderer()


def test_in_memory_report_renderer_records_model():
    renderer = InMemoryReportRenderer()
    model = ReportModel(total_events=3, executive_summary="x")
    path = renderer.render(model, Path("/tmp/report.docx"))
    assert renderer.last_model is model
    assert renderer.last_path == Path("/tmp/report.docx")
    assert path == renderer.last_path
    assert renderer.call_count == 1


def test_report_builder_reads_empty_db(initialized_db):
    service = LLMService(port=InMemoryLLMAdapter(default_response="摘要"))
    builder = ReportBuilder(db_path=initialized_db, llm_service=service)
    model = builder.build()

    assert model.total_events == 0
    assert model.level_counts == {}
    assert model.top_events == []
    assert model.executive_summary == "摘要"
    assert model.report_type == "comprehensive"


def test_report_generator_uses_in_memory_renderers(initialized_db, tmp_path):
    service = LLMService(port=InMemoryLLMAdapter(responses={"摘要": "执行摘要"}))
    word_renderer = InMemoryReportRenderer()
    excel_renderer = InMemoryReportRenderer()

    gen = ReportGenerator(
        db_path=initialized_db,
        output_dir=str(tmp_path),
        llm_service=service,
        word_renderer=word_renderer,
        excel_renderer=excel_renderer,
    )

    result = gen.run()
    assert result["status"] == "success"
    assert word_renderer.call_count == 1
    assert excel_renderer.call_count == 1
    assert "执行摘要" in word_renderer.last_model.executive_summary

    # Word report should be placed under the requested output/word folder.
    assert word_renderer.last_path.parent.name == "word"
    assert excel_renderer.last_path.parent.name == "excel"


def test_word_report_renderer_writes_file(tmp_path):
    model = ReportModel(
        total_events=1,
        level_counts={"S": 1},
        top_products=[
            {
                "product_name": "P",
                "brand": "B",
                "country": "C",
                "latest_rs_level": "S",
                "latest_total_score": 9000,
                "highest_hazard_type": "机械",
            }
        ],
        top_countries=[
            {
                "country": "C",
                "event_count": 1,
                "s_count": 1,
                "m_count": 0,
                "l_count": 0,
                "a_count": 0,
            }
        ],
        pending_alerts=[
            {"severity": "high", "rule_name": "R", "description": "desc"}
        ],
        executive_summary="test",
    )
    renderer = WordReportRenderer()
    path = renderer.render(model, tmp_path / "word" / "report.docx")
    assert path.exists()
    assert path.stat().st_size > 0


def test_excel_report_renderer_writes_file(tmp_path, initialized_db):
    renderer = ExcelReportRenderer(db_path=initialized_db)
    path = renderer.render(ReportModel(), tmp_path / "excel" / "report.xlsx")
    assert path.exists()
    assert path.stat().st_size > 0


def test_report_generator_fetch_data_matches_legacy_shape(initialized_db):
    """fetch_data() preserves the legacy dict shape for external callers."""
    service = LLMService(port=InMemoryLLMAdapter(default_response=""))
    gen = ReportGenerator(db_path=initialized_db, llm_service=service)
    data = gen.fetch_data()
    expected_keys = {
        "total_events",
        "level_counts",
        "top_events",
        "top_products",
        "top_countries",
        "pending_alerts",
    }
    assert set(data.keys()) == expected_keys
