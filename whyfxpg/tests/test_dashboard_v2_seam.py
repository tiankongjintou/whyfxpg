"""Tests for the Dashboard v2 seam (T18).

Covers domain models, WidgetRegistry, DashboardDataPort adapters,
DashboardBuilderService, and export ports. All tests use in-memory fixtures
or temporary SQLite databases so they do not depend on production whyfxpg.db.
"""

from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
import yaml

from whyfxpg.adapters.config.in_memory_config_store import InMemoryConfigStoreAdapter
from whyfxpg.adapters.dashboard import (
    DashboardReadModelAdapter,
    ExcelDashboardExportAdapter,
    InMemoryDashboardDataAdapter,
    InMemoryDashboardExportAdapter,
)
from whyfxpg.core.db import get_db_connection
from whyfxpg.ports.config_store import ConfigRecord
from whyfxpg.services.dashboard_builder import DashboardBuilderService
from whyfxpg.webui.dashboard_models import (
    DashboardContext,
    DashboardTemplate,
    DashboardViewModel,
    DrillDownSpec,
    DrillFilter,
    ExportFormat,
    WidgetSpec,
    WidgetViewModel,
)
from whyfxpg.webui.widget_registry import WidgetRegistry, WidgetType


# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------
def _event_defaults() -> dict[str, Any]:
    now = datetime.now().isoformat()  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
    return {
        "page_id": "p1",
        "source_id": "test_api",
        "source_url": "https://example.com/1",
        "title": "title",
        "product_name": "产品A",
        "brand": "品牌A",
        "model": "M1",
        "hs_code": "1234",
        "product_category": "普通机电",
        "manufacturer": "MfrA",
        "hazard_desc": "desc",
        "severity_level": "严重",
        "probability_level": "可能",
        "country_factor": 1.0,
        "product_factor": 1.0,
        "history_factor": 1.0,
        "evidence_factor": 1.0,
        "causal_factor": 1.0,
        "standards": "",
        "original_text": "text",
        "extracted_at": now,
        "evaluated_at": now,
        "config_version": "1.0",
        "model_version": "1.0",
        "extraction_confidence": 0.5,
        "review_status": "auto",
    }


def _insert_event(
    conn: Any,
    event_id: str,
    publish_date: str,
    country: str,
    hazard_type: str,
    ss_score: int,
    total_score: int,
    rs_level: str,
) -> None:
    defaults = _event_defaults()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO risk_events (
            event_id, page_id, source_id, source_url, publish_date, title,
            product_name, brand, model, hs_code, product_category, country,
            manufacturer, hazard_type, hazard_desc, severity_level, ss_score,
            probability_level, ps_score, country_factor, product_factor,
            history_factor, evidence_factor, causal_factor, total_score, rs_level,
            standards, original_text, extracted_at, evaluated_at, config_version,
            model_version, extraction_confidence, review_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_id,
            defaults["page_id"],
            defaults["source_id"],
            defaults["source_url"],
            publish_date,
            defaults["title"],
            defaults["product_name"],
            defaults["brand"],
            defaults["model"],
            defaults["hs_code"],
            defaults["product_category"],
            country,
            defaults["manufacturer"],
            hazard_type,
            defaults["hazard_desc"],
            defaults["severity_level"],
            ss_score,
            defaults["probability_level"],
            ss_score,
            defaults["country_factor"],
            defaults["product_factor"],
            defaults["history_factor"],
            defaults["evidence_factor"],
            defaults["causal_factor"],
            total_score,
            rs_level,
            defaults["standards"],
            defaults["original_text"],
            defaults["extracted_at"],
            defaults["evaluated_at"],
            defaults["config_version"],
            defaults["model_version"],
            defaults["extraction_confidence"],
            defaults["review_status"],
        ),
    )
    conn.commit()


