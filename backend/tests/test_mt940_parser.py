"""Тест MT940-парсера на синтетической выписке РК (доход + свой перевод + расход-налог)."""

from decimal import Decimal

from app.ingestion.mt940_parser import parse_mt940

SAMPLE = """:20:STMT001
:25:KZ75125KZT1001300335
:28C:1/1
:60F:C260701KZT0,00
:61:2607150715C700000,00NTRFNONREF
:86:KNP 710 оплата за товары от ТОО Ромашка БИН 180540021234
:61:2608200820C50000,00NTRFNONREF
:86:KNP 342 перевод между своими счетами
:61:2609100910D30000,00NTRFNONREF
:86:KNP 911 оплата налога
:62F:C260930KZT720000,00"""


def test_parse_and_classify():
    ops = parse_mt940(SAMPLE)
    assert len(ops) == 3

    by_amount = {o["amount"]: o for o in ops}

    sale = by_amount[Decimal("700000.00")]
    assert sale["is_income"] is True
    assert sale["knp"] == "710"
    assert sale["counterparty_bin_iin"] == "180540021234"
    assert sale["payment_channel"] == "credit"

    transfer = by_amount[Decimal("50000.00")]
    assert transfer["is_income"] is False        # свой перевод (342)

    tax = by_amount[Decimal("30000.00")]
    assert tax["is_income"] is False             # расход
    assert tax["payment_channel"] == "debit"

    # суммарный доход = только продажа
    income = sum(o["amount"] for o in ops if o["is_income"] is True)
    assert income == Decimal("700000.00")
