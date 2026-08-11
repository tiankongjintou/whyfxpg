"""当前账户端点（受保护示例，P02）。"""

from typing import Annotated

from fastapi import APIRouter, Depends

from whyfxpg.ports.account_port import AccountInfo
from whyfxpg_api.dependencies import get_current_account
from whyfxpg_api.schemas import AccountOut

router = APIRouter()


@router.get(
    "/api/v1/me",
    tags=["accounts"],
    summary="当前账户信息（需 API Key）",
    response_model=AccountOut,
)
def me(account: Annotated[AccountInfo, Depends(get_current_account)]) -> AccountOut:
    return AccountOut(
        account_id=account.account_id,
        company_name=account.company_name,
        plan_type=account.plan_type,
        monthly_quota=account.monthly_quota,
        status=account.status,
    )
