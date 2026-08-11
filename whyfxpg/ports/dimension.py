"""Dimension port: abstract risk dimensions behind a seam."""

from abc import ABC, abstractmethod
from typing import Any

from whyfxpg.config.models import RiskDimension


class DimensionPort(ABC):
    """Query and aggregate risk dimensions without knowing whether they
    come from a fixed YAML file, a database registry, or an external API.
    """

    @abstractmethod
    def list_dimensions(self) -> list[RiskDimension]:
        """Return all configured dimensions."""
        ...

    @abstractmethod
    def weight_of(self, dimension_id: str) -> float:
        """Return the weight for a dimension."""
        ...

    @abstractmethod
    def aggregate(self, dimension_id: str, events: list[dict[str, Any]]) -> Any:
        """Aggregate a list of events along the given dimension."""
        ...
