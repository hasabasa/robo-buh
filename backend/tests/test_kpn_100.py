"""Тесты движка КПН 100.00."""
from decimal import Decimal
from app.tax.kpn_100 import calc_kpn_100


def test_basic_kpn():
    r = calc_kpn_100(gross_income=Decimal("50000000"), deductions=Decimal("38000000"))
    assert r.taxable_income == Decimal("12000000")
    assert r.kpn == Decimal("2400000")     # 12млн × 20%


def test_advances_reduce_payable():
    r = calc_kpn_100(gross_income=Decimal("50000000"), deductions=Decimal("38000000"),
                     advances_paid=Decimal("1500000"))
    assert r.kpn_payable == Decimal("900000")   # 2.4млн − 1.5млн


def test_loss_carry_forward():
    r = calc_kpn_100(gross_income=Decimal("10000000"), deductions=Decimal("12000000"))
    assert r.kpn == Decimal("0")
    assert r.loss_carry_forward == Decimal("2000000")


def test_prior_loss_offsets():
    r = calc_kpn_100(gross_income=Decimal("20000000"), deductions=Decimal("15000000"),
                     prior_losses=Decimal("2000000"))
    assert r.taxable_income == Decimal("3000000")   # 5млн − 2млн убыток
    assert r.kpn == Decimal("600000")
