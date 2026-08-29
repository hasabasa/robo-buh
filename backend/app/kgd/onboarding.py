"""Гейт онбординга и валидация налогоплательщика через справки КГД (Тир-1).

При заведении клиента: подтвердить, что БИН/ИИН реальный и действующий, вытащить УГД
(нужен для формы), проверить статус НДС. Валидация контрагентов из выписки — тем же клиентом.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import UUID

from ..core.database import get_pool
from .portal_client import KgdPortalClient, TaxpayerInfo


async def validate_taxpayer(code: str, kind: str = "too") -> dict:
    """Проверка клиента при онбординге. kind: 'too'→UL, 'ip'→IP."""
    tt = "UL" if kind == "too" else "IP"
    client = KgdPortalClient()
    info: TaxpayerInfo = await client.taxpayer(code, tt)

    if not info.found:
        return {"ok": False, "reason": "Налогоплательщик не найден в реестре КГД", "code": code}

    warnings = []
    if info.end_date:
        warnings.append(f"Внимание: снят с учёта/ликвидирован ({info.end_reason or info.end_date})")

    nds = await client.is_nds_payer(code)
    if nds:
        warnings.append("Клиент стоит на учёте по НДС — режим упрощёнки неприменим, нужен ОУР+НДС")

    return {
        "ok": True,
        "code": info.code,
        "name": info.name,
        "taxpayer_type": info.taxpayer_type,
        "begin_date": info.begin_date,
        "end_date": info.end_date,
        "end_reason": info.end_reason,
        "active": not info.end_date,
        "ugd_code": info.ugd_code,          # автозаполнение реквизита формы
        "ugd_name": info.ugd_name,
        "is_nds_payer": nds,
        "warnings": warnings,
    }


async def sync_taxpayer_card(taxpayer_id: UUID) -> dict:
    """Тянет карточку из КГД по ИИН/БИН и сохраняет её в taxpayers.requisites (+ УГД)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        tp = await conn.fetchrow("SELECT iin_bin, kind FROM taxpayers WHERE id=$1", taxpayer_id)
        if not tp:
            raise ValueError("Налогоплательщик не найден")
    card = await validate_taxpayer(tp["iin_bin"], tp["kind"])
    if not card.get("ok"):
        return card
    card["synced_at"] = datetime.now(timezone.utc).isoformat()

    async with pool.acquire() as conn:
        await conn.execute(
            """UPDATE taxpayers SET
                 requisites = COALESCE(requisites,'{}'::jsonb) || jsonb_build_object('kgd_card',$2::jsonb),
                 ugd_code = COALESCE(ugd_code, $3),
                 name = COALESCE(NULLIF($4,''), name)
               WHERE id=$1""",
            taxpayer_id, json.dumps(card), card.get("ugd_code"), card.get("name") or "")
    return card
