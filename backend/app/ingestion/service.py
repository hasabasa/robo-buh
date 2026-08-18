"""Приём выписки в income_ledger: парс → классификация → идемпотентный UPSERT.

Уверенно классифицированные операции (knp_rule/direction) → status='confirmed' (учитываются
в расчёте налога). Неопознанные (is_income=None) → status='pending' (очередь ручной сверки,
в оборот не попадают, пока человек не подтвердит).
"""

from __future__ import annotations

import json
import logging
from datetime import date
from decimal import Decimal
from uuid import UUID

from ..core.database import get_pool
from .client_bank_1c import parse_1c
from .mt940_parser import parse_mt940

logger = logging.getLogger(__name__)


def _status_for(op: dict) -> str:
    return "confirmed" if op.get("classified_by") in ("knp_rule", "direction") else "pending"


def detect_and_parse(content: str) -> tuple[str, list[dict]]:
    """Автоопределение формата выписки → (формат, операции)."""
    head = content.lstrip()[:200]
    if head.startswith("1CClientBankExchange"):
        return "bank_1c", parse_1c(content)
    if ":20:" in content[:400] or ":61:" in content:
        return "bank_mt940", parse_mt940(content)
    raise ValueError("Не распознан формат выписки (ожидается MT940 или 1CClientBankExchange)")


async def _upsert_ops(taxpayer_id: UUID, ops: list[dict]) -> dict:
    """Идемпотентный UPSERT разобранных операций в income_ledger + сводка."""
    if not ops:
        return {"imported": 0, "income": 0, "non_income": 0, "review": 0}
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            for op in ops:
                await conn.execute(
                    """
                    INSERT INTO income_ledger
                        (taxpayer_id, source, external_id, op_date, amount, payment_channel,
                         counterparty_name, counterparty_bin_iin, counterparty_iik, knp, purpose_text,
                         is_income, confidence, classified_by, status, raw_payload)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16)
                    ON CONFLICT (taxpayer_id, source, external_id) DO UPDATE SET
                        amount = EXCLUDED.amount,
                        is_income = EXCLUDED.is_income,
                        confidence = EXCLUDED.confidence,
                        classified_by = EXCLUDED.classified_by,
                        status = EXCLUDED.status,
                        knp = EXCLUDED.knp,
                        purpose_text = EXCLUDED.purpose_text
                    """,
                    taxpayer_id, op["source"], op["external_id"],
                    date.fromisoformat(op["op_date"]) if op.get("op_date") else None,
                    Decimal(str(op["amount"])), op.get("payment_channel"),
                    op.get("counterparty_name"),
                    op.get("counterparty_bin_iin"), op.get("counterparty_iik"),
                    op.get("knp"), op.get("purpose_text"),
                    op["is_income"], op.get("confidence"), op.get("classified_by"),
                    _status_for(op), json.dumps(op, default=str),
                )
    return {
        "imported": len(ops),
        "income": sum(1 for o in ops if o["is_income"] is True),
        "non_income": sum(1 for o in ops if o["is_income"] is False),
        "review": sum(1 for o in ops if o["is_income"] is None),
    }


async def ingest_statement(taxpayer_id: UUID, content: str) -> dict:
    """Автоопределяет формат выписки (MT940/1С), разбирает и складывает в income_ledger."""
    fmt, ops = detect_and_parse(content)
    summary = await _upsert_ops(taxpayer_id, ops)
    summary["format"] = fmt
    logger.info("Выписка %s в income_ledger %s: %s", fmt, taxpayer_id, summary)
    return summary


async def ingest_mt940(taxpayer_id: UUID, content: str) -> dict:
    """Совместимость: разбор строго MT940."""
    return await _upsert_ops(taxpayer_id, parse_mt940(content))
