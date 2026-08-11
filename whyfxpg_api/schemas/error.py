"""统一响应 Schema（P02 AC-4）。"""

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """统一错误响应：``{"success": false, "error": "...", "request_id": "..."}``"""

    success: bool = False
    error: str
    request_id: str
