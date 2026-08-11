"""Rule repository port.

Abstracts where rule definitions live (YAML files, in-memory fixtures, DB, etc.).
"""

from abc import ABC, abstractmethod
from typing import Any


class RuleRepositoryPort(ABC):
    """Port for loading and saving AlertRule objects."""

    @abstractmethod
    def load(self, rule_id: str) -> Any:
        """Load a single rule by its identifier."""
        ...

    @abstractmethod
    def list(self) -> list[Any]:
        """Return all rules."""
        ...

    @abstractmethod
    def save(self, rule: Any) -> None:
        """Save or update a rule."""
        ...

    @abstractmethod
    def delete(self, rule_id: str) -> None:
        """Remove a rule by its identifier."""
        ...
