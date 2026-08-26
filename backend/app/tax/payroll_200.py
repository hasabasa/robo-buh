"""Зарплатный движок (форма 200.00, ОУР): налоги/взносы по работникам.

Ставки CONFIRMED 2026 (НК 214-VIII, kz_2026.py). База каждого платежа — стандартная
казахстанская, ФИНАЛЬНО сверить с Правилами заполнения 200.00 v2026:
  удержания с работника: ИПН 10% (база = оклад − ОПВ − ВОСМС − вычет 30 МРП), ОПВ 10%, ВОСМС 2%
  платежи работодателя:  ОПВР 3.5%, СО 5%, ООСМС 3%, соцналог 6%
ИПН прогрессия 15% (свыше ~36,7 млн ₸/год) применяется нарастающим итогом за год — в MVP
считаем помесячно 10%, годовой перерасчёт 15% пометим отдельной задачей.
Взаимозачёт соцналога и соцотчислений в 2026 ОТМЕНЁН (платятся отдельно).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from ..taxconfig.kz_2026 import KZ_2026


def _r(x: Decimal) -> Decimal:
    return Decimal(str(x)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def _clamp(v: Decimal, lo_mzp: int | None, hi_mzp: int) -> Decimal:
    mzp = KZ_2026.mzp
    v = min(v, mzp * hi_mzp)
    if lo_mzp is not None:
        v = max(v, mzp * lo_mzp)
    return v


@dataclass
class PayrollMonth:
    salary: Decimal
    opv: Decimal          # ОПВ 10% (работник)
    vosms: Decimal        # ВОСМС 2% (работник)
    ipn: Decimal          # ИПН 10% (работник, после вычетов)
    opvr: Decimal         # ОПВР 3.5% (работодатель)
    so: Decimal           # СО 5% (работодатель)
    oosms: Decimal        # ООСМС 3% (работодатель)
    social_tax: Decimal   # соцналог 6% (работодатель)

    @property
    def employee_withheld(self) -> Decimal:
        return self.ipn + self.opv + self.vosms

    @property
    def employer_paid(self) -> Decimal:
        return self.opvr + self.so + self.oosms + self.social_tax

    @property
    def net_salary(self) -> Decimal:
        return self.salary - self.employee_withheld


def calc_employee_month(salary: Decimal) -> PayrollMonth:
    """Расчёт налогов/взносов по одному работнику за месяц."""
    c = KZ_2026
    s = Decimal(str(salary or 0))

    opv = _r(_clamp(s, None, c.opv_base_max_mzp_emp) * c.opv_employee_rate)
    vosms = _r(_clamp(s, None, c.vosms_base_max_mzp_emp) * c.vosms_employee_rate)

    # ИПН: база = оклад − ОПВ − ВОСМС − вычет 30 МРП, не ниже 0
    deduction = c.mrp * c.ipn_standard_deduction_mrp
    ipn_base = s - opv - vosms - deduction
    ipn = _r(ipn_base * c.ipn_source_rate_low) if ipn_base > 0 else Decimal(0)

    # СО: база = (оклад − ОПВ), кламп 1–7 МЗП
    so = _r(_clamp(s - opv, c.so_base_max_mzp_emp and 1, c.so_base_max_mzp_emp) * c.so_employer_rate)
    opvr = _r(_clamp(s, None, c.opv_base_max_mzp_emp) * c.opvr_employer_rate)
    oosms = _r(_clamp(s, None, c.oosms_base_max_mzp_emp) * c.oosms_employer_rate)
    # соцналог: база = оклад − ОПВ − ВОСМС (взаимозачёт с СО отменён в 2026), не ниже 1 МЗП
    sn_base = max(s - opv - vosms, c.mzp)
    social_tax = _r(sn_base * c.social_tax_employer_rate)

    return PayrollMonth(salary=s, opv=opv, vosms=vosms, ipn=ipn,
                        opvr=opvr, so=so, oosms=oosms, social_tax=social_tax)


def calc_200_quarter(salaries: list[Decimal], months: int = 3) -> dict:
    """Свод 200.00 за квартал: суммирует по работникам × месяцам (оклады постоянны)."""
    per_emp = [calc_employee_month(s) for s in salaries]
    agg = {k: Decimal(0) for k in
           ("ipn", "opv", "vosms", "opvr", "so", "oosms", "social_tax")}
    for m in per_emp:
        for k in agg:
            agg[k] += getattr(m, k) * months
    total_to_budget = sum(agg.values())
    return {
        "employees": len(salaries), "months": months,
        **{k: str(v) for k, v in agg.items()},
        "employee_withheld_total": str(agg["ipn"] + agg["opv"] + agg["vosms"]),
        "employer_paid_total": str(agg["opvr"] + agg["so"] + agg["oosms"] + agg["social_tax"]),
        "total_to_budget": str(total_to_budget),
    }
