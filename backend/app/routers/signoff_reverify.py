"""签收复验路由：按历史包号复验签收正文、补全正式引用并留存归档凭据。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.signoff_reverify import signoff_reverify_service

router = APIRouter(prefix="/api/signoff_reverify", tags=["签收复验"])

service = signoff_reverify_service


class ReverifyPayload(BaseModel):
    """复验提交：包号、原签收摘要与手中字幕。"""

    pack_id: str = Field(default="", description="历史字幕包号")
    signoff_digest: str = Field(default="", description="签收当时记录的原摘要")
    subtitles: str = Field(default="", description="手中字幕正文")
    operator: str = Field(default="", description="提交人/接收人")


@router.get("/packs", response_model=list[dict])
def list_packs() -> list[dict[str, Any]]:
    """历史签收包及其复验/引用状态，供复验页选择包号。"""
    return service.packs_payload()


@router.get("/credentials", response_model=list[dict])
def list_credentials() -> list[dict[str, Any]]:
    """已永久保存的归档凭据，按复验先后排列。"""
    return service.credentials_payload()


@router.get("/status", response_model=dict)
def status() -> dict[str, Any]:
    """复验总览：历史签收包、已补全引用与未确认引用的数量。"""
    return service.summary()


@router.post("/verify", response_model=dict)
def verify(payload: ReverifyPayload) -> dict[str, Any]:
    """执行复验：服务端计算实际校验，通过才补写正式引用。"""
    result, message, status_code = service.verify(
        payload.pack_id, payload.signoff_digest, payload.subtitles, payload.operator)
    if result is None:
        raise HTTPException(status_code=status_code, detail=message)
    return result


@router.get("/packs/{pack_id}", response_model=dict)
def pack_detail(pack_id: str) -> dict[str, Any]:
    """单个历史签收包的复验与引用状态。"""
    for item in service.packs_payload():
        if item["pack_id"].upper() == pack_id.strip().upper():
            return item
    raise HTTPException(status_code=404, detail=f"未找到已签收的字幕包 {pack_id}")
