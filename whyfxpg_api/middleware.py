"""FastAPI 中间件（P02 AC-2/4/6）。

- RequestIDMiddleware：为每个请求生成/透传 ``X-Request-ID``，
  存入 ``request.state.request_id``（统一错误响应使用）。
- AuthMiddleware：默认保护所有端点，白名单（/health、/docs 等）除外；
  解析 ``X-API-Key`` 请求头 → AccountService.verify_key → 注入
  ``request.state.account``；失败返回 403 统一错误格式。
"""

import uuid
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from whyfxpg.services.account_service import AccountService, ApiKeyError

# 公开端点白名单：不要求 API Key
PUBLIC_PATHS: set[str] = {"/", "/health", "/favicon.ico"}
PUBLIC_PREFIXES: set[str] = {"/docs", "/redoc", "/openapi.json"}

API_KEY_HEADER = "X-API-Key"


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

    def _unauthorized(self, request: Request, message: str) -> JSONResponse:
        return JSONResponse(
            status_code=403,
            content={
                "success": False,
                "error": message,
                "request_id": getattr(request.state, "request_id", ""),
            },
        )

    async def dispatch(self, request: Request, call_next: Any) -> JSONResponse:
        if self._is_public(request.url.path):
            return await call_next(request)

        api_key = request.headers.get(API_KEY_HEADER)
        if not api_key:
            return self._unauthorized(request, "缺少 X-API-Key 请求头")
        try:
            account = self._account_service.verify_key(api_key)
        except ApiKeyError as exc:
            return self._unauthorized(request, str(exc))
        request.state.account = account
        return await call_next(request)
