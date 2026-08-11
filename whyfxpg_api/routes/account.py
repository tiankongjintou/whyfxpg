"""账户用量端点（P04）。

- GET /api/v1/account/usage — 当月累计调用次数
- GET /api/v1/account/quota  — 额度信息（含 reset_at）
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request

from whyfxpg.ports.account_port import AccountInfo
from whyfxpg.services.metering_service import MeteringService
from whyfxpg_api.dependencies import get_current_account, get_metering_service
from whyfxpg_api.schemas.api_response import ok_response

router = APIRouter(prefix="/api/v1/account")


@router.get("/usage", summary="当月累计用量")
def account_usage(
    request: Request,
    account: Annotated[AccountInfo, Depends(get_current_account)],
    metering: Annotated[MeteringService, Depends(get_metering_service)],
) -> Any:
    used = metering.get_monthly_usage(account.account_id)
    return ok_response(request, {"monthly_used": used, "plan_type": account.plan_type})


@router.get("/quota", summary="额度信息（含 reset_at）")
def account_quota(
    request: Request,
    account: Annotated[AccountInfo, Depends(get_current_account)],
    metering: Annotated[MeteringService, Depends(get_metering_service)],
) -> Any:
    return ok_response(request, metering.get_quota(account))
