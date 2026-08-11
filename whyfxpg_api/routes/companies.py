"""企业风险画像端点（P03）。

- GET /api/v1/companies/{name}/profile — 企业风险画像（聚合事件+评分）
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request

from whyfxpg.ports.account_port import AccountInfo
from whyfxpg.ports.event_query_port import EventQueryPort
from whyfxpg_api.dependencies import get_current_account, get_event_query_port
from whyfxpg_api.schemas.api_response import ok_response

router = APIRouter(prefix="/api/v1")


@router.get("/companies/{company_name}/profile", summary="企业风险画像")
def company_profile(
    request: Request,
    company_name: str,
    account: Annotated[AccountInfo, Depends(get_current_account)],
    events: Annotated[EventQueryPort, Depends(get_event_query_port)],
) -> Any:
    profile = events.company_profile(account.account_id, company_name)
    if profile is None:
        raise HTTPException(status_code=404, detail="未找到该企业的风险事件")
    return ok_response(
        request,
        {
            "company_name": profile.company_name,
            "event_count": profile.event_count,
            "avg_score": profile.avg_score,
            "level_distribution": profile.level_distribution,
            "latest_events": [vars(e) for e in profile.latest_events],
        },
    )
