"""История базовой ставки НБРК — источник для расчёта пени.

Ставка = данные, а не логика: при новом решении НБРК добавить одну строку в RATE_HISTORY.
Источник: НБРК / Параграф (prg.kz doc_id=36378707). Хранятся только точки ИЗМЕНЕНИЯ ставки
(между ними ставка постоянна). Даты — «действует с».
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

# (действует с; ставка, %). Только реальные изменения значения.
RATE_HISTORY: list[tuple[date, Decimal]] = [
    (date(2023, 1, 16), Decimal("16.75")),
    (date(2023, 8, 28), Decimal("16.50")),
    (date(2023, 10, 9), Decimal("16.00")),
    (date(2023, 11, 27), Decimal("15.75")),
    (date(2024, 1, 22), Decimal("15.25")),
    (date(2024, 2, 26), Decimal("14.75")),
    (date(2024, 6, 3), Decimal("14.50")),
    (date(2024, 7, 15), Decimal("14.25")),
    (date(2024, 12, 2), Decimal("15.25")),
    (date(2025, 3, 11), Decimal("16.50")),
    (date(2025, 10, 13), Decimal("18.00")),
    (date(2026, 6, 8), Decimal("17.00")),
    (date(2026, 7, 27), Decimal("16.75")),   # актуальна; ← дописывать сюда новые решения НБРК
]

# Коэффициент пени (× базовая ставка). НК РК: 1,25. Тоже история — на случай изменения.
PENALTY_COEF_HISTORY: list[tuple[date, Decimal]] = [
    (date(2015, 1, 1), Decimal("1.25")),
]


def _value_on(history: list[tuple[date, Decimal]], d: date) -> Decimal:
    val = history[0][1]
    for start, v in history:
        if start <= d:
            val = v
        else:
            break
    return val


def rate_on(d: date) -> Decimal:
    """Базовая ставка НБРК (%), действующая на дату d."""
    return _value_on(RATE_HISTORY, d)


def penalty_coef_on(d: date) -> Decimal:
    """Коэффициент пени на дату d (обычно 1.25)."""
    return _value_on(PENALTY_COEF_HISTORY, d)


def last_known_rate_date() -> date:
    """Дата последнего известного изменения ставки (для предупреждения об устаревании)."""
    return RATE_HISTORY[-1][0]


def rate_segments(d_from: date, d_to: date) -> list[tuple[date, date, Decimal, Decimal]]:
    """Разбивает [d_from, d_to] на под-периоды постоянной (ставка, коэффициент).

    Возвращает [(seg_start, seg_end, rate_pct, coef)] — границы там, где менялась ставка/коэф.
    """
    if d_to < d_from:
        return []
    # даты смены ставки/коэффициента, попадающие внутрь окна
    boundaries = sorted({d for d, _ in RATE_HISTORY if d_from < d <= d_to}
                        | {d for d, _ in PENALTY_COEF_HISTORY if d_from < d <= d_to})
    segments = []
    seg_start = d_from
    for b in boundaries:
        segments.append((seg_start, b - __import__("datetime").timedelta(days=1),
                         rate_on(seg_start), penalty_coef_on(seg_start)))
        seg_start = b
    segments.append((seg_start, d_to, rate_on(seg_start), penalty_coef_on(seg_start)))
    return segments
