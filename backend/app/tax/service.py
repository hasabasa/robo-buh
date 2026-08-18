"""Расчёт 910.00 из данных: агрегирует оборот income_ledger за полугодие → черновик декларации."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import date
from decimal import Decimal
from uuid import UUID

from ..core.database import get_pool
from .simplified_910 import Calc910, calc_910, snr_limit_status

logger = logging.getLogger(__name__)


def half_year_bounds(year: int, half: int) -> tuple[date, date]:
    if half == 1:
        return date(year, 1, 1), date(year, 6, 30)
    return date(year, 7, 1), date(year, 12, 31)


async def _turnover(conn, taxpayer_id: UUID, d1: date, d2: date) -> Decimal:
    """Облагаемый оборот: подтверждённый доход, без дублей, за период."""
    val = await conn.fetchval(
        """
        SELECT COALESCE(SUM(amount), 0) FROM income_ledger
        WHERE taxpayer_id = $1
          AND is_income IS TRUE
          AND status = 'confirmed'
          AND duplicate_of IS NULL
          AND op_date BETWEEN $2 AND $3
        """,
        taxpayer_id, d1, d2,
    )
    return Decimal(str(val or 0))


async def compute_declaration_910(taxpayer_id: UUID, year: int, half: int) -> dict:
    """Считает 910.00 за полугодие и сохраняет/обновляет черновик декларации."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        tp = await conn.fetchrow(
            "SELECT kind, iin_bin, maslikhat_rate, birth_date FROM taxpayers WHERE id=$1",
            taxpayer_id,
        )
        if not tp:
            raise ValueError("Налогоплательщик не найден")

        d1, d2 = half_year_bounds(year, half)
        turnover = await _turnover(conn, taxpayer_id, d1, d2)
        # оборот нарастающим итогом с 1 января — для светофора лимита СНР
        ytd = await _turnover(conn, taxpayer_id, date(year, 1, 1), d2)

    calc: Calc910 = calc_910(
        turnover=turnover,
        period=f"H{half}-{year}",
        taxpayer_kind=tp["kind"],
        maslikhat_rate=tp["maslikhat_rate"],
        birth_date=tp["birth_date"],
    )
    limit = snr_limit_status(ytd)

    calc_json = {
        "period": calc.period,
        "turnover": str(calc.turnover),
        "rate": str(calc.rate),
        "income_tax": str(calc.income_tax),
        "income_tax_name": calc.income_tax_name,
        "lines": calc.lines,
        "social": _social_to_json(calc.social),
        "snr_limit": {
            "ytd_turnover": str(limit.ytd_turnover),
            "limit": str(limit.limit),
            "share": str(limit.share),
            "zone": limit.zone,
            "message": limit.message,
        },
    }

    async with pool.acquire() as conn:
        decl_id = await conn.fetchval(
            """
            INSERT INTO declarations (taxpayer_id, form_code, period_year, period_no, calc, status)
            VALUES ($1, '910.00', $2, $3, $4, 'draft')
            ON CONFLICT (taxpayer_id, form_code, period_year, period_no, kind)
            DO UPDATE SET calc = EXCLUDED.calc, updated_at = now(),
                          status = CASE WHEN declarations.status IN ('signed','submitted','accepted')
                                        THEN declarations.status ELSE 'draft' END
            RETURNING id
            """,
            taxpayer_id, year, half, json.dumps(calc_json),
        )
    logger.info("910.00 %s: оборот %s → %s %s (decl %s)",
                calc.period, turnover, calc.income_tax, calc.income_tax_name, decl_id)
    return {"declaration_id": str(decl_id), **calc_json}


def _social_to_json(social: dict) -> dict:
    if not social:
        return {}
    m = social["monthly"]
    return {
        "months": social["months"],
        "monthly": {"opv": str(m.opv), "opvr": str(m.opvr), "so": str(m.so), "vosms": str(m.vosms),
                    "total": str(m.total)},
        "opv_total": str(social["opv_total"]),
        "opvr_total": str(social["opvr_total"]),
        "so_total": str(social["so_total"]),
        "vosms_total": str(social["vosms_total"]),
        "total": str(social["total"]),
    }
