"""Периоды и сроки сдачи/уплаты форм РК (для дашборда и календаря обязательств).

Сроки по НК РК: 910.00 полугодовая (H1: сдать 15.08, уплатить 25.08; H2: 15.02, 25.02 след. года);
200.00 квартальная (сдать до 15 числа 2-го месяца после квартала, уплатить до 25-го); соцплатежи ИП
ежемесячно до 25 числа следующего месяца.
"""

from __future__ import annotations

from datetime import date


def current_half(d: date) -> int:
    return 1 if d.month <= 6 else 2


def current_quarter(d: date) -> int:
    return (d.month - 1) // 3 + 1


def due_dates_910(year: int, half: int) -> tuple[date, date]:
    """(срок сдачи, срок уплаты) для 910.00."""
    if half == 1:
        return date(year, 8, 15), date(year, 8, 25)
    return date(year + 1, 2, 15), date(year + 1, 2, 25)


def due_dates_200(year: int, quarter: int) -> tuple[date, date]:
    """(срок сдачи, срок уплаты) для 200.00/300.00: 15/25 числа 2-го месяца после квартала."""
    # квартал N кончается в месяце 3N; +2 месяца → месяц сдачи
    m = 3 * quarter + 2
    y = year + (1 if m > 12 else 0)
    if m > 12:
        m -= 12
    return date(y, m, 15), date(y, m, 25)


def next_social_due(today: date) -> date:
    """Ближайший срок соцплатежей ИП — 25 число следующего месяца."""
    m, y = today.month + 1, today.year
    if m > 12:
        m, y = 1, y + 1
    return date(y, m, 25)
