"""
Tests for the BigScreen presenter seam.

These tests do NOT import streamlit; they verify data transformation only.
"""
import pandas as pd

from whyfxpg.webui.presenters.bigscreen_presenter import (
    BigScreenPresenter,
    BigScreenViewModel,
)
from whyfxpg.webui.read_model import DashboardReadModel


class FakeReadModel(DashboardReadModel):
    """In-memory stand-in that returns deterministic dashboard data."""

    def __init__(self, data):
        super().__init__(db_path=None)
        self._data = data

    def get_summary(self) -> dict:
        return self._data["summary"]

    def get_trend(self, days: int = 30) -> pd.DataFrame:
        return self._data["trend"]

    def get_hazard_distribution(self, limit: int = 10) -> pd.DataFrame:
        return self._data["hazard_distribution"]

    def get_country_summary(self, limit: int = 20) -> pd.DataFrame:
        return self._data["country_summary"]

    def get_recent_high_risk(self, limit: int = 15) -> pd.DataFrame:
        return self._data["recent_high_risk"]

    def get_alerts(self, limit: int = 200) -> pd.DataFrame:
        return self._data["alerts"]


def make_sample_data() -> dict:
    return {
        "summary": {
            "total_events": 100,
            "level_dist": {"S": 5, "M": 10, "L": 30, "A": 55},
            "pending_alerts": 3,
            "country_count": 12,
            "reviewed_count": 7,
        },
        "trend": pd.DataFrame({
            "date": ["2026-07-01", "2026-07-02"],
            "cnt": [4, 7],
        }),
        "hazard_distribution": pd.DataFrame({
            "type": ["机械危险", "电气危险"],
            "cnt": [8, 5],
        }),
        "country_summary": pd.DataFrame({
            "country": ["德国", "美国"],
            "event_count": [20, 15],
        }),
        "recent_high_risk": pd.DataFrame({
            "event_id": ["e1"],
            "publish_date": ["2026-07-01"],
            "product_name": ["电钻"],
            "brand": ["Bosch"],
            "country": ["德国"],
            "hazard_type": ["机械危险"],
            "rs_level": ["S"],
            "total_score": [9000],
        }),
        "alerts": pd.DataFrame({
            "triggered_at": ["2026-07-02 10:00"],
            "rule_name": ["高严重度"],
            "severity": ["high"],
            "status": ["pending"],
        }),
    }


def test_view_model_defaults():
    vm = BigScreenViewModel()
    assert vm.total_events == 0
    assert vm.level_dist == {}
    assert vm.pending_alerts == 0
    assert vm.country_count == 0
    assert vm.trend.empty
    assert vm.alerts.empty


def test_presenter_builds_view_model():
    data = make_sample_data()
    presenter = BigScreenPresenter(FakeReadModel(data))
    vm = presenter.present()

    assert vm.total_events == 100
    assert vm.level_dist == {"S": 5, "M": 10, "L": 30, "A": 55}
    assert vm.pending_alerts == 3
    assert vm.country_count == 12
    assert list(vm.trend.columns) == ["date", "cnt"]
    assert len(vm.alerts) == 1


def test_presenter_truncates_alerts_to_top10():
    data = make_sample_data()
    data["alerts"] = pd.DataFrame(
        {"triggered_at": [f"2026-07-{i:02d}" for i in range(1, 21)],
         "rule_name": ["R"] * 20,
         "severity": ["high"] * 20,
         "status": ["pending"] * 20,
        }
    )
    presenter = BigScreenPresenter(FakeReadModel(data))
    vm = presenter.present()
    assert len(vm.alerts) == 10


def test_presenter_with_empty_read_model():
    empty = {
        "summary": {
            "total_events": 0,
            "level_dist": {},
            "pending_alerts": 0,
            "country_count": 0,
            "reviewed_count": 0,
        },
        "trend": pd.DataFrame(),
        "hazard_distribution": pd.DataFrame(),
        "country_summary": pd.DataFrame(),
        "recent_high_risk": pd.DataFrame(),
        "alerts": pd.DataFrame(),
    }
    presenter = BigScreenPresenter(FakeReadModel(empty))
    vm = presenter.present()
    assert vm.total_events == 0
    assert vm.level_dist == {}
    assert vm.alerts.empty


def test_real_read_model_on_empty_initialized_db(initialized_db):
    """Smoke test: read_model + presenter work against a real empty test DB."""
    read_model = DashboardReadModel(db_path=initialized_db)
    presenter = BigScreenPresenter(read_model)
    vm = presenter.present()
    assert vm.total_events == 0
    assert vm.level_dist == {}
    assert vm.alerts.empty
    assert isinstance(vm.generated_at, str)
