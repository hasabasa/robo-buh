"""Сборка XML форм ОУР 300.00 (НДС) и 100.00 (КПН): свод → ФЛК → XML → declarations.xml."""

from __future__ import annotations

import json
import logging
from uuid import UUID

from ..core.database import get_pool
from .xml_300 import build_300_xml, flk_300
from .xml_100 import build_100_xml, flk_100

logger = logging.getLogger(__name__)


async def _load(declaration_id: UUID):
    pool = await get_pool()
    async with pool.acquire() as conn:
        decl = await conn.fetchrow(
            "SELECT taxpayer_id, period_year, period_no, calc, status FROM declarations WHERE id=$1",
            declaration_id)
        if not decl:
            raise ValueError("Декларация не найдена")
        if decl["status"] in ("signed", "submitted", "accepted"):
            raise ValueError(f"Декларация в статусе '{decl['status']}' — XML не пересобирается")
        tp = await conn.fetchrow(
            "SELECT kind, iin_bin, name, ugd_code FROM taxpayers WHERE id=$1", decl["taxpayer_id"])
    calc = decl["calc"] if isinstance(decl["calc"], dict) else json.loads(decl["calc"])
    return decl, tp, calc


async def _save(declaration_id: UUID, form: str, xml_text: str, errors, warns) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE declarations SET xml=$2, xsd_version=$3, flk_report=$4, updated_at=now() WHERE id=$1",
            declaration_id, xml_text, form, json.dumps({"errors": errors, "warnings": warns}))


async def generate_300_xml(declaration_id: UUID) -> dict:
    """XML 300.00 (НДС) для черновой декларации."""
    decl, tp, calc = await _load(declaration_id)
    errors, warns = flk_300(calc)
    if errors:
        return {"ok": False, "flk_errors": errors, "flk_warnings": warns}
    xml_text = build_300_xml(calc, iin_bin=tp["iin_bin"], name=tp["name"],
                             year=decl["period_year"], quarter=decl["period_no"],
                             is_ip=(tp["kind"] == "ip"), ugd_code=tp["ugd_code"]).decode("utf-8")
    await _save(declaration_id, "300.00", xml_text, errors, warns)
    logger.info("300.00 XML собран для декларации %s (%d байт)", declaration_id, len(xml_text))
    return {"ok": True, "flk_warnings": warns, "xml": xml_text}


async def generate_100_xml(declaration_id: UUID) -> dict:
    """XML 100.00 (КПН) для черновой декларации."""
    decl, tp, calc = await _load(declaration_id)
    errors, warns = flk_100(calc)
    if errors:
        return {"ok": False, "flk_errors": errors, "flk_warnings": warns}
    xml_text = build_100_xml(calc, iin_bin=tp["iin_bin"], name=tp["name"],
                             year=decl["period_year"], is_ip=(tp["kind"] == "ip"),
                             ugd_code=tp["ugd_code"]).decode("utf-8")
    await _save(declaration_id, "100.00", xml_text, errors, warns)
    logger.info("100.00 XML собран для декларации %s (%d байт)", declaration_id, len(xml_text))
    return {"ok": True, "flk_warnings": warns, "xml": xml_text}
