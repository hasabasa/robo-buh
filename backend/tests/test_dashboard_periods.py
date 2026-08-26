"""Тесты сроков форм и склонения для дашборда."""
from datetime import date
from app.dashboard.periods import (current_half, current_quarter, due_dates_910,
                                    due_dates_200, next_social_due)
from app.dashboard.service import _plural_ops


def test_half_and_quarter():
    assert current_half(date(2026, 6, 30)) == 1 and current_half(date(2026, 7, 1)) == 2
    assert current_quarter(date(2026, 1, 15)) == 1
    assert current_quarter(date(2026, 8, 26)) == 3
    assert current_quarter(date(2026, 12, 31)) == 4


def test_due_dates_910():
    assert due_dates_910(2026, 1) == (date(2026, 8, 15), date(2026, 8, 25))
    assert due_dates_910(2026, 2) == (date(2027, 2, 15), date(2027, 2, 25))  # H2 → след. год


def test_due_dates_200_rolls_year():
    assert due_dates_200(2026, 3) == (date(2026, 11, 15), date(2026, 11, 25))
    assert due_dates_200(2026, 4) == (date(2027, 2, 15), date(2027, 2, 25))  # Q4 → февраль


def test_next_social_due():
    assert next_social_due(date(2026, 8, 26)) == date(2026, 9, 25)
    assert next_social_due(date(2026, 12, 10)) == date(2027, 1, 25)


def test_plural_ops():
    assert _plural_ops(1) == "1 операция"
    assert _plural_ops(3) == "3 операции"
    assert _plural_ops(5) == "5 операций"
    assert _plural_ops(11) == "11 операций"
    assert _plural_ops(21) == "21 операция"
