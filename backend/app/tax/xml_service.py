"""Сборка XML 910.00 для декларации: расчёт → ФЛК → XML → сохранение в declarations.xml.

Замыкает поток: income_ledger → расчёт → XML → (готово к) подписи ЭЦП клиента.
"""

from __future__ import annotations

import json
import logging
from datetime import date
from decimal import Decimal
from uuid import UUID

from ..core.database import get_pool
from .flk import check_910
from .simplified_910 import Calc910, calc_910
from .xml_910 import build_910_xml

logger = logging.getLogger(__name__)


def _calc_from_json(cj: dict) -> Calc910:
    """Восстанавливает Calc910 из сохранённого JSON расчёта (declarations.calc)."""
    social = {}
    sj = cj.get("social") or {}
    if sj:
        # пересобираем через calc_910 не нужно — берём готовые числа
        from .social import SocialMonthly
        mm = sj["monthly"]
        social = {
            "monthly": SocialMonthly(
                opv=Decimal(mm["opv"]), opvr=Decimal(mm["opvr"]),
                so=Decimal(mm["so"]), vosms=Decimal(mm["vosms"]),
            ),
            "months": sj["months"], "total": Decimal(sj["total"]),
        }
    return Calc910(
        period=cj["period"], taxpayer_kind="ip" if social else "too",
        turnover=Decimal(cj["turnover"]), rate=Decimal(cj["rate"]),
        income_tax=Decimal(cj["income_tax"]), income_tax_name=cj["income_tax_name"],
        social=social, lines=cj.get("lines", {}),
    )


async def generate_910_xml(declaration_id: UUID) -> dict:
    """Генерирует XML 910.00 для черновой декларации, прогоняет ФЛК, сохраняет xml."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        decl = await conn.fetchrow(
            "SELECT taxpayer_id, period_year, period_no, calc, status FROM declarations WHERE id=$1",
            declaration_id,
        )
        if not decl:
            raise ValueError("Декларация не найдена")
        if decl["status"] in ("signed", "submitted", "accepted"):
            raise ValueError(f"Декларация в статусе '{decl['status']}' — XML не пересобирается")
        tp = await conn.fetchrow(
            "SELECT kind, iin_bin, name, ugd_code FROM taxpayers WHERE id=$1", decl["taxpayer_id"]
        )

    cj = decl["calc"] if isinstance(decl["calc"], dict) else json.loads(decl["calc"])
    calc = _calc_from_json(cj)

    flk = check_910(calc, iin_bin=tp["iin_bin"], ugd_code=tp["ugd_code"])
    if not flk.ok:
        return {"ok": False, "flk_errors": flk.errors, "flk_warnings": flk.warnings}

    xml_bytes = build_910_xml(
        calc,
        iin_bin=tp["iin_bin"], name=tp["name"], year=decl["period_year"],
        half=decl["period_no"], is_ip=(tp["kind"] == "ip"), ugd_code=tp["ugd_code"],
    )
    xml_text = xml_bytes.decode("utf-8")

    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE declarations SET xml=$2, xsd_version='910.00', flk_report=$3, updated_at=now() WHERE id=$1",
            declaration_id, xml_text,
            json.dumps({"errors": flk.errors, "warnings": flk.warnings}),
        )
    logger.info("910.00 XML собран для декларации %s (%d байт, ФЛК warnings=%d)",
                declaration_id, len(xml_bytes), len(flk.warnings))
    return {"ok": True, "flk_warnings": flk.warnings, "xml": xml_text}
