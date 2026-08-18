"""Юнит-тесты налогового движка 910.00 и соцплатежей (офлайн, детерминированные)."""

from datetime import date
from decimal import Decimal

from app.tax.simplified_910 import calc_910, effective_rate, snr_limit_status
from app.tax.social import social_monthly


def test_effective_rate_default_and_clamp():
    assert effective_rate(None) == Decimal("0.04")      # базовая
    assert effective_rate(3) == Decimal("0.03")          # маслихат 3%
    assert effective_rate(2) == Decimal("0.02")          # нижняя граница
    assert effective_rate(6) == Decimal("0.06")          # верхняя граница
    assert effective_rate(1) == Decimal("0.02")          # ниже 2% → кламп
    assert effective_rate(9) == Decimal("0.06")          # выше 6% → кламп


def test_ipn_from_turnover():
    c = calc_910(turnover=Decimal("8450000"), period="H2-2026", taxpayer_kind="ip")
    assert c.income_tax_name == "ИПН"
    assert c.income_tax == Decimal("338000")             # 8 450 000 × 4%
    assert c.rate == Decimal("0.04")


def test_too_uses_kpn():
    c = calc_910(turnover=Decimal("1000000"), period="H1-2026", taxpayer_kind="too")
    assert c.income_tax_name == "КПН"
    assert c.income_tax == Decimal("40000")
    assert c.social == {}                                # у ТОО соцплатежи за себя не считаются


def test_maslikhat_reduced_rate():
    c = calc_910(turnover=Decimal("1000000"), period="H1-2026", maslikhat_rate=Decimal("2"))
    assert c.income_tax == Decimal("20000")              # 2%


def test_social_minimum_with_opvr():
    # ИП рождён после 1975 → ОПВР есть; база 1 МЗП (85 000)
    m = social_monthly(birth_date=date(1990, 5, 1))
    assert m.opv == Decimal("8500")     # 10% × 85000
    assert m.opvr == Decimal("2975")    # 3.5% × 85000
    assert m.so == Decimal("4250")      # 5% × 85000
    assert m.vosms == Decimal("5950")   # фикс
    assert m.total == Decimal("21675")


def test_social_no_opvr_before_1975():
    m = social_monthly(birth_date=date(1970, 1, 1))
    assert m.opvr == Decimal("0")
    assert m.total == Decimal("18700")  # без ОПВР


def test_snr_limit_zones():
    # лимит 600 000 × 4325 = 2 595 000 000
    assert snr_limit_status(Decimal("1000000000")).zone == "green"
    assert snr_limit_status(Decimal("2300000000")).zone == "yellow"
    assert snr_limit_status(Decimal("2600000000")).zone == "red"
