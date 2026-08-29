"""Сборка XML 200.00 для декларации: свод → локальный ФЛК → XML → declarations.xml."""

from __future__ import annotations

import json
import logging
from uuid import UUID

from ..core.database import get_pool
from .xml_200 import build_200_xml, flk_200

logger = logging.getLogger(__name__)


async def generate_200_xml(declaration_id: UUID) -> dict:
    """Генерирует XML 200.00 для черновой декларации, прогоняет ФЛК, сохраняет xml."""
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
    errors, warns = flk_200(calc)
    if errors:
        return {"ok": False, "flk_errors": errors, "flk_warnings": warns}

    xml_bytes = build_200_xml(
        calc, iin_bin=tp["iin_bin"], name=tp["name"], year=decl["period_year"],
        quarter=decl["period_no"], is_ip=(tp["kind"] == "ip"), ugd_code=tp["ugd_code"])
    xml_text = xml_bytes.decode("utf-8")

    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE declarations SET xml=$2, xsd_version='200.00', flk_report=$3, updated_at=now() WHERE id=$1",
            declaration_id, xml_text, json.dumps({"errors": errors, "warnings": warns}))
    logger.info("200.00 XML собран для декларации %s (%d байт, ФЛК warnings=%d)",
                declaration_id, len(xml_bytes), len(warns))
    return {"ok": True, "flk_warnings": warns, "xml": xml_text}
