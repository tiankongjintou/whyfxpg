"""FastAPI 中间件（P02/P04）。

- RequestIDMiddleware：为每个请求生成/透传 ``X-Request-ID``，
  存入 ``request.state.request_id``（统一错误响应使用）。
- AuthMiddleware：默认保护所有端点，白名单（/health、/docs 等）除外；
  解析 ``X-API-Key`` 请求头 → AccountService.verify_key → 注入
  ``request.state.account``；失败返回 403 统一错误格式。
- MeteringMiddleware：认证后请求每次扣减额度（月度 + QPS），
  超额返回 429；注入 quota_used / quota_remaining 供响应 meta 使用。
"""

import uuid
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from whyfxpg.services.account_service import AccountService, ApiKeyError
from whyfxpg.services.metering_service import MeteringService, QuotaExceeded

# 公开端点白名单：不要求 API Key
# /api/v1/accounts(POST 注册)靠 X-Master-Key 保护,放行给 AuthMiddleware
PUBLIC_PATHS: set[str] = {"/", "/health", "/favicon.ico", "/api/v1/accounts"}
PUBLIC_PREFIXES: set[str] = {"/docs", "/redoc", "/openapi.json"}

# 不消耗额度的路径（用量查询不自我消耗）
METERING_EXEMPT: set[str] = {"/api/v1/account/usage", "/api/v1/account/quota"}

API_KEY_HEADER = "X-API-Key"


def _error_response(request: Request, status_code: int, message: str) -> JSONResponse:
    """构造统一错误响应（P02 AC-4）。"""
    return JSONResponse(
        status_code=status_code,
        content={
            "success": False,
            "error": message,
            "request_id": getattr(request.state, "request_id", ""),
        },
    )


class RequestIDMiddleware(BaseHTTPMiddleware):
    """为每个请求注入 request_id。"""

    async def dispatch(self, request: Request, call_next: Any) -> JSONResponse:
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


class AuthMiddleware(BaseHTTPMiddleware):
    """API Key 认证中间件（默认保护全部端点）。"""

    def __init__(self, app: Any, account_service: AccountService):
        super().__init__(app)
        self._account_service = account_service

    @staticmethod
    def _is_public(path: str) -> bool:
        return path in PUBLIC_PATHS or any(path.startswith(p) for p in PUBLIC_PREFIXES)

    async def dispatch(self, request: Request, call_next: Any) -> JSONResponse:
        if self._is_public(request.url.path):
            return await call_next(request)

        api_key = request.headers.get(API_KEY_HEADER)
        if not api_key:
            return _error_response(request, 403, "缺少 X-API-Key 请求头")
        try:
            account = self._account_service.verify_key(api_key)
        except ApiKeyError as exc:
            return _error_response(request, 403, str(exc))
        request.state.account = account
        return await call_next(request)


class MeteringMiddleware(BaseHTTPMiddleware):
    """API 计量与限流中间件（P04）。"""

    def __init__(self, app: Any, metering_service: MeteringService):
        super().__init__(app)
        self._service = metering_service

    async def dispatch(self, request: Request, call_next: Any) -> JSONResponse:
        account = getattr(request.state, "account", None)
        if account is None or request.url.path in METERING_EXEMPT:
            return await call_next(request)
        try:
            result = self._service.check_and_consume(account)
        except QuotaExceeded as exc:
            return _error_response(request, 429, str(exc))
        request.state.quota_used = result.quota_used
        request.state.quota_remaining = result.quota_remaining
        return await call_next(request)
