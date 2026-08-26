"""Тест парсера ЭСФ: направление по БИН + извлечение НДС."""
from decimal import Decimal
from app.ingestion.esf_parser import parse_esf_invoices

VAT_INVOICE = """<?xml version="1.0" encoding="UTF-8"?>
<esf:invoiceContainer xmlns:esf="esf"><invoiceSet><v2:invoice xmlns:v2="v2.esf">
<num>900000111</num><date>10.02.2026</date><turnoverDate>10.02.2026</turnoverDate>
<sellers><seller><tin>111111111111</tin><name>ТОО Опт-бутик</name></seller></sellers>
<customers><customer><tin>222222222222</tin><name>ТОО Ресторан</name></customer></customers>
<totalTurnoverSize>5000000</totalTurnoverSize><totalVatSize>800000</totalVatSize>
</v2:invoice></invoiceSet></esf:invoiceContainer>"""


def test_seller_sale_with_vat():
    ops = parse_esf_invoices(VAT_INVOICE, "111111111111")   # мы продавец
    assert len(ops) == 1
    o = ops[0]
    assert o["payment_channel"] == "credit" and o["is_income"] is True
    assert o["amount"] == Decimal("5800000")      # брутто = оборот + НДС
    assert o["vat_amount"] == Decimal("800000")   # исходящий НДС
    assert o["counterparty_name"] == "ТОО Ресторан"
    assert o["esf_id"] == "900000111"


def test_customer_purchase():
    ops = parse_esf_invoices(VAT_INVOICE, "222222222222")   # мы покупатель
    o = ops[0]
    assert o["payment_channel"] == "debit" and o["is_income"] is False
    assert o["vat_amount"] == Decimal("800000")   # входящий НДС к зачёту
    assert o["counterparty_name"] == "ТОО Опт-бутик"


def test_unrelated_bin_goes_to_review():
    ops = parse_esf_invoices(VAT_INVOICE, "999999999999")
    assert ops[0]["is_income"] is None            # ни продавец ни покупатель → сверка
