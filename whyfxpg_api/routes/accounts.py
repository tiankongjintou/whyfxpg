"""账户管理端点（P1b-01）。

- POST  /api/v1/accounts                     — 注册（需 X-Master-Key，生成 API Key）
- GET   /api/v1/accounts/{account_id}        — 账户详情（需 API Key，租户隔离）
- POST  /api/v1/account/api-key/rotate       — 轮换自身 API Key
- POST  /api/v1/account/disable              — 禁用自身账户
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request

from whyfxpg.ports.account_port import AccountInfo
from whyfxpg.services.account_service import AccountService, MasterKeyError
from whyfxpg_api.dependencies import get_account_service, get_current_account
from whyfxpg_api.schemas.api_response import ok_response

router = APIRouter(prefix="/api/v1")

MASTER_KEY_HEADER = "X-Master-Key"

PLAN_QUOTAS = {"trial": 100, "basic": 5000, "pro": 50000}


def _handle_master_error(exc: MasterKeyError) -> HTTPException:
    if "未配置" in str(exc):
        return HTTPException(status_code=503, detail=str(exc))
    return HTTPException(status_code=403, detail=str(exc))


@router.post("/accounts", summary="注册企业账户（需 X-Master-Key）")
def create_account(
    request: Request,
    body: dict,
    service: Annotated[AccountService, Depends(get_account_service)],
) -> Any:
    master_key = request.headers.get(MASTER_KEY_HEADER)
    try:
        AccountService.check_master_key(master_key)
    except MasterKeyError as exc:
        raise _handle_master_error(exc) from exc

    company_name = (body.get("company_name") or "").strip()
    plan_type = (body.get("plan_type") or "trial").strip()
    if not company_name:
        raise HTTPException(status_code=422, detail="company_name 必填")
    monthly_quota = int(body.get("monthly_quota") or PLAN_QUOTAS.get(plan_type, 100))

    account, api_key = service.create_account(company_name, plan_type, monthly_quota)
    return ok_response(
        request,
        {
            "account_id": account.account_id,
            "company_name": account.company_name,
            "plan_type": account.plan_type,
            "monthly_quota": account.monthly_quota,
            "api_key_prefix": api_key[:10],
            "api_key": api_key,  # 明文仅此一次
        },
    )


@router.get("/accounts/{account_id}", summary="账户详情（需 API Key）")
def get_account_detail(
    request: Request,
    account_id: str,
    account: Annotated[AccountInfo, Depends(get_current_account)],
    service: Annotated[AccountService, Depends(get_account_service)],
) -> Any:
    # 租户隔离:仅可查询自身;master key 请求可查任意
    master_key = request.headers.get(MASTER_KEY_HEADER)
    if account.account_id != account_id:
        try:
            AccountService.check_master_key(master_key)
        except MasterKeyError as exc:
            raise _handle_master_error(exc) from exc
    target = service.get_account(account_id)
    if target is None:
        raise HTTPException(status_code=404, detail="账户不存在")
    return ok_response(
        request,
        {
            "account_id": target.account_id,
            "company_name": target.company_name,
            "plan_type": target.plan_type,
            "monthly_quota": target.monthly_quota,
            "status": target.status,
        },
    )


@router.post("/account/api-key/rotate", summary="轮换自身 API Key")
def rotate_api_key(
    request: Request,
    account: Annotated[AccountInfo, Depends(get_current_account)],
    service: Annotated[AccountService, Depends(get_account_service)],
) -> Any:
    new_key = service.rotate_api_key(account.account_id)
    return ok_response(
        request, {"api_key_prefix": new_key[:10], "api_key": new_key}
    )


@router.post("/account/disable", summary="禁用自身账户")
def disable_account(
    request: Request,
    account: Annotated[AccountInfo, Depends(get_current_account)],
    service: Annotated[AccountService, Depends(get_account_service)],
) -> Any:
    service.disable_account(account.account_id)
    return ok_response(request, {"account_id": account.account_id, "status": "disabled"})
