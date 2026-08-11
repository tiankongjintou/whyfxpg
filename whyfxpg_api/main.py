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
from whyfxpg.ports.account_port import AccountPort
from whyfxpg.services.account_service import AccountService
from whyfxpg_api import __version__
from whyfxpg_api.middleware import AuthMiddleware, RequestIDMiddleware
from whyfxpg_api.routes import health_router, me_router


def create_app(
    account_port: AccountPort | None = None,
    account_service: AccountService | None = None,
) -> FastAPI:
    """应用工厂：默认按 DATABASE_URL 选择账户存储。

    - DATABASE_URL 为 PostgreSQL → PgAccountAdapter（生产）
    - 未设置 / 非 PG（本地开发、测试）→ InMemoryAccountAdapter（空账户，
      认证一律 403，避免无 PG 环境启动失败）
    """
    app = FastAPI(
        title="WHYFXPG API",
        version=__version__,
        description="海关进口机电产品风险评价闭环系统 — Phase 1 API",
        openapi_tags=[
            {"name": "system", "description": "系统级端点（健康检查）"},
            {"name": "accounts", "description": "账户与认证"},
        ],
    )

    if account_port is None:
        from whyfxpg.core.db import get_database_url, is_postgres_url

        db_url = get_database_url()
        if is_postgres_url(db_url):
            account_port = PgAccountAdapter(db_url)
        else:
            account_port = InMemoryAccountAdapter()
            import warnings

            warnings.warn(
                "DATABASE_URL 未指向 PostgreSQL，使用空 InMemory 账户存储（仅本地/测试）"
            )
    service = account_service or AccountService(account_port)
    app.state.account_service = service

    # 注意顺序:后 add 的在外层。RequestID 最外层保证所有响应(含 Auth 403)
    # 都带 X-Request-ID 头,且 Auth 中间件能读到 request.state.request_id。
    app.add_middleware(AuthMiddleware, account_service=service)
    app.add_middleware(RequestIDMiddleware)

    app.include_router(health_router)
    app.include_router(me_router)

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
