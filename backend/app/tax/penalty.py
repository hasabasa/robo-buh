"""Расчёт пени за несвоевременную уплату налога (НК РК).

Формула официального калькулятора КГД: П = Н × (Р/100) × k × Д / 365, где Н — недоимка,
Р — базовая ставка НБРК (%), k — коэффициент (1,25), Д — дни просрочки. Период просрочки
нарезается по датам изменения ставки/коэффициента и суммируется по под-периодам.

НК РК: пеня начисляется за каждый день просрочки, начиная СО ДНЯ, СЛЕДУЮЩЕГО за днём срока
уплаты, включая день уплаты.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from .nbrk_rates import last_known_rate_date, rate_segments


@dataclass
class PenaltySegment:
    date_from: date
    date_to: date
    days: int
    rate_pct: Decimal
    coef: Decimal
    amount: Decimal      # пеня за этот под-период


@dataclass
class PenaltyResult:
    principal: Decimal          # недоимка
    due_date: date
    pay_date: date
    total_days: int
    total: Decimal              # пеня всего
    stale: bool                 # период выходит за последнюю известную ставку НБРК
    segments: list[PenaltySegment] = field(default_factory=list)


def calc_penalty(principal: Decimal, due_date: date, pay_date: date) -> PenaltyResult:
    """Пеня на недоимку principal, срок уплаты due_date, фактическая уплата pay_date."""
    principal = Decimal(str(principal or 0))
    if pay_date <= due_date or principal <= 0:
        return PenaltyResult(principal, due_date, pay_date, 0, Decimal("0.00"), False, [])

    window_start = due_date + timedelta(days=1)   # со следующего дня после срока
    window_end = pay_date                         # включая день уплаты

    segs: list[PenaltySegment] = []
    total = Decimal(0)
    for s, e, rate, coef in rate_segments(window_start, window_end):
        days = (e - s).days + 1
        seg = principal * (rate / 100) * coef * days / 365
        segs.append(PenaltySegment(s, e, days, rate, coef, seg.quantize(Decimal("0.01"), ROUND_HALF_UP)))
        total += seg

    return PenaltyResult(
        principal=principal,
        due_date=due_date,
        pay_date=pay_date,
        total_days=(pay_date - due_date).days,
        total=total.quantize(Decimal("0.01"), ROUND_HALF_UP),
        stale=window_end > last_known_rate_date() + timedelta(days=370),
        segments=segs,
    )
