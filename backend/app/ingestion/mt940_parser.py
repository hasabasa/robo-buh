"""Парсер банковской выписки MT940 (стандарт НБРК) → нормализованные операции дохода.

Структуру :61:/балансы даёт библиотека mt-940; казахстанскую начинку поля :86:
(КНП, БИН/ИИН контрагента, ИИК) достаём нашим kz_entities. Каждая операция сразу
классифицируется по КНП (доход/не-доход/на сверку).

На выходе — список dict под UPSERT в income_ledger (source='bank_mt940').
"""

from __future__ import annotations

import logging
from decimal import Decimal

from . import kz_entities
from .knp_classifier import classify_by_knp

logger = logging.getLogger(__name__)


def parse_mt940(content: str, *, external_prefix: str = "mt940") -> list[dict]:
    """Разбирает текст MT940 → список операций для income_ledger."""
    import mt940  # тяжёлая зависимость — импорт локальный

    transactions = mt940.parse(content)
    ops: list[dict] = []
    for i, tx in enumerate(transactions):
        d = tx.data
        amount = d.get("amount")
        value = Decimal(str(amount.amount)) if amount is not None else Decimal(0)
        # знак/направление: mt-940 хранит сумму со знаком (D<0, C>0)
        direction = "credit" if value > 0 else "debit"
        purpose = (d.get("transaction_details") or "").replace("\n", " ").strip()

        ent = kz_entities.extract(purpose)
        knp = ent["knp"][0] if ent["knp"] else None
        cp_bin = ent["bin"][0] if ent["bin"] else None
        cp_iin = ent["iin"][0] if ent["iin"] else None
        cp_iik = ent["iik"][0] if ent["iik"] else None

        cls = classify_by_knp(knp, direction)
        entry_date = d.get("entry_date") or d.get("date")

        ops.append({
            "source": "bank_mt940",
            "external_id": f"{external_prefix}:{entry_date}:{i}:{abs(value)}",
            "op_date": str(entry_date) if entry_date else None,
            "amount": abs(value),                 # income_ledger хранит модуль, направление отдельно
            "payment_channel": direction,
            "counterparty_bin_iin": cp_bin or cp_iin,
            "counterparty_iik": cp_iik,
            "knp": knp,
            "purpose_text": purpose,
            "is_income": cls.is_income,
            "confidence": cls.confidence,
            "classified_by": cls.classified_by,
        })
    logger.info("MT940: разобрано операций %d (доход %d, не-доход %d, на сверку %d)",
                len(ops),
                sum(1 for o in ops if o["is_income"] is True),
                sum(1 for o in ops if o["is_income"] is False),
                sum(1 for o in ops if o["is_income"] is None))
    return ops
