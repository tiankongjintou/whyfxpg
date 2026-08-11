"""In-memory dashboard data adapter for unit tests and fixtures."""

from typing import Any

import pandas as pd

from whyfxpg.ports.dashboard_data import DashboardContext, DashboardDataPort


class InMemoryDashboardDataAdapter(DashboardDataPort):
    """Data port backed by a plain dictionary.

    Context filters are applied to DataFrames so tests can exercise
    drill-down without needing a database.
    """

    def __init__(self, data: dict[str, Any] | None = None):
        self.data = dict(data) if data else {}

    def load(self, context: DashboardContext, query: str) -> Any:
        data = self.data.get(query)
        if data is None:
            raise ValueError(f"No in-memory data registered for query: {query}")
        return _apply_filters(data, context.filters)


def _apply_filters(data: Any, filters: dict[str, Any]) -> Any:
    if not isinstance(data, pd.DataFrame) or data.empty or not filters:
        return data
    mask = pd.Series(True, index=data.index)
    for column, value in filters.items():
        if column in data.columns:
            mask &= data[column] == value
    return data[mask].reset_index(drop=True)
