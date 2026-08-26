"""Тесты движка НДС 300.00."""
from decimal import Decimal
from app.tax.vat_300 import calc_vat_300, vat_from_net, vat_from_gross, quarter_bounds


def test_vat_extract():
    assert vat_from_net(Decimal("1000000")) == Decimal("160000")     # 16% сверху
    assert vat_from_gross(Decimal("1160000")) == Decimal("160000")   # 16/116 из цены с НДС


def test_payable_positive():
    r = calc_vat_300(period="Q1-2026", output_vat=Decimal("500000"),
                     input_vat_creditable=Decimal("300000"))
    assert r.vat_payable == Decimal("200000")     # 500к − 300к
    assert r.vat_carry_forward == Decimal("0")


def test_excess_carry_forward():
    # входящий > исходящий → к уплате 0, превышение переносится
    r = calc_vat_300(period="Q2-2026", output_vat=Decimal("200000"),
                     input_vat_creditable=Decimal("350000"))
    assert r.vat_payable == Decimal("0")
    assert r.vat_carry_forward == Decimal("150000")


def test_output_from_turnover():
    r = calc_vat_300(period="Q1-2026", taxable_turnover=Decimal("1000000"))
    assert r.output_vat == Decimal("160000")      # 1млн × 16%
    assert r.rate == Decimal("0.16")


def test_quarter_bounds():
    d1, d2 = quarter_bounds(2026, 3)
    assert str(d1) == "2026-07-01" and str(d2) == "2026-09-30"
