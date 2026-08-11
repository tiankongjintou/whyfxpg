"""
BigScreen presenter: transform dashboard data into a renderable view model.

Keeps Streamlit rendering details out of data transformation and unit tests.
"""
from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

from whyfxpg.webui.read_model import DashboardReadModel


@dataclass
class BigScreenViewModel:
    """Plain data object consumed by the bigscreen render function."""

    total_events: int = 0
    level_dist: dict[str, int] = field(default_factory=dict)
    pending_alerts: int = 0
    country_count: int = 0
    trend: pd.DataFrame = field(default_factory=pd.DataFrame)
    hazard_distribution: pd.DataFrame = field(default_factory=pd.DataFrame)
    country_summary: pd.DataFrame = field(default_factory=pd.DataFrame)
    recent_high_risk: pd.DataFrame = field(default_factory=pd.DataFrame)
    alerts: pd.DataFrame = field(default_factory=pd.DataFrame)
    generated_at: str = field(
        default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S")  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
    )


class BigScreenPresenter:
    """Build a BigScreenViewModel from a DashboardReadModel."""

    def __init__(self, read_model: DashboardReadModel):
        self._read_model = read_model

    def present(self) -> BigScreenViewModel:
        summary = self._read_model.get_summary()
        return BigScreenViewModel(
            total_events=summary.get("total_events", 0),
            level_dist=summary.get("level_dist", {}),
            pending_alerts=summary.get("pending_alerts", 0),
            country_count=summary.get("country_count", 0),
            trend=self._read_model.get_trend(days=30),
            hazard_distribution=self._read_model.get_hazard_distribution(limit=10),
            country_summary=self._read_model.get_country_summary(limit=10),
            recent_high_risk=self._read_model.get_recent_high_risk(limit=15),
            alerts=self._read_model.get_alerts().head(10),
        )
