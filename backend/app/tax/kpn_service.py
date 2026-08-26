"""Расчёт КПН 100.00 из income_ledger: СГД (доходы) − вычеты (расходы) за год → черновик.

Доход = подтверждённые is_income (без НДС). Вычеты = debit-расходы, помеченные is_deductible
(без НДС; закупки у упрощенцев is_deductible=FALSE в вычеты не идут). prior_losses/advances —
из настроек налогоплательщика (пока 0 по умолчанию, задаётся вручную).
"""
from __future__ import annotations
import json, logging
from datetime import date
from decimal import Decimal
from uuid import UUID
from ..core.database import get_pool
from .kpn_100 import calc_kpn_100

logger = logging.getLogger(__name__)


async def compute_kpn_100(taxpayer_id: UUID, year: int,
                          prior_losses: Decimal = Decimal(0),
                          advances_paid: Decimal = Decimal(0)) -> dict:
    d1, d2 = date(year, 1, 1), date(year, 12, 31)
    pool = await get_pool()
    async with pool.acquire() as conn:
        tp = await conn.fetchrow("SELECT kind FROM taxpayers WHERE id=$1", taxpayer_id)
        if not tp:
            raise ValueError("Налогоплательщик не найден")
        # СГД: доходы без НДС
        income = await conn.fetchval(
            """SELECT COALESCE(SUM(amount - COALESCE(vat_amount,0)),0) FROM income_ledger
               WHERE taxpayer_id=$1 AND op_date BETWEEN $2 AND $3
                 AND status='confirmed' AND is_income IS TRUE""", taxpayer_id, d1, d2)
        # вычеты: расходы без НДС, вычитаемые
        ded = await conn.fetchval(
            """SELECT COALESCE(SUM(amount - COALESCE(vat_amount,0)),0) FROM income_ledger
               WHERE taxpayer_id=$1 AND op_date BETWEEN $2 AND $3
                 AND status='confirmed' AND payment_channel='debit' AND is_deductible IS TRUE""",
            taxpayer_id, d1, d2)
        # справочно: невычитаемые расходы (закупки у упрощенцев и пр.)
        nonded = await conn.fetchval(
            """SELECT COALESCE(SUM(amount - COALESCE(vat_amount,0)),0) FROM income_ledger
               WHERE taxpayer_id=$1 AND op_date BETWEEN $2 AND $3
                 AND status='confirmed' AND payment_channel='debit' AND is_deductible IS FALSE""",
            taxpayer_id, d1, d2)

    calc = calc_kpn_100(year=year, gross_income=Decimal(str(income)),
                        deductions=Decimal(str(ded)), non_deductible=Decimal(str(nonded)),
                        prior_losses=prior_losses, advances_paid=advances_paid)
    calc_json = {"year": year, "gross_income": str(calc.gross_income),
                 "deductions": str(calc.deductions), "non_deductible": str(calc.non_deductible),
                 "taxable_income": str(calc.taxable_income), "kpn": str(calc.kpn),
                 "kpn_payable": str(calc.kpn_payable), "kpn_overpaid": str(calc.kpn_overpaid),
                 "loss_carry_forward": str(calc.loss_carry_forward), "lines": calc.lines}

    async with pool.acquire() as conn:
        decl_id = await conn.fetchval(
            """INSERT INTO declarations (taxpayer_id, form_code, period_year, period_no, calc, status)
               VALUES ($1,'100.00',$2,1,$3,'draft')
               ON CONFLICT (taxpayer_id, form_code, period_year, period_no, kind)
               DO UPDATE SET calc=EXCLUDED.calc, updated_at=now(),
                 status=CASE WHEN declarations.status IN ('signed','submitted','accepted')
                             THEN declarations.status ELSE 'draft' END
               RETURNING id""", taxpayer_id, year, json.dumps(calc_json))
    logger.info("100.00 %d: СГД %s − вычеты %s → КПН %s (decl %s)",
                year, calc.gross_income, calc.deductions, calc.kpn, decl_id)
    return {"declaration_id": str(decl_id), **calc_json}
