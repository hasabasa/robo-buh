"""Парсер PDF-выписки Kaspi Bank (текстовый PDF, детерминированно через pdfplumber).

Выписка Kaspi по расчётному счёту юрлица/ИП — чистая таблица из 9 колонок:
  1 номер документа · 2 дата операции · 3 дебет · 4 кредит · 5 контрагент(+БИН/ИИН) ·
  6 ИИК бенефициара · 7 БИК банка · 8 КНП · 9 назначение платежа
Дебет/кредит в РАЗНЫХ колонках (пусто, если не та сторона) → направление берём по колонке.

Разбор локальный (без внешних OCR) — банковские данные наружу не уходят. Классификация
доход/не-доход — тем же `classify_by_knp`, что и MT940/1С.
"""

from __future__ import annotations

import io
import logging
import re
from datetime import datetime
from decimal import Decimal

import pdfplumber

from .knp_classifier import classify_by_knp

logger = logging.getLogger(__name__)

_BIN = re.compile(r"\b(\d{12})\b")            # БИН/ИИН в колонке контрагента
_HEADER_HINT = "Номер"                         # шапка таблицы
_NUM_ROW = re.compile(r"^\d$")                 # строка нумерации колонок «1 2 3 …»


def is_kaspi_bank_pdf(pdf_bytes: bytes) -> bool:
    """Быстрая проверка: это выписка Kaspi по счёту (по маркерам первой страницы)."""
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            head = (pdf.pages[0].extract_text() or "")[:600]
    except Exception:  # noqa: BLE001
        return False
    return "Лицевой счет" in head and ("КНП" in head or "Назначение платежа" in head)


def _amount(cell: str | None) -> Decimal:
    if not cell:
        return Decimal(0)
    return Decimal(re.sub(r"[^\d.,]", "", cell).replace("\xa0", "").replace(",", ".") or "0")


def _date(cell: str | None) -> str | None:
    """'14.08.2026 19:58:47' → '2026-08-14'."""
    if not cell:
        return None
    m = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", cell)
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else None


def _counterparty(cell: str | None) -> tuple[str | None, str | None]:
    """'АО \"KASPI BANK\" БИН/ИИН 000000000000' → (имя, БИН)."""
    if not cell:
        return None, None
    flat = cell.replace("\n", " ").strip()
    m = _BIN.search(flat)
    cp_bin = m.group(1) if m else None
    name = re.split(r"\s*БИН/ИИН", flat)[0].strip() or None
    return name, cp_bin


def row_to_op(row: list) -> dict | None:
    """Строка таблицы (9 колонок) → операция ledger; None для шапки/нумерации/пустых."""
    if not row or len(row) < 9:
        return None
    docnum = (row[0] or "").strip()
    if not docnum or docnum.startswith(_HEADER_HINT) or _NUM_ROW.match(docnum) or not docnum[0].isdigit():
        return None
    debit, credit = _amount(row[2]), _amount(row[3])
    if debit == 0 and credit == 0:
        return None
    direction = "credit" if credit > 0 else "debit"
    amount = credit if credit > 0 else debit
    op_date = _date(row[1])
    cp_name, cp_bin = _counterparty(row[4])
    knp = (row[7] or "").strip() or None
    cls = classify_by_knp(knp, direction)
    return {
        "source": "bank_pdf",
        "external_id": f"kaspi:{docnum}:{op_date or '?'}",
        "op_date": op_date,
        "amount": amount,
        "payment_channel": direction,
        "counterparty_name": cp_name,
        "counterparty_bin_iin": cp_bin,
        "counterparty_iik": (row[5] or "").strip() or None,
        "knp": knp,
        "purpose_text": (row[8] or "").replace("\n", " ").strip(),
        "is_income": cls.is_income,
        "confidence": cls.confidence,
        "classified_by": cls.classified_by,
        "raw_payload_extra": {"bik": (row[6] or "").strip() or None, "docnum": docnum},
    }


def parse_kaspi_bank_pdf(pdf_bytes: bytes) -> list[dict]:
    """PDF-выписка Kaspi → операции income_ledger (source='bank_pdf')."""
    ops: list[dict] = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables():
                for row in table:
                    op = row_to_op(row)
                    if op:
                        ops.append(op)
    logger.info("Kaspi PDF: разобрано операций %d (доход %d, не-доход %d, на сверку %d)",
                len(ops),
                sum(1 for o in ops if o["is_income"] is True),
                sum(1 for o in ops if o["is_income"] is False),
                sum(1 for o in ops if o["is_income"] is None))
    return ops
