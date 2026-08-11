"""Dimension adapters."""

from pathlib import Path
from typing import Any

import yaml

from whyfxpg.config.models import RiskDimension
from whyfxpg.ports.dimension import DimensionPort


def _aggregate(dimension: RiskDimension, events: list[dict[str, Any]]) -> Any:
    field = dimension.source_field
    agg = dimension.aggregation
    values = [e.get(field) for e in events if field in e]
    if not values:
        return {}

    if agg == "sum":
        return sum(_as_number(v) for v in values)
    if agg == "max":
        return max(_as_number(v) for v in values)
    if agg == "distinct":
        return len({str(v) for v in values if v is not None})
    if agg == "custom":
        return {"count": len(values), "field": field}
    # default count
    counts: dict[str, int] = {}
    for v in values:
        key = "missing" if v is None else str(v)
        counts[key] = counts.get(key, 0) + 1
    return counts


def _as_number(value: Any) -> float:
    try:
        return float(value) if value is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


class FixedDimensionsAdapter(DimensionPort):
    """Load dimensions from a local YAML file."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._dimensions: list[RiskDimension] = []
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        payload = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        dims = payload.get("dimensions") or []
        self._dimensions = [
            RiskDimension.from_dict(d) for d in dims if isinstance(d, dict)
        ]

    def list_dimensions(self) -> list[RiskDimension]:
        return list(self._dimensions)

    def weight_of(self, dimension_id: str) -> float:
        for d in self._dimensions:
            if d.dimension_id == dimension_id:
                return d.weight
        return 1.0

    def aggregate(self, dimension_id: str, events: list[dict[str, Any]]) -> Any:
        for d in self._dimensions:
            if d.dimension_id == dimension_id:
                return _aggregate(d, events)
        return {}


class InMemoryDimensionAdapter(DimensionPort):
    """In-memory dimensions for tests and demos."""

    def __init__(self, dimensions: list[RiskDimension]):
        self._dimensions = dimensions

    def list_dimensions(self) -> list[RiskDimension]:
        return list(self._dimensions)

    def weight_of(self, dimension_id: str) -> float:
        for d in self._dimensions:
            if d.dimension_id == dimension_id:
                return d.weight
        return 1.0

    def aggregate(self, dimension_id: str, events: list[dict[str, Any]]) -> Any:
        for d in self._dimensions:
            if d.dimension_id == dimension_id:
                return _aggregate(d, events)
        return {}
