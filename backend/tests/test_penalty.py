"""Тесты движка пени: одна ставка + нарезка по смене ставки НБРК."""

from datetime import date
from decimal import Decimal

from app.tax.penalty import calc_penalty
from app.tax.nbrk_rates import rate_on, rate_segments


def test_rate_lookup():
    assert rate_on(date(2026, 7, 27)) == Decimal("16.75")   # актуальная
    assert rate_on(date(2026, 6, 10)) == Decimal("17.00")   # после 08.06
    assert rate_on(date(2026, 1, 1)) == Decimal("18.00")    # с 13.10.2025


def test_no_penalty_if_paid_on_time():
    r = calc_penalty(Decimal("100000"), date(2026, 8, 25), date(2026, 8, 25))
    assert r.total == Decimal("0.00") and not r.segments


def test_single_rate_period():
    # долг 100000, срок 25.08.2026, уплата 27.08.2026 → 2 дня по 16,75%
    r = calc_penalty(Decimal("100000"), date(2026, 8, 25), date(2026, 8, 27))
    assert r.total_days == 2
    assert len(r.segments) == 1
    # 100000 × 0.1675 × 1.25 × 2 / 365 = 114.73
    assert r.total == Decimal("114.73")


def test_spans_rate_change():
    # срок 01.06.2026, уплата 30.06.2026 → смена ставки 08.06 (18% → 17%)
    r = calc_penalty(Decimal("100000"), date(2026, 6, 1), date(2026, 6, 30))
    assert len(r.segments) == 2
    s1, s2 = r.segments
    assert s1.rate_pct == Decimal("18.00") and s1.days == 6    # 02.06–07.06
    assert s2.rate_pct == Decimal("17.00") and s2.days == 23   # 08.06–30.06
    # 135000/365 + 488750/365 = 1708.90
    assert r.total == Decimal("1708.90")


def test_segments_cover_whole_window():
    r = calc_penalty(Decimal("50000"), date(2026, 5, 20), date(2026, 8, 10))
    covered = sum(s.days for s in r.segments)
    assert covered == r.total_days                              # без дыр/нахлёстов
