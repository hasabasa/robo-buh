"""Налоговый движок КПН (форма 100.00, ОУР): годовой корпоративный подоходный налог.

НК 214-VIII/2026: КПН = налогооблагаемый доход × 20%.
Налогооблагаемый доход = СГД (совокупный годовой доход) − вычеты.
⚠️ Вычеты: расходы на покупку товаров/работ/услуг У ЛИЦ НА УПРОЩЁНКЕ в вычеты НЕ включаются.
Убыток переносится на будущие периоды (до 10 лет). Авансовые платежи считает УГД (1/12
прошлого периода); в декларации — итоговый КПН за год за минусом уплаченных авансов.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from ..taxconfig.kz_2026 import KZ_2026


def _r(x: Decimal) -> Decimal:
    return Decimal(str(x)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)


@dataclass
class Kpn100:
    year: int
    gross_income: Decimal          # СГД — совокупный годовой доход (без НДС)
    deductions: Decimal            # вычитаемые расходы
    non_deductible: Decimal        # невычитаемые (в т.ч. закупки у упрощенцев) — справочно
    prior_losses_used: Decimal     # перенесённый убыток к зачёту
    taxable_income: Decimal        # налогооблагаемый доход (≥0)
    loss_carry_forward: Decimal    # убыток на будущее (если СГД−вычеты < 0)
    kpn: Decimal                   # КПН к начислению
    advances_paid: Decimal         # уплачено авансов за год
    kpn_payable: Decimal           # к доплате в декларации (≥0)
    kpn_overpaid: Decimal          # переплата (если авансы > КПН)
    rate: Decimal
    lines: dict = field(default_factory=dict)


def calc_kpn_100(
    *,
    year: int = 2026,
    gross_income: Decimal = Decimal(0),
    deductions: Decimal = Decimal(0),
    non_deductible: Decimal = Decimal(0),
    prior_losses: Decimal = Decimal(0),
    advances_paid: Decimal = Decimal(0),
    rate: Decimal | None = None,
) -> Kpn100:
    """Годовой расчёт КПН 100.00."""
    r = rate if rate is not None else KZ_2026.kpn_rate
    sgd = Decimal(str(gross_income or 0))
    ded = Decimal(str(deductions or 0))       # предполагается: невычитаемые уже исключены
    losses = Decimal(str(prior_losses or 0))
    adv = Decimal(str(advances_paid or 0))

    income_after_deductions = sgd - ded
    if income_after_deductions <= 0:
        # убыток года → переносим, налог 0
        return Kpn100(
            year=year, gross_income=sgd, deductions=ded, non_deductible=Decimal(str(non_deductible or 0)),
            prior_losses_used=Decimal(0), taxable_income=Decimal(0),
            loss_carry_forward=_r(-income_after_deductions), kpn=Decimal(0),
            advances_paid=adv, kpn_payable=Decimal(0), kpn_overpaid=adv, rate=r,
            lines={"taxable_income": "0", "kpn": "0", "loss_carry_forward": str(_r(-income_after_deductions))},
        )

    used_loss = min(losses, income_after_deductions)
    taxable = income_after_deductions - used_loss
    kpn = _r(taxable * r)
    diff = kpn - adv
    payable = diff if diff > 0 else Decimal(0)
    overpaid = -diff if diff < 0 else Decimal(0)

    return Kpn100(
        year=year, gross_income=sgd, deductions=ded,
        non_deductible=Decimal(str(non_deductible or 0)),
        prior_losses_used=_r(used_loss), taxable_income=_r(taxable),
        loss_carry_forward=Decimal(0), kpn=kpn, advances_paid=adv,
        kpn_payable=payable, kpn_overpaid=overpaid, rate=r,
        lines={"gross_income": str(sgd), "deductions": str(ded),
               "taxable_income": str(_r(taxable)), "kpn": str(kpn),
               "kpn_payable": str(payable), "kpn_overpaid": str(overpaid)},
    )