def _insert_country_summary(
    conn: Any, country: str, event_count: int, s_count: int = 0, m_count: int = 0
) -> None:
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT OR REPLACE INTO country_risk_summary
        (country, event_count, s_count, m_count, l_count, a_count, latest_event_date, updated_at)
        VALUES (?, ?, ?, ?, 0, 0, ?, ?)
        """,
        (country, event_count, s_count, m_count, "2026-01-01", datetime.now().isoformat()),  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
    )
    conn.commit()


def _insert_alert(conn: Any, alert_id: str, status: str = "pending") -> None:
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO alert_records
        (alert_id, rule_id, rule_name, triggered_at, object_type, object_value, severity, triggered_value, description, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            alert_id,
            "r1",
            "rule",
            datetime.now().isoformat(),  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
            "event",
            "e1",
            "high",
            "1",
            "desc",
            status,
        ),
    )
    conn.commit()


@pytest.fixture
def sample_template() -> DashboardTemplate:
    return DashboardTemplate(
        dashboard_id="test",
        name="Test Dashboard",
        widgets=[
            WidgetSpec(
                widget_id="w1",
                type="metric",
                query="summary.total_events",
                title="Total",
            ),
            WidgetSpec(
                widget_id="w2",
                type="table",
                query="events",
                title="Events",
                drill_down=DrillDownSpec(dimension="country"),
            ),
        ],
    )


# ----------------------------------------------------------------------
# Domain models
# ----------------------------------------------------------------------
def test_dashboard_context_with_filter() -> None:
    ctx = DashboardContext(filters={"country": "德国"})
    new_ctx = ctx.with_filter(DrillFilter(widget_id="w2", dimension="country", value="美国"))
    assert new_ctx.filters == {"country": "美国"}

    add_ctx = ctx.with_filter(DrillFilter(widget_id="w2", dimension="hazard_type", value="电气危险"))
    assert add_ctx.filters == {"country": "德国", "hazard_type": "电气危险"}


# ----------------------------------------------------------------------
# Widget registry
# ----------------------------------------------------------------------
def test_widget_registry_builtin_types() -> None:
    registry = WidgetRegistry()
    assert registry.supports("metric")
    assert registry.supports("table")
    assert not registry.supports("unknown")
    assert registry.default_title("metric") == "指标"


def test_widget_registry_register_custom_type() -> None:
    registry = WidgetRegistry()
    registry.register(WidgetType("funnel", "Funnel Chart", "漏斗图"))
    assert registry.supports("funnel")
    assert registry.default_title("funnel") == "漏斗图"


# ----------------------------------------------------------------------
# In-memory data adapter
# ----------------------------------------------------------------------
def test_in_memory_data_adapter_load_and_filter() -> None:
    df = pd.DataFrame({"country": ["德国", "美国"], "score": [90, 70]})
    adapter = InMemoryDashboardDataAdapter({"events": df, "scalar": 42})

    assert adapter.load(DashboardContext(), "scalar") == 42
    loaded = adapter.load(DashboardContext(), "events")
    assert isinstance(loaded, pd.DataFrame)
    assert len(loaded) == 2

    filtered = adapter.load(DashboardContext(filters={"country": "德国"}), "events")
    assert len(filtered) == 1
    assert filtered.iloc[0]["country"] == "德国"


# ----------------------------------------------------------------------
# Read-model data adapter
# ----------------------------------------------------------------------
def test_dashboard_read_model_adapter_summary(initialized_db: str) -> None:
    conn = get_db_connection(initialized_db)
    try:
        _insert_event(conn, "e1", "2026-01-01", "德国", "电气危险", 95, 9000, "S")
        _insert_event(conn, "e2", "2026-01-02", "美国", "机械危险", 60, 3000, "M")
        _insert_country_summary(conn, "德国", 2, s_count=1, m_count=0)
        _insert_country_summary(conn, "美国", 1, s_count=0, m_count=1)
        _insert_alert(conn, "a1")
        _insert_alert(conn, "a2", status="confirmed")
    finally:
        conn.close()

    adapter = DashboardReadModelAdapter(initialized_db)
    assert adapter.load(DashboardContext(), "summary.total_events") == 2
    assert adapter.load(DashboardContext(), "summary.level_dist.S") == 1
    assert adapter.load(DashboardContext(), "summary.level_dist.M") == 1
    assert adapter.load(DashboardContext(), "summary.pending_alerts") == 1
    assert adapter.load(DashboardContext(), "summary.country_count") == 2

    level_dist = adapter.load(DashboardContext(), "summary.level_dist")
    assert isinstance(level_dist, dict)
    assert level_dist.get("S") == 1

    hazard_df = adapter.load(DashboardContext(), "hazard_distribution.limit=10")
    assert isinstance(hazard_df, pd.DataFrame)
    assert len(hazard_df) == 2

    country_df = adapter.load(DashboardContext(), "country_summary.limit=20")
    assert isinstance(country_df, pd.DataFrame)
    assert len(country_df) == 2

    recent_df = adapter.load(DashboardContext(), "recent_high_risk.limit=15")
    assert isinstance(recent_df, pd.DataFrame)
    assert len(recent_df) == 2

    alerts_df = adapter.load(DashboardContext(), "alerts.limit=10")
    assert isinstance(alerts_df, pd.DataFrame)
    assert len(alerts_df) == 2

    trend_df = adapter.load(DashboardContext(), "trend.days=30")
    assert isinstance(trend_df, pd.DataFrame)


def test_dashboard_read_model_adapter_filters_dataframe(initialized_db: str) -> None:
    conn = get_db_connection(initialized_db)
    try:
        _insert_event(conn, "e1", "2026-01-01", "德国", "电气危险", 95, 9000, "S")
        _insert_event(conn, "e2", "2026-01-02", "美国", "机械危险", 60, 3000, "M")
        _insert_country_summary(conn, "德国", 1, s_count=1)
        _insert_country_summary(conn, "美国", 1, m_count=1)
    finally:
        conn.close()

    adapter = DashboardReadModelAdapter(initialized_db)
    ctx = DashboardContext(filters={"country": "德国"})
    country_df = adapter.load(ctx, "country_summary.limit=20")
    assert len(country_df) == 1
    assert country_df.iloc[0]["country"] == "德国"


# ----------------------------------------------------------------------
# Dashboard builder service
# ----------------------------------------------------------------------
def test_builder_service_load_default_template(tmp_path: Path) -> None:
    data_port = InMemoryDashboardDataAdapter({})
    export_port = InMemoryDashboardExportAdapter()
    service = DashboardBuilderService(
        data_port,
        export_port,
        default_templates_dir=tmp_path,
    )

    template_path = tmp_path / "default.yaml"
    template_path.write_text(
        yaml.safe_dump(
            {
                "dashboard_id": "default",
                "name": "Default",
                "widgets": [
                    {
                        "widget_id": "kpi",
                        "type": "metric",
                        "query": "total",
                        "title": "Total",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    template = service.load_template("default")
    assert template.dashboard_id == "default"
    assert template.name == "Default"
    assert len(template.widgets) == 1


def test_builder_service_list_and_load_from_config_store() -> None:
    store = InMemoryConfigStoreAdapter()
    store.write(
        ConfigRecord(
            object_type="dashboard_template",
            object_id="operational",
            status="published",
            payload={
                "name": "Operational",
                "widgets": [
                    {
                        "widget_id": "kpi",
                        "type": "metric",
                        "query": "summary.total_events",
                        "title": "Total",
                    }
                ],
            },
            version_id="v1",
            created_at=datetime.now(),  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
            created_by="test",
        )
    )

    data_port = InMemoryDashboardDataAdapter({"summary.total_events": 123})
    export_port = InMemoryDashboardExportAdapter()
    service = DashboardBuilderService(data_port, export_port, config_store=store)

    templates = service.list_templates()
    assert any(t.dashboard_id == "operational" for t in templates)

    template = service.load_template("operational")
    assert template.dashboard_id == "operational"
    view_model = service.build(template)
    assert view_model.widgets[0].data == 123


def test_builder_service_build_and_drill_down(sample_template: DashboardTemplate) -> None:
    events = pd.DataFrame(
        {
            "country": ["德国", "美国", "德国"],
            "score": [90, 70, 80],
        }
    )
    data_port = InMemoryDashboardDataAdapter(
        {"summary.total_events": 3, "events": events}
    )
    export_port = InMemoryDashboardExportAdapter()
    service = DashboardBuilderService(data_port, export_port)

    view_model = service.build(sample_template)
    assert view_model.dashboard_id == "test"
    assert len(view_model.widgets) == 2
    assert view_model.widgets[0].data == 3
    assert len(view_model.widgets[1].data) == 3

    drilled = service.drill_down(
        view_model,
        DrillFilter(widget_id="w2", dimension="country", value="德国"),
    )
    assert drilled.context is not None
    assert drilled.context.filters == {"country": "德国"}
    table_data = drilled.widgets[1].data
    assert len(table_data) == 2
    assert set(table_data["country"]) == {"德国"}


def test_builder_service_export(sample_template: DashboardTemplate) -> None:
    data_port = InMemoryDashboardDataAdapter(
        {"summary.total_events": 5, "events": pd.DataFrame({"country": ["德国"], "score": [90]})}
    )
    export_port = InMemoryDashboardExportAdapter()
    service = DashboardBuilderService(data_port, export_port)

    view_model = service.build(sample_template)
    path = service.export(view_model, ExportFormat.EXCEL)
    assert path == Path("memory")
    assert export_port.exports == [("test", ExportFormat.EXCEL)]


def test_builder_service_unsupported_widget_type() -> None:
    template = DashboardTemplate(
        dashboard_id="bad",
        name="Bad",
        widgets=[WidgetSpec(widget_id="w", type="unknown", query="x", title="X")],
    )
    service = DashboardBuilderService(
        InMemoryDashboardDataAdapter({}),
        InMemoryDashboardExportAdapter(),
    )
    with pytest.raises(ValueError, match="unsupported widget type"):
        service.build(template)


# ----------------------------------------------------------------------
# Export adapters
# ----------------------------------------------------------------------
def test_excel_export_adapter(tmp_path: Path) -> None:
    view_model = DashboardViewModel(
        dashboard_id="export_test",
        name="Export Test",
        widgets=[
            WidgetViewModel(
                widget_id="kpi",
                type="metric",
                title="Total",
                query="total",
                data=42,
            ),
            WidgetViewModel(
                widget_id="table1",
                type="table",
                title="Countries",
                query="countries",
                data=pd.DataFrame({"country": ["德国", "美国"], "score": [90, 70]}),
            ),
        ],
    )
    adapter = ExcelDashboardExportAdapter(tmp_path)
    path = adapter.export(view_model, ExportFormat.EXCEL)
    assert path.exists()
    assert path.stat().st_size > 0

    sheets = pd.ExcelFile(path).sheet_names
    assert "metrics" in sheets
    assert "table1" in sheets


def test_excel_export_adapter_unsupported_format(tmp_path: Path) -> None:
    view_model = DashboardViewModel(
        dashboard_id="export_test",
        name="Export Test",
        widgets=[],
    )
    adapter = ExcelDashboardExportAdapter(tmp_path)
    with pytest.raises(NotImplementedError):
        adapter.export(view_model, ExportFormat.PDF)


# ----------------------------------------------------------------------
# Default project template
# ----------------------------------------------------------------------
def test_default_dashboard_template_yaml_exists() -> None:
    path = Path(__file__).resolve().parent.parent.parent / "Config" / "dashboard_templates" / "default.yaml"
    assert path.exists(), "Default dashboard template must exist"
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert payload["dashboard_id"] == "default"
    assert isinstance(payload["widgets"], list)
    widget_ids = {w["widget_id"] for w in payload["widgets"]}
    assert "kpi_total_events" in widget_ids
    assert "trend_30d" in widget_ids
    assert "country_summary" in widget_ids
