"""Роутер дашборда: единый агрегат «сколько должен по всем налогам + что не сходится»."""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from ..dashboard.service import build_dashboard

router = APIRouter()


@router.get("/{taxpayer_id}")
async def dashboard(taxpayer_id: UUID, as_of: date | None = Query(None)):
    """Налоговая картина налогоплательщика на дату `as_of` (по умолчанию сегодня)."""
    try:
        return await build_dashboard(taxpayer_id, as_of)
    except ValueError as e:
        raise HTTPException(404, str(e))
