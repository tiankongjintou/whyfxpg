"""路由包。"""

from whyfxpg_api.routes.health import router as health_router
from whyfxpg_api.routes.me import router as me_router

__all__ = ["health_router", "me_router"]
