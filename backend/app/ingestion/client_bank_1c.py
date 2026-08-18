"""Парсер выписки 1CClientBankExchange → нормализованные операции дохода.

Текстовый формат «клиент-банк» (секции СекцияДокумент…КонецДокумента). Направление
операции определяем по счёту-владельцу выписки: если он получатель — приход (credit),
если плательщик — расход (debit). КНП/БИН/ИИК тянем из назначения платежа нашим kz_entities.

На выходе — список dict под UPSERT в income_ledger (source='bank_1c').
"""

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation

from . import kz_entities
from .knp_classifier import classify_by_knp

logger = logging.getLogger(__name__)


def _kv(line: str) -> tuple[str, str] | None:
    if "=" not in line:
        return None
    k, v = line.split("=", 1)
    return k.strip(), v.strip()


def _to_iso(d: str) -> str | None:
    """1С-дата ДД.ММ.ГГГГ → ГГГГ-ММ-ДД."""
    parts = d.split(".")
    if len(parts) == 3 and all(parts):
        dd, mm, yy = parts
        return f"{yy}-{mm.zfill(2)}-{dd.zfill(2)}"
    return None


def _amount(s: str) -> Decimal:
    try:
        return Decimal(s.replace(" ", "").replace(",", "."))
    except (InvalidOperation, AttributeError):
        return Decimal(0)


def parse_1c(content: str) -> list[dict]:
    """Разбирает текст 1CClientBankExchange → операции для income_ledger."""
    lines = content.splitlines()

    # Счёт-владелец выписки: РасчСчет в шапке / СекцияРасчСчет
    owner_acct = ""
    in_doc = False
    doc: dict[str, str] = {}
    docs: list[dict[str, str]] = []

    for raw in lines:
        line = raw.strip()
        if line.startswith("СекцияДокумент"):
            in_doc, doc = True, {}
            continue
        if line.startswith("КонецДокумента"):
            if doc:
                docs.append(doc)
            in_doc, doc = False, {}
            continue
        kv = _kv(line)
        if not kv:
            continue
        k, v = kv
        if not in_doc and k == "РасчСчет" and v and not owner_acct:
            owner_acct = v
        elif in_doc:
            doc[k] = v

    ops: list[dict] = []
    for i, d in enumerate(docs):
        payer_acct = d.get("ПлательщикСчет", "")
        payee_acct = d.get("ПолучательСчет", "")
        # direction относительно владельца выписки
        if owner_acct and payee_acct == owner_acct:
            direction, cp_name = "credit", d.get("Плательщик", "")
            cp_acct = payer_acct
        elif owner_acct and payer_acct == owner_acct:
            direction, cp_name = "debit", d.get("Получатель", "")
            cp_acct = payee_acct
        else:
            # владелец не определён — по наличию получателя-нас не решаем, ставим credit-кандидат
            direction, cp_name, cp_acct = "credit", d.get("Плательщик", ""), payer_acct

        purpose = d.get("НазначениеПлатежа", "")
        # КНП: отдельное поле или из текста назначения
        knp = d.get("КодНазначенияПлатежа") or d.get("КНП")
        ent = kz_entities.extract(f"{purpose} {d.get('ПлательщикБИН','')} {d.get('ПлательщикИНН','')}")
        if not knp:
            knp = ent["knp"][0] if ent["knp"] else None
        cp_bin = d.get("ПлательщикБИН") or d.get("ПолучательБИН") or (ent["bin"][0] if ent["bin"] else None)
        cp_iin = ent["iin"][0] if ent["iin"] else None

        amount = _amount(d.get("Сумма", "0"))
        cls = classify_by_knp(knp, direction)
        op_date = _to_iso(d.get("Дата", ""))

        ops.append({
            "source": "bank_1c",
            "external_id": f"1c:{d.get('Номер', i)}:{d.get('Дата', '')}:{amount}",
            "op_date": op_date,
            "amount": amount,
            "payment_channel": direction,
            "counterparty_name": cp_name or None,
            "counterparty_bin_iin": cp_bin or cp_iin,
            "counterparty_iik": cp_acct or None,
            "knp": knp,
            "purpose_text": purpose,
            "is_income": cls.is_income,
            "confidence": cls.confidence,
            "classified_by": cls.classified_by,
        })

    logger.info("1C: разобрано операций %d (доход %d, не-доход %d, на сверку %d)",
                len(ops),
                sum(1 for o in ops if o["is_income"] is True),
                sum(1 for o in ops if o["is_income"] is False),
                sum(1 for o in ops if o["is_income"] is None))
    return ops
