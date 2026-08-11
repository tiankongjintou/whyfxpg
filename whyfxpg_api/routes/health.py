"""健康检查（公开端点，P02 AC-6）。"""

from fastapi import APIRouter

import whyfxpg_api

router = APIRouter()


@router.get("/health", tags=["system"], summary="健康检查（公开）")
def health() -> dict:
    return {"status": "ok", "service": "whyfxpg-api", "version": whyfxpg_api.__version__}
