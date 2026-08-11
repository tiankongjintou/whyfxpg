"""风险事件端点（P03）。

- GET  /api/v1/events          — 分页 + 筛选（manufacturer/country/hazard_type）
- GET  /api/v1/events/{id}     — 事件详情
- POST /api/v1/events/assess   — 实时评分（RiskScorer，含 breakdown）
- POST /api/v1/events/batch-assess — 批量评分（≤100）
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from whyfxpg.core.risk_scorer import RiskScorer
from whyfxpg.ports.account_port import AccountInfo
from whyfxpg.ports.event_query_port import EventQueryPort, EventRecord
from whyfxpg_api.dependencies import get_current_account, get_event_query_port
from whyfxpg_api.schemas.api_response import ok_response

router = APIRouter(prefix="/api/v1")

MAX_BATCH = 100


@router.get("/events", summary="分页查询风险事件")
def list_events(
    request: Request,
    account: Annotated[AccountInfo, Depends(get_current_account)],
    events: Annotated[EventQueryPort, Depends(get_event_query_port)],
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    manufacturer: str | None = None,
    country: str | None = None,
    hazard_type: str | None = None,
) -> Any:
    items, total = events.list_events(
        account.account_id, page, per_page, manufacturer, country, hazard_type
    )
    return ok_response(
        request,
        {
            "items": [vars(e) for e in items],
            "total": total,
            "page": page,
            "per_page": per_page,
        },
    )


@router.get("/events/{event_id}", summary="事件详情")
def get_event(
    request: Request,
    event_id: str,
    account: Annotated[AccountInfo, Depends(get_current_account)],
    events: Annotated[EventQueryPort, Depends(get_event_query_port)],
) -> Any:
    event: EventRecord | None = events.get_event(account.account_id, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="事件不存在")
    return ok_response(request, vars(event))


@router.post("/events/assess", summary="实时评分（含 breakdown）")
def assess_event(
    request: Request,
    body: dict[str, Any],
    account: Annotated[AccountInfo, Depends(get_current_account)],
) -> Any:
    event: dict[str, Any] = body.get("event") or {}
    historical_counts: dict[str, int] = body.get("historical_counts") or {}
    causal_factor: float = float(body.get("causal_factor", 1.0))
    result = RiskScorer.assess(event, historical_counts, causal_factor)
    return ok_response(
        request,
        {
            "ss_score": result.ss_score,
            "ps_score": result.ps_score,
            "probability_level": result.probability_level,
            "total_score": result.total_score,
            "rs_level": result.rs_level,
            "breakdown": {
                "country_factor": result.country_factor,
                "product_factor": result.product_factor,
                "history_factor": result.history_factor,
                "evidence_factor": result.evidence_factor,
                "causal_factor": result.causal_factor,
            },
        },
    )


@router.post("/events/batch-assess", summary="批量评分（≤100）")
def batch_assess(
    request: Request,
    body: dict[str, Any],
    account: Annotated[AccountInfo, Depends(get_current_account)],
) -> Any:
    events_input: list[dict[str, Any]] = body.get("events") or []
    if len(events_input) > MAX_BATCH:
        raise HTTPException(status_code=422, detail=f"批量评分最多 {MAX_BATCH} 条")
    results = []
    for item in events_input:
        historical_counts: dict[str, int] = item.get("historical_counts") or {}
        causal_factor: float = float(item.get("causal_factor", 1.0))
        result = RiskScorer.assess(item.get("event") or {}, historical_counts, causal_factor)
        results.append(
            {
                "total_score": result.total_score,
                "rs_level": result.rs_level,
                "ss_score": result.ss_score,
                "ps_score": result.ps_score,
            }
        )
    return ok_response(request, {"results": results, "count": len(results)})
