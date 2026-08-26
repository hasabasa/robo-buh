"""Тесты парсера PDF-выписки Kaspi (row→op) + тюнинг КНП на реальных строках.

Строки — по образцу реальной выписки Kaspi (ТОО), сам PDF в репо не коммитим.
"""
from decimal import Decimal

from app.ingestion.kaspi_bank_pdf import row_to_op, _counterparty, _amount, _date
from app.ingestion.knp_classifier import classify_by_knp

H = ["Номер документа", "Дата операции", "Дебет", "Кредит", "Наименование", "ИИК", "БИК", "КНП", "Назн."]
NUMROW = ["1", "2", "3", "4", "5", "6", "7", "8", "9"]

# значения синтетические (формат по образцу выписки Kaspi; реальные счета/номера не используем)
SALE = ["1001", "14.08.2026 19:57:59", "", "50 000", 'АО "KASPI BANK" БИН/ИИН 000000000000',
        "KZ00TEST000000000001", "CASPKZKA", "190", "Продажи с Kaspi.kz за 14/08/2026"]
TRANSFER = ["1002", "09.07.2026 10:00:00", "", "12 000", "Перевод со счета TESTWALLET-001",
            "KZ00TEST000000000002", "CASPKZKA", "390", "Перевод со счета TESTWALLET-001"]
WITHDRAW = ["1003", "14.08.2026 19:58:47", "50 000", "", 'АО "KASPI BANK" БИН/ИИН 000000000000',
            "KZ00TEST000000000003", "CASPKZKA", "341", "Снятия наличных в Kaspi Банкомат"]
SERVICE = ["1004", "08.08.2026 12:00:00", "", "471 000", "ТОО Клиент БИН/ИИН 000000000012",
           "KZ00TEST000000000004", "HSBKKZKX", "859", "Согласно счета на оплату № 11"]


def test_skips_header_and_numbering():
    assert row_to_op(H) is None
    assert row_to_op(NUMROW) is None
    assert row_to_op(["", "", "", "", "", "", "", "", ""]) is None


def test_kaspi_sale_is_income():
    op = row_to_op(SALE)
    assert op["payment_channel"] == "credit" and op["is_income"] is True
    assert op["amount"] == Decimal("50000")
    assert op["knp"] == "190"
    assert op["op_date"] == "2026-08-14"
    assert op["counterparty_bin_iin"] == "000000000000"
    assert op["external_id"] == "kaspi:1001:2026-08-14"


def test_own_transfer_not_income():
    op = row_to_op(TRANSFER)
    assert op["payment_channel"] == "credit" and op["is_income"] is False  # КНП 390 — перевод


def test_withdrawal_is_debit_not_income():
    op = row_to_op(WITHDRAW)
    assert op["payment_channel"] == "debit" and op["is_income"] is False


def test_service_income_range():
    op = row_to_op(SERVICE)
    assert op["is_income"] is True and op["amount"] == Decimal("471000")


def test_knp_tuning():
    assert classify_by_knp("190", "credit").is_income is True    # Продажи с Kaspi
    assert classify_by_knp("390", "credit").is_income is False   # перевод
    assert classify_by_knp("341", "debit").is_income is False


def test_helpers():
    assert _amount("50 000") == Decimal("50000")
    assert _amount("1 506 100,50") == Decimal("1506100.50")
    assert _date("14.08.2026 19:57:59") == "2026-08-14"
    assert _counterparty('АО "KASPI BANK" БИН/ИИН 000000000012') == ('АО "KASPI BANK"', "000000000012")
