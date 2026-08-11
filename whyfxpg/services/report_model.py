"""
Report model: a plain data object used by ReportBuilder and ReportRenderer.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class ReportModel:
    """Plain data object passed from builder to renderer(s)."""

    total_events: int = 0
    level_counts: dict[str, int] = field(default_factory=dict)
    top_events: list[dict[str, Any]] = field(default_factory=list)
    top_products: list[dict[str, Any]] = field(default_factory=list)
    top_countries: list[dict[str, Any]] = field(default_factory=list)
    pending_alerts: list[dict[str, Any]] = field(default_factory=list)
    executive_summary: str = ""
    generated_at: str = field(
        default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S")  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
    )
    report_type: str = "comprehensive"
    filters: dict[str, Any] | None = None

    @property
    def has_data(self) -> bool:
        return self.total_events > 0 or bool(self.top_events)
