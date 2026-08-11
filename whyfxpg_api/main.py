"""WHYFXPG Phase 1 API 入口（P02）。

用法::

    uvicorn whyfxpg_api.main:app --reload
    # 或
    from whyfxpg_api.main import create_app
    app = create_app()

OpenAPI 文档: 启动后访问 /docs（Swagger UI）。
"""


from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from whyfxpg.adapters.accounts.in_memory_account_adapter import InMemoryAccountAdapter
from whyfxpg.adapters.accounts.pg_account_adapter import PgAccountAdapter
from whyfxpg.adapters.events.in_memory_event_query_adapter import (
    InMemoryEventQueryAdapter,
)
from whyfxpg.adapters.events.pg_event_query_adapter import PgEventQueryAdapter
from whyfxpg.adapters.metering.in_memory_metering_adapter import InMemoryMeteringAdapter
from whyfxpg.adapters.webhooks.in_memory_webhook_adapter import InMemoryWebhookAdapter
from whyfxpg.ports.account_port import AccountPort
from whyfxpg.ports.event_query_port import EventQueryPort
from whyfxpg.services.account_service import AccountService
from whyfxpg.services.metering_service import MeteringService
from whyfxpg.services.webhook_service import WebhookService
from whyfxpg_api import __version__
from whyfxpg_api.middleware import (
    AuthMiddleware,
    MeteringMiddleware,
    RequestIDMiddleware,
)
from whyfxpg_api.routes import (
    account_router,
    alerts_router,
    companies_router,
    events_router,
    health_router,
    me_router,
    webhooks_router,
)


def create_app(
    account_port: AccountPort | None = None,
    account_service: AccountService | None = None,
    event_query_port: EventQueryPort | None = None,
    metering_service: MeteringService | None = None,
    webhook_service: WebhookService | None = None,
) -> FastAPI:
    """应用工厂：默认按 DATABASE_URL 选择账户/事件存储。

    - DATABASE_URL 为 PostgreSQL → Pg adapter（生产）
    - 未设置 / 非 PG（本地开发、测试）→ InMemory adapter（空数据，
      避免无 PG 环境启动失败）
    """
    app = FastAPI(
        title="WHYFXPG API",
        version=__version__,
        description="海关进口机电产品风险评价闭环系统 — Phase 1 API",
        openapi_tags=[
            {"name": "system", "description": "系统级端点（健康检查）"},
            {"name": "accounts", "description": "账户与认证"},
            {"name": "events", "description": "风险事件查询与评分"},
            {"name": "alerts", "description": "预警"},
        ],
    )

    from whyfxpg.core.db import get_database_url, is_postgres_url

    db_url = get_database_url()
    if is_postgres_url(db_url):
        account_port = account_port or PgAccountAdapter(db_url)
        event_query_port = event_query_port or PgEventQueryAdapter(db_url)
    else:
        account_port = account_port or InMemoryAccountAdapter()
        event_query_port = event_query_port or InMemoryEventQueryAdapter()
        import warnings

        warnings.warn(
            "DATABASE_URL 未指向 PostgreSQL，使用空 InMemory 存储（仅本地/测试）"
        )
    service = account_service or AccountService(account_port)
    app.state.account_service = service
    app.state.event_query_port = event_query_port
    metering = metering_service or MeteringService(InMemoryMeteringAdapter())
    app.state.metering_service = metering
    webhooks = webhook_service or WebhookService(InMemoryWebhookAdapter())
    app.state.webhook_service = webhooks

    # 注意顺序:后 add 的在外层。RequestID 最外层保证所有响应(含 403/429)
    # 都带 X-Request-ID 头;Auth 在 Metering 外层(先认证再计量)。
    app.add_middleware(MeteringMiddleware, metering_service=metering)
    app.add_middleware(AuthMiddleware, account_service=service)
    app.add_middleware(RequestIDMiddleware)

    app.include_router(health_router)
    app.include_router(me_router)
    app.include_router(events_router)
    app.include_router(alerts_router)
    app.include_router(companies_router)
    app.include_router(account_router)
    app.include_router(webhooks_router)

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(request, exc: RequestValidationError) -> JSONResponse:
        """参数校验错误也返回统一错误格式。"""
        request_id = getattr(request.state, "request_id", "")
        return JSONResponse(
            status_code=422,
            content={"success": False, "error": str(exc.errors()[:1]), "request_id": request_id},
        )

    return app


app = create_app()
