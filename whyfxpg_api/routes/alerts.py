"""预警端点（P03）。

- GET /api/v1/alerts           — 分页 + status 筛选
- GET /api/v1/alerts/{alert_id} — 预警详情
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from whyfxpg.ports.account_port import AccountInfo
from whyfxpg.ports.event_query_port import AlertRecord, EventQueryPort
from whyfxpg_api.dependencies import get_current_account, get_event_query_port
from whyfxpg_api.schemas.api_response import ok_response

router = APIRouter(prefix="/api/v1")


@router.get("/alerts", summary="预警列表（分页+状态筛选）")
def list_alerts(
    request: Request,
    account: Annotated[AccountInfo, Depends(get_current_account)],
    events: Annotated[EventQueryPort, Depends(get_event_query_port)],
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    status: str | None = None,
) -> Any:
    items, total = events.list_alerts(account.account_id, page, per_page, status)
    return ok_response(
        request,
        {"items": [vars(a) for a in items], "total": total, "page": page, "per_page": per_page},
    )


@router.get("/alerts/{alert_id}", summary="预警详情")
def get_alert(
    request: Request,
    alert_id: str,
    account: Annotated[AccountInfo, Depends(get_current_account)],
    events: Annotated[EventQueryPort, Depends(get_event_query_port)],
) -> Any:
    alert: AlertRecord | None = events.get_alert(account.account_id, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="预警不存在")
    return ok_response(request, vars(alert))
