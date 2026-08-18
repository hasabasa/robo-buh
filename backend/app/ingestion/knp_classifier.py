"""Классификатор операций «доход / не-доход» по КНП (код назначения платежа).

Для упрощёнки налог с ОБОРОТА, поэтому доход — это входящие поступления (credit) за
товары/услуги. Принцип безопасности: молча доходом не помечаем ничего. Три исхода:
  is_income=True   — уверенно выручка (входящий + доходный КНП);
  is_income=False  — уверенно не выручка (любой расход, либо недоходный КНП на входе);
  is_income=None   — неясно → очередь ручной сверки (человек/Qwen решает).

КНП сверены по открытым источникам (tsnik.kz / egov, классификатор НБРК). Набор частичный
и расширяемый: полный справочник НБРК за пейволом ЦДБ — при доступе пополнить REFERENCE.
Дальше по цепочке: неуверенные (None) идут в Qwen-классификатор по назначению платежа.
"""

from __future__ import annotations

from dataclasses import dataclass

# --- Доходные КНП (выручка предпринимателя) ---
INCOME_KNP: set[str] = {"710", "821"}          # 710 — за товары, 821 — строительные услуги
INCOME_KNP_RANGES = [(851, 862)]               # 851–862 — услуги (связь, юр, образование, медицина, IT и т.п.)

# --- Явно НЕ-доходные КНП (даже на входящем платеже это не выручка) ---
NONINCOME_KNP: set[str] = {
    "342", "343",              # переводы между своими счетами
    "421", "423", "429",       # погашение/движение займов
    "610",                     # покупка/выкуп акций, долей
    "661",                     # дивиденды
    "332",                     # зарплата от юрлица
}
NONINCOME_KNP_RANGES = [(10, 17), (121, 124), (911, 913)]  # пенсионные, медстрах, налоги/штрафы

# Неоднозначные — НЕ решаем автоматически (внесение наличных, возвраты):
#   331 (внесение наличных), 780/880 (возвраты) → всегда в ручную сверку.


def _in_ranges(code_int: int, ranges) -> bool:
    return any(lo <= code_int <= hi for lo, hi in ranges)


@dataclass
class Classification:
    is_income: bool | None
    confidence: float
    classified_by: str        # 'knp_rule' | 'direction' | 'unknown'
    reason: str


def classify_by_knp(knp: str | None, direction: str | None) -> Classification:
    """Классифицирует операцию. direction: 'credit' (приход) | 'debit' (расход) | None."""
    # 1. Расход выручкой не бывает — независимо от КНП
    if direction == "debit":
        return Classification(False, 0.99, "direction", "расход (debit) — не доход")

    knp = (knp or "").strip()
    if knp.isdigit():
        code = int(knp)
        if knp in INCOME_KNP or _in_ranges(code, INCOME_KNP_RANGES):
            return Classification(True, 0.95, "knp_rule", f"КНП {knp} — выручка за товары/услуги")
        if knp in NONINCOME_KNP or _in_ranges(code, NONINCOME_KNP_RANGES):
            return Classification(False, 0.95, "knp_rule", f"КНП {knp} — не выручка (перевод/заём/налог/дивиденд)")

    # 2. КНП нет или неизвестен → не угадываем, отправляем на сверку
    return Classification(None, 0.0, "unknown", f"КНП '{knp or '—'}' не распознан — нужна ручная сверка")
