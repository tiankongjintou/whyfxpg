"""Adapter that wraps the existing DashboardReadModel as a DashboardDataPort."""

from typing import Any

import pandas as pd

from whyfxpg.ports.dashboard_data import DashboardContext, DashboardDataPort
from whyfxpg.webui.read_model import DashboardReadModel


class DashboardReadModelAdapter(DashboardDataPort):
    """Load dashboard data from the SQLite read model.

    Query syntax is intentionally simple so templates stay declarative:

    - ``summary.total_events`` / ``summary.level_dist`` / ``summary.pending_alerts``
      / ``summary.country_count`` / ``summary.reviewed_count``
    - ``trend`` or ``trend.days=30``
    - ``hazard_distribution.limit=10``
    - ``country_summary.limit=20``
    - ``recent_high_risk.limit=15``
    - ``alerts.limit=10``
    - ``event_stream.limit=50``
    - ``heatmap.dimension_x=country.dimension_y=hazard_type`` (placeholder)
    """

    def __init__(self, read_model_or_db_path: str | DashboardReadModel | None = None):
        if isinstance(read_model_or_db_path, DashboardReadModel):
            self._read_model = read_model_or_db_path
        else:
            self._read_model = DashboardReadModel(read_model_or_db_path)

    def load(self, context: DashboardContext, query: str) -> Any:
        base, params = _parse_query(query)
        loader = getattr(self, f"_load_{base}", None)
        if loader is None:
            raise ValueError(f"Unsupported dashboard query: {query}")
        data = loader(context, params)
        return _apply_filters(data, context.filters)

    def _load_summary(self, context: DashboardContext, params: dict[str, Any]) -> Any:
        summary = self._read_model.get_summary()
        key = params.get("key")
        if key:
            value = summary.get(key)
            subkey = params.get("subkey")
            if subkey and isinstance(value, dict):
                for token in str(subkey).split("."):
                    if isinstance(value, dict):
                        value = value.get(token)
                    else:
                        break
            return value
        return summary

    def _load_trend(self, context: DashboardContext, params: dict[str, Any]) -> pd.DataFrame:
        days = int(params.get("days", 30))
        return self._read_model.get_trend(days=days)

    def _load_hazard_distribution(
        self, context: DashboardContext, params: dict[str, Any]
    ) -> pd.DataFrame:
        limit = int(params.get("limit", 10))
        return self._read_model.get_hazard_distribution(limit=limit)

    def _load_country_summary(
        self, context: DashboardContext, params: dict[str, Any]
    ) -> pd.DataFrame:
        limit = int(params.get("limit", 20))
        return self._read_model.get_country_summary(limit=limit)

    def _load_recent_high_risk(
        self, context: DashboardContext, params: dict[str, Any]
    ) -> pd.DataFrame:
        limit = int(params.get("limit", 15))
        return self._read_model.get_recent_high_risk(limit=limit)

    def _load_alerts(self, context: DashboardContext, params: dict[str, Any]) -> pd.DataFrame:
        limit = int(params.get("limit", 10))
        return self._read_model.get_alerts(limit=limit)

    def _load_event_stream(
        self, context: DashboardContext, params: dict[str, Any]
    ) -> pd.DataFrame:
        limit = int(params.get("limit", 50))
        return self._read_model.get_events(limit=limit)

    def _load_heatmap(
        self, context: DashboardContext, params: dict[str, Any]
    ) -> pd.DataFrame:
        return pd.DataFrame(
            columns=[
                params.get("dimension_x", "x"),
                params.get("dimension_y", "y"),
                "cnt",
            ]
        )


def _parse_query(query: str) -> tuple[str, dict[str, Any]]:
    parts = query.split(".")
    base = parts[0]
    params: dict[str, Any] = {}
    if base == "summary" and len(parts) >= 2 and "=" not in parts[1]:
        params["key"] = parts[1]
        subkeys: list[str] = []
        extra = parts[2:]
        for part in extra:
            if "=" in part:
                key, value = part.split("=", 1)
                params[key] = _coerce(value)
            elif part.isdigit():
                params["limit"] = int(part)
            else:
                subkeys.append(part)
        if subkeys:
            params["subkey"] = ".".join(subkeys)
        return base, params
    extra = parts[1:]
    for part in extra:
        if "=" in part:
            key, value = part.split("=", 1)
            params[key] = _coerce(value)
        elif part.isdigit():
            params["limit"] = int(part)
    return base, params


def _coerce(value: str) -> Any:
    if value.isdigit():
        return int(value)
    return value


def _apply_filters(data: Any, filters: dict[str, Any]) -> Any:
    """Apply dashboard context filters to DataFrames only."""
    if not isinstance(data, pd.DataFrame) or data.empty or not filters:
        return data
    mask = pd.Series(True, index=data.index)
    for column, value in filters.items():
        if column in data.columns:
            mask &= data[column] == value
    return data[mask].reset_index(drop=True)
