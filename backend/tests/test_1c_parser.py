"""Тест парсера 1CClientBankExchange: направление по счёту-владельцу + классификация."""

from decimal import Decimal

from app.ingestion.client_bank_1c import parse_1c
from app.ingestion.service import detect_and_parse

OWNER = "KZ75125KZT1001300335"

SAMPLE = f"""1CClientBankExchange
ВерсияФормата=1.03
Кодировка=Windows
Отправитель=Bank
Получатель=ИП Тест
РасчСчет={OWNER}
СекцияДокумент=Платежное поручение
Номер=101
Дата=15.03.2026
Сумма=900000.00
ПлательщикСчет=KZ11111111111111111111
Плательщик=ТОО Ромашка
ПлательщикБИН=180540021234
ПолучательСчет={OWNER}
Получатель=ИП Тест
НазначениеПлатежа=Оплата за товары КНП 710
КонецДокумента
СекцияДокумент=Платежное поручение
Номер=102
Дата=20.03.2026
Сумма=45000.00
ПлательщикСчет={OWNER}
Плательщик=ИП Тест
ПолучательСчет=KZ22222222222222222222
Получатель=Комитет госдоходов
НазначениеПлатежа=Оплата налога КНП 911
КонецДокумента
"""


def test_1c_direction_and_classification():
    ops = parse_1c(SAMPLE)
    assert len(ops) == 2

    sale = next(o for o in ops if o["amount"] == Decimal("900000.00"))
    assert sale["payment_channel"] == "credit"       # владелец — получатель
    assert sale["is_income"] is True                 # КНП 710
    assert sale["knp"] == "710"
    assert sale["counterparty_bin_iin"] == "180540021234"
    assert sale["counterparty_name"] == "ТОО Ромашка"

    tax = next(o for o in ops if o["amount"] == Decimal("45000.00"))
    assert tax["payment_channel"] == "debit"          # владелец — плательщик
    assert tax["is_income"] is False                  # расход


def test_autodetect_1c():
    fmt, ops = detect_and_parse(SAMPLE)
    assert fmt == "bank_1c" and len(ops) == 2
