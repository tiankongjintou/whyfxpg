"""Webhook 端点（P05）。

- POST   /api/v1/webhooks             — 注册（account_id 下 url 唯一）
- GET    /api/v1/webhooks             — 当前账户全部 Webhook
- DELETE /api/v1/webhooks/{id}        — 删除
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request

from whyfxpg.ports.account_port import AccountInfo
from whyfxpg.services.webhook_service import WebhookService
from whyfxpg_api.dependencies import get_current_account, get_webhook_service
from whyfxpg_api.schemas.api_response import ok_response

router = APIRouter(prefix="/api/v1")


def _record_to_dict(w) -> dict:
    return {
        "webhook_id": w.webhook_id,
        "url": w.url,
        "event_types": w.event_types,
        "enabled": w.enabled,
    }


@router.post("/webhooks", summary="注册 Webhook")
def create_webhook(
    request: Request,
    body: dict,
    account: Annotated[AccountInfo, Depends(get_current_account)],
    webhooks: Annotated[WebhookService, Depends(get_webhook_service)],
) -> Any:
    url = (body.get("url") or "").strip()
    event_types: list[str] = [str(t) for t in (body.get("event_types") or [])]
    if not url.startswith("https://") and not url.startswith("http://"):
        raise HTTPException(status_code=422, detail="url 必须为 http(s) 地址")
    record = webhooks.register(account.account_id, url, event_types)
    data = _record_to_dict(record)
    data["secret"] = record.secret  # 注册时返回一次 secret 供客户验签
    return ok_response(request, data)


@router.get("/webhooks", summary="列出当前账户 Webhook")
def list_webhooks(
    request: Request,
    account: Annotated[AccountInfo, Depends(get_current_account)],
    webhooks: Annotated[WebhookService, Depends(get_webhook_service)],
) -> Any:
    records = webhooks.list(account.account_id)
    return ok_response(request, {"items": [_record_to_dict(w) for w in records], "total": len(records)})


@router.delete("/webhooks/{webhook_id}", summary="删除 Webhook")
def delete_webhook(
    request: Request,
    webhook_id: str,
    account: Annotated[AccountInfo, Depends(get_current_account)],
    webhooks: Annotated[WebhookService, Depends(get_webhook_service)],
) -> Any:
    deleted = webhooks.delete(account.account_id, webhook_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Webhook 不存在")
    return ok_response(request, {"deleted": True, "webhook_id": webhook_id})
