"""Dashboard data port: abstract the query layer behind a seam."""

from abc import ABC, abstractmethod
from typing import Any

from whyfxpg.webui.dashboard_models import DashboardContext


class DashboardDataPort(ABC):
    """Load data for a dashboard widget without exposing the storage backend.

    Implementations may wrap the existing ``DashboardReadModel`` (SQLite),
    an in-memory fixture, or a future real-time / OLAP source. The query
    string is intentionally opaque to the caller: the adapter decides how
    to interpret it.
    """

    @abstractmethod
    def load(self, context: DashboardContext, query: str) -> Any:
        """Return data for ``query`` under the given ``context``.

        The returned value should be JSON-serialisable or a pandas DataFrame,
        depending on the widget type that requested it.
        """
        ...
