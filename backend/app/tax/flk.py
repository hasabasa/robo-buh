"""Локальный ФЛК (форматно-логический контроль) формы 910.00 перед выдачей/подписью.

Ловим ошибки до отправки в КГД: арифметика строк, обязательные реквизиты, границы.
Это наш предохранитель; официальный ФЛК ИСНА строже — его правила добавляем по мере
получения спецификации (Smart Bridge).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from .simplified_910 import Calc910


@dataclass
class FLKResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def check_910(calc: Calc910, *, iin_bin: str, ugd_code: str | None) -> FLKResult:
    errors: list[str] = []
    warnings: list[str] = []

    # Реквизиты
    if not (iin_bin and iin_bin.isdigit() and len(iin_bin) == 12):
        errors.append("ИИН/БИН должен быть 12 цифр")
    if not ugd_code:
        warnings.append("Не указан код органа госдоходов (УГД) — нужен для сдачи")

    # Арифметика: 004 = round(003 × ставка); 003 = 001 − 002 (002=0 в MVP)
    expected_tax = (calc.turnover * calc.rate).quantize(Decimal("1"))
    if calc.income_tax != expected_tax:
        errors.append(f"910.00.004 ({calc.income_tax}) ≠ доход×ставка ({expected_tax})")

    # Границы
    if calc.turnover < 0:
        errors.append("Доход (910.00.001) отрицательный")
    if not (Decimal("0.02") <= calc.rate <= Decimal("0.06")):
        errors.append(f"Ставка {calc.rate} вне диапазона 2–6%")

    # Соцплатежи (для ИП): итог = сумме месяцев (наш расчёт равномерный)
    if calc.social:
        m = calc.social["monthly"]
        if m.vosms <= 0:
            warnings.append("ВОСМС = 0 — обычно платится даже при нулевом доходе")

    return FLKResult(ok=not errors, errors=errors, warnings=warnings)
