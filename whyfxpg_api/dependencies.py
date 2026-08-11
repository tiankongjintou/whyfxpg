"""依赖注入（P02）。

- ``get_current_account``：从 ``request.state.account`` 取当前账户
  （由 AuthMiddleware 注入；直接调用时若未认证则抛 403）。
"""

from typing import Any

from fastapi import HTTPException, Request

from whyfxpg.ports.account_port import AccountInfo
from whyfxpg.services.account_service import AccountService


def get_account_service(request: Request) -> AccountService:
    """从应用状态取 AccountService。"""
    service: AccountService = request.app.state.account_service
    return service


def get_current_account(request: Request) -> AccountInfo:
    """返回当前认证账户（AuthMiddleware 注入）。"""
    account: Any = getattr(request.state, "account", None)
    if account is None:
        raise HTTPException(status_code=403, detail="未认证")
    return account
