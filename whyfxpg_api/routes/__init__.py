"""路由包。"""

from whyfxpg_api.routes.alerts import router as alerts_router
from whyfxpg_api.routes.companies import router as companies_router
from whyfxpg_api.routes.events import router as events_router
from whyfxpg_api.routes.health import router as health_router
from whyfxpg_api.routes.me import router as me_router

__all__ = [
    "alerts_router",
    "companies_router",
    "events_router",
    "health_router",
    "me_router",
]
