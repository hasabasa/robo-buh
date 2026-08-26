"""Расчёт 200.00 из БД: берёт работников налогоплательщика → свод за квартал → черновик."""
from __future__ import annotations
import json, logging
from decimal import Decimal
from uuid import UUID
from ..core.database import get_pool
from .payroll_200 import calc_200_quarter
from .vat_300 import quarter_bounds

logger = logging.getLogger(__name__)


async def compute_200(taxpayer_id: UUID, year: int, quarter: int) -> dict:
    d1, d2 = quarter_bounds(year, quarter)
    pool = await get_pool()
    async with pool.acquire() as conn:
        tp = await conn.fetchrow("SELECT kind FROM taxpayers WHERE id=$1", taxpayer_id)
        if not tp:
            raise ValueError("Налогоплательщик не найден")
        # работники, активные в квартале (приняты до конца, не уволены до начала)
        rows = await conn.fetch(
            """SELECT salary FROM employees WHERE taxpayer_id=$1
               AND (hired_at IS NULL OR hired_at <= $3)
               AND (fired_at IS NULL OR fired_at >= $2)""",
            taxpayer_id, d1, d2)
    salaries = [Decimal(str(r["salary"])) for r in rows if r["salary"]]
    if not salaries:
        return {"period": f"Q{quarter}-{year}", "employees": 0, "total_to_budget": "0",
                "note": "нет активных работников в периоде"}

    calc = calc_200_quarter(salaries)
    calc_json = {"period": f"Q{quarter}-{year}", **calc}

    async with pool.acquire() as conn:
        decl_id = await conn.fetchval(
            """INSERT INTO declarations (taxpayer_id, form_code, period_year, period_no, calc, status)
               VALUES ($1,'200.00',$2,$3,$4,'draft')
               ON CONFLICT (taxpayer_id, form_code, period_year, period_no, kind)
               DO UPDATE SET calc=EXCLUDED.calc, updated_at=now(),
                 status=CASE WHEN declarations.status IN ('signed','submitted','accepted')
                             THEN declarations.status ELSE 'draft' END
               RETURNING id""", taxpayer_id, year, quarter, json.dumps(calc_json))
    logger.info("200.00 %s: %d работников, в бюджет %s (decl %s)",
                calc_json["period"], calc["employees"], calc["total_to_budget"], decl_id)
    return {"declaration_id": str(decl_id), **calc_json}
