"""Расчёт НДС 300.00 из income_ledger: агрегирует исходящий/входящий НДС за квартал.

Исходящий НДС — с продаж (credit-операции с vat_amount).
Входящий к зачёту — с закупок (debit-операции с vat_amount), только валидные к зачёту
(есть ЭСФ / is_deductible ≠ FALSE). Если vat_amount не проставлен, но есть vat_rate —
можно доисчислить; иначе операция не участвует в НДС (пойдёт на ручную разметку).
"""

from __future__ import annotations

import json
import logging
from decimal import Decimal
from uuid import UUID

from ..core.database import get_pool
from .vat_300 import Vat300, calc_vat_300, quarter_bounds

logger = logging.getLogger(__name__)


async def compute_vat_300(taxpayer_id: UUID, year: int, quarter: int) -> dict:
    """Считает НДС 300.00 за квартал из income_ledger и сохраняет черновик декларации."""
    d1, d2 = quarter_bounds(year, quarter)
    pool = await get_pool()
    async with pool.acquire() as conn:
        tp = await conn.fetchrow("SELECT kind FROM taxpayers WHERE id=$1", taxpayer_id)
        if not tp:
            raise ValueError("Налогоплательщик не найден")

        # исходящий НДС: продажи (доход, credit) с проставленным НДС
        out = await conn.fetchrow(
            """
            SELECT COALESCE(SUM(vat_amount),0) AS vat,
                   COALESCE(SUM(amount - COALESCE(vat_amount,0)),0) AS net
            FROM income_ledger
            WHERE taxpayer_id=$1 AND op_date BETWEEN $2 AND $3
              AND status='confirmed' AND is_income IS TRUE AND vat_amount IS NOT NULL
            """, taxpayer_id, d1, d2)

        # входящий НДС к зачёту: закупки (debit) с НДС и валидные к зачёту
        inp = await conn.fetchval(
            """
            SELECT COALESCE(SUM(vat_amount),0) FROM income_ledger
            WHERE taxpayer_id=$1 AND op_date BETWEEN $2 AND $3
              AND status='confirmed' AND payment_channel='debit'
              AND vat_amount IS NOT NULL AND is_deductible IS NOT FALSE
            """, taxpayer_id, d1, d2)

    calc: Vat300 = calc_vat_300(
        period=f"Q{quarter}-{year}",
        taxable_turnover=Decimal(str(out["net"])),
        output_vat=Decimal(str(out["vat"])),
        input_vat_creditable=Decimal(str(inp)),
    )

    calc_json = {
        "period": calc.period, "taxable_turnover": str(calc.taxable_turnover),
        "output_vat": str(calc.output_vat), "input_vat_creditable": str(calc.input_vat_creditable),
        "vat_payable": str(calc.vat_payable), "vat_carry_forward": str(calc.vat_carry_forward),
        "rate": str(calc.rate), "lines": calc.lines,
    }

    async with pool.acquire() as conn:
        decl_id = await conn.fetchval(
            """
            INSERT INTO declarations (taxpayer_id, form_code, period_year, period_no, calc, status)
            VALUES ($1,'300.00',$2,$3,$4,'draft')
            ON CONFLICT (taxpayer_id, form_code, period_year, period_no, kind)
            DO UPDATE SET calc=EXCLUDED.calc, updated_at=now(),
                status=CASE WHEN declarations.status IN ('signed','submitted','accepted')
                            THEN declarations.status ELSE 'draft' END
            RETURNING id
            """, taxpayer_id, year, quarter, json.dumps(calc_json))
    logger.info("300.00 %s: исход %s − вход %s = к уплате %s (decl %s)",
                calc.period, calc.output_vat, calc.input_vat_creditable, calc.vat_payable, decl_id)
    return {"declaration_id": str(decl_id), **calc_json}
