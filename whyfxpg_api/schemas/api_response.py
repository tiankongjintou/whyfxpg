"""统一成功响应信封（P03 AC-8）。

成功响应：``{"success": true, "data": {...}, "meta": {"request_id": "...", "quota_used": N}, "error": null}``
失败响应沿用 P02 的 ErrorResponse（``success: false``）。
"""

from typing import Any

from pydantic import BaseModel


class EnvelopeMeta(BaseModel):
    request_id: str
    quota_used: int = 0
    quota_remaining: int | None = None


class ApiResponse(BaseModel):
    success: bool = True
    data: Any
    meta: EnvelopeMeta
    error: str | None = None


def ok_response(request: Any, data: Any) -> ApiResponse:
    """构造统一成功响应，meta 从 request.state 读取（中间件注入）。"""
    return ApiResponse(
        success=True,
        data=data,
        meta=EnvelopeMeta(
            request_id=getattr(request.state, "request_id", ""),
            quota_used=getattr(request.state, "quota_used", 0),
            quota_remaining=getattr(request.state, "quota_remaining", None),
        ),
    )
