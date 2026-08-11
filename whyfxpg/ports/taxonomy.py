"""Taxonomy port: abstract product classification behind a seam."""

from abc import ABC, abstractmethod
from typing import Any

from whyfxpg.config.models import TaxonomyNode


class TaxonomyPort(ABC):
    """Query a product taxonomy without knowing whether it comes from
    a local YAML file, an HS code database, an IEC standard, etc.
    """

    @abstractmethod
    def list_children(self, parent_id: str | None) -> list[TaxonomyNode]:
        """Return direct children of a node."""
        ...

    @abstractmethod
    def search(self, keyword: str) -> list[TaxonomyNode]:
        """Return nodes whose name, aliases, or keywords contain the keyword."""
        ...

    @abstractmethod
    def map_event(self, event: dict[str, Any]) -> TaxonomyNode | None:
        """Map a risk event (e.g. by product_name / hs_code) to a taxonomy node."""
        ...
