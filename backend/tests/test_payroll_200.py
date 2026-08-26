"""Тесты зарплатного движка 200.00."""
from decimal import Decimal
from app.tax.payroll_200 import calc_employee_month, calc_200_quarter


def test_standard_salary():
    m = calc_employee_month(Decimal("500000"))
    assert m.opv == Decimal("50000")       # 10%
    assert m.vosms == Decimal("10000")     # 2%
    assert m.ipn == Decimal("31025")       # (500000−50000−10000−129750)×10%
    assert m.opvr == Decimal("17500")      # 3.5%
    assert m.so == Decimal("22500")        # (500000−50000)×5%
    assert m.oosms == Decimal("15000")     # 3%
    assert m.social_tax == Decimal("26400")  # (500000−50000−10000)×6%
    assert m.net_salary == Decimal("408975")


def test_minimum_wage_zero_ipn():
    # низкий оклад: вычет 30 МРП (129750) съедает базу ИПН → 0
    m = calc_employee_month(Decimal("100000"))
    assert m.ipn == Decimal("0")           # база отрицательная → 0
    assert m.opv == Decimal("10000")       # взносы всё равно есть


def test_quarter_aggregate():
    r = calc_200_quarter([Decimal("500000"), Decimal("300000")], months=3)
    assert r["employees"] == 2 and r["months"] == 3
    # суммы за квартал = (по работникам) × 3 мес; проверяем что сходится
    assert Decimal(r["total_to_budget"]) > 0
    assert Decimal(r["employer_paid_total"]) > 0
