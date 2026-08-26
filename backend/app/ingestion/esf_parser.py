"""Парсер счетов-фактур ЭСФ (invoiceContainer) → операции для income_ledger.

Читает выгрузку ЭСФ (esf:invoiceContainer / invoiceSet / invoice) и превращает каждый
счёт в строку ledger с НДС. Направление определяется по БИН владельца: он продавец →
реализация (доход, исходящий НДС); он покупатель → закупка (расход, входящий НДС к зачёту).

Namespace-agnostic (local-name) — устойчиво к версиям инвойса v1/v2. Структура сверена по
InvoiceV2.xsd и примеру из SDK ЭСФ.
"""

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation

from lxml import etree

logger = logging.getLogger(__name__)


def _txt(node, name: str) -> str | None:
    """Первый потомок с local-name==name (на любой глубине)."""
    r = node.xpath(f".//*[local-name()=$n]", n=name)
    return r[0].text.strip() if r and r[0].text else None


def _dec(v: str | None) -> Decimal:
    if not v:
        return Decimal(0)
    try:
        return Decimal(str(v).replace(" ", "").replace(",", "."))
    except (InvalidOperation, AttributeError):
        return Decimal(0)


def _iso(d: str | None) -> str | None:
    """ДД.ММ.ГГГГ → ГГГГ-ММ-ДД."""
    if not d:
        return None
    p = d.split(".")
    return f"{p[2]}-{p[1].zfill(2)}-{p[0].zfill(2)}" if len(p) == 3 else None


def _party(inv, kind: str) -> tuple[str | None, str | None]:
    """(tin, name) продавца/покупателя. kind: 'seller' | 'customer'."""
    nodes = inv.xpath(f".//*[local-name()=$k]", k=kind)
    if not nodes:
        return None, None
    node = nodes[0]
    return _txt(node, "tin"), _txt(node, "name")


def parse_esf_invoices(xml: str | bytes, own_bin: str) -> list[dict]:
    """Разбирает выгрузку ЭСФ → операции для income_ledger (source='esf')."""
    if isinstance(xml, str):
        xml = xml.encode("utf-8")
    root = etree.fromstring(xml)
    invoices = root.xpath("//*[local-name()='invoice']")
    ops: list[dict] = []
    for inv in invoices:
        num = _txt(inv, "num") or _txt(inv, "registrationNumber")
        op_date = _iso(_txt(inv, "turnoverDate") or _txt(inv, "date"))
        turnover = _dec(_txt(inv, "totalTurnoverSize"))
        vat = _dec(_txt(inv, "totalVatSize"))

        seller_tin, seller_name = _party(inv, "seller")
        cust_tin, cust_name = _party(inv, "customer")

        if own_bin and seller_tin == own_bin:
            direction, is_income = "credit", True          # мы продавец → реализация
            cp_tin, cp_name = cust_tin, cust_name
        elif own_bin and cust_tin == own_bin:
            direction, is_income = "debit", False           # мы покупатель → закупка
            cp_tin, cp_name = seller_tin, seller_name
        else:
            # владелец не совпал ни с кем — на ручную разметку
            direction, is_income = "credit", None
            cp_tin, cp_name = seller_tin, seller_name

        ops.append({
            "source": "esf",
            "external_id": f"esf:{num}",
            "esf_id": num,
            "op_date": op_date,
            "amount": turnover + vat,                        # брутто (с НДС)
            "vat_amount": vat if vat > 0 else None,
            "vat_rate": None,
            "payment_channel": direction,
            "counterparty_name": cp_name,
            "counterparty_bin_iin": cp_tin,
            "knp": None,
            "purpose_text": f"ЭСФ {num}",
            "is_income": is_income,
            "confidence": 0.98 if is_income is not None else 0.0,
            "classified_by": "esf" if is_income is not None else "unknown",
            # для КПН: закупка вычитаема, если продавец не на упрощёнке — уточняется отдельно
            "is_deductible": (False if is_income is True else None),
        })
    logger.info("ЭСФ: разобрано счетов %d (реализация %d, закупка %d, на сверку %d)",
                len(ops), sum(1 for o in ops if o["is_income"] is True),
                sum(1 for o in ops if o["is_income"] is False),
                sum(1 for o in ops if o["is_income"] is None))
    return ops
