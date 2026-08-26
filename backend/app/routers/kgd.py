"""Роутер справок КГД: валидация налогоплательщика/контрагента."""

from fastapi import APIRouter, HTTPException, Query

from ..kgd.onboarding import validate_taxpayer
from ..kgd.portal_client import KgdPortalClient, KgdPortalError

router = APIRouter()


@router.get("/validate")
async def validate(code: str = Query(..., min_length=12, max_length=12),
                   kind: str = Query("too", pattern="^(too|ip)$")):
    """Онбординг-гейт: проверить БИН/ИИН клиента в реестре КГД (статус, УГД, НДС)."""
    try:
        return await validate_taxpayer(code, kind)
    except KgdPortalError as e:
        raise HTTPException(503, str(e))


@router.get("/counterparty")
async def counterparty(code: str = Query(..., min_length=12, max_length=12),
                       kind: str = Query("too", pattern="^(too|ip)$")):
    """Проверка контрагента из выписки (статус, ликвидация, НДС)."""
    try:
        info = await KgdPortalClient().taxpayer(code, "UL" if kind == "too" else "IP")
        return {"found": info.found, "name": info.name, "type": info.taxpayer_type,
                "begin_date": info.begin_date, "end_date": info.end_date,
                "liquidation": info.end_reason}
    except KgdPortalError as e:
        raise HTTPException(503, str(e))
