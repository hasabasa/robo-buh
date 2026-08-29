"""Роутер налогового расчёта 910.00."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from datetime import date
from decimal import Decimal

from ..tax.penalty import calc_penalty
from ..tax.service import compute_declaration_910
from ..tax.xml_service import generate_910_xml
from ..tax.xml_200_service import generate_200_xml
from ..tax.vat_service import compute_vat_300
from ..tax.payroll_service import compute_200
from ..tax.kpn_service import compute_kpn_100

router = APIRouter()


@router.post("/penalty")
async def penalty(amount: Decimal, due_date: date, pay_date: date):
    """Пеня за просрочку уплаты: П = недоимка × ставка НБРК/100 × 1,25 × дни / 365, по под-периодам."""
    r = calc_penalty(amount, due_date, pay_date)
    return {
        "principal": str(r.principal), "total_days": r.total_days,
        "penalty_total": str(r.total), "stale_rate": r.stale,
        "breakdown": [
            {"from": str(s.date_from), "to": str(s.date_to), "days": s.days,
             "rate_pct": str(s.rate_pct), "coef": str(s.coef), "penalty": str(s.amount)}
            for s in r.segments
        ],
    }


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


@router.post("/910/{declaration_id}/xml")
async def build_910_xml_endpoint(declaration_id: UUID):
    """Собирает XML 910.00 по официальной структуре формы + локальный ФЛК, сохраняет в декларацию."""
    try:
        result = await generate_910_xml(declaration_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    if not result.get("ok"):
        raise HTTPException(422, detail={"flk_errors": result["flk_errors"], "flk_warnings": result["flk_warnings"]})
    return result


@router.post("/200/{declaration_id}/xml")
async def build_200_xml_endpoint(declaration_id: UUID):
    """Собирает XML 200.00 по своду + локальный ФЛК, сохраняет в декларацию."""
    try:
        result = await generate_200_xml(declaration_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    if not result.get("ok"):
        raise HTTPException(422, detail={"flk_errors": result["flk_errors"],
                                         "flk_warnings": result["flk_warnings"]})
    return result


@router.post("/300/calculate")
async def calculate_300(taxpayer_id: UUID, year: int = Query(..., ge=2026, le=2035),
                        quarter: int = Query(..., ge=1, le=4)):
    """Считает НДС форму 300.00 за квартал из income_ledger (исходящий − входящий)."""
    try:
        return await compute_vat_300(taxpayer_id, year, quarter)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/200/calculate")
async def calculate_200(taxpayer_id: UUID, year: int = Query(..., ge=2026, le=2035),
                        quarter: int = Query(..., ge=1, le=4)):
    """Считает зарплатную форму 200.00 за квартал по работникам налогоплательщика."""
    try:
        return await compute_200(taxpayer_id, year, quarter)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/100/calculate")
async def calculate_100(taxpayer_id: UUID, year: int = Query(..., ge=2026, le=2035),
                        prior_losses: Decimal = Decimal(0), advances_paid: Decimal = Decimal(0)):
    """Считает годовую форму 100.00 (КПН) из income_ledger: СГД − вычеты × 20%."""
    try:
        return await compute_kpn_100(taxpayer_id, year, prior_losses, advances_paid)
    except ValueError as e:
        raise HTTPException(404, str(e))
