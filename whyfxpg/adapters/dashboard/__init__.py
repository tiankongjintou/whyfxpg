"""Dashboard adapters package."""

from whyfxpg.adapters.dashboard.dashboard_read_model_adapter import (
    DashboardReadModelAdapter,
)
from whyfxpg.adapters.dashboard.excel_dashboard_export_adapter import (
    ExcelDashboardExportAdapter,
)
from whyfxpg.adapters.dashboard.in_memory_dashboard_data_adapter import (
    InMemoryDashboardDataAdapter,
)
from whyfxpg.adapters.dashboard.in_memory_dashboard_export_adapter import (
    InMemoryDashboardExportAdapter,
)

__all__ = [
    "DashboardReadModelAdapter",
    "ExcelDashboardExportAdapter",
    "InMemoryDashboardDataAdapter",
    "InMemoryDashboardExportAdapter",
]
