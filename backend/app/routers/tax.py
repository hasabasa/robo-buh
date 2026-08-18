"""Роутер налогового расчёта 910.00."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from ..tax.service import compute_declaration_910

router = APIRouter()


@router.post("/910/calculate")
async def calculate_910(
    taxpayer_id: UUID,
    year: int = Query(..., ge=2026, le=2035),
    half: int = Query(..., ge=1, le=2),
):
    """Считает форму 910.00 за полугодие из оборота income_ledger, сохраняет черновик."""
    try:
        return await compute_declaration_910(taxpayer_id, year, half)
    except ValueError as e:
        raise HTTPException(404, str(e))
