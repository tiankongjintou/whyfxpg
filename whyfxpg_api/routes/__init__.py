"""路由包。"""

from whyfxpg_api.routes.account import router as account_router
from whyfxpg_api.routes.accounts import router as accounts_router
from whyfxpg_api.routes.alerts import router as alerts_router
from whyfxpg_api.routes.companies import router as companies_router
from whyfxpg_api.routes.events import router as events_router
from whyfxpg_api.routes.health import router as health_router
from whyfxpg_api.routes.me import router as me_router
from whyfxpg_api.routes.webhooks import router as webhooks_router

__all__ = [
    "account_router",
    "accounts_router",
    "alerts_router",
    "companies_router",
    "events_router",
    "health_router",
    "me_router",
    "webhooks_router",
]
