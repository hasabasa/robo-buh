"""Налоговый движок формы 910.00 (СНР упрощёнка): оборот → ИПН/КПН + соцплатежи.

Чистый расчёт: на вход — оборот за полугодие и параметры налогоплательщика, на выход —
построчный расчёт (маппинг на официальные коды строк 910.00 делает xml-билдер, когда
будет XSD КГД). База — НК 214-VIII/2026, константы из taxconfig.kz_2026.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from ..taxconfig.kz_2026 import KZ_2026, snr_income_limit_kzt
from .social import social_for_period


def _round(x: Decimal) -> Decimal:
    return x.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def effective_rate(maslikhat_rate: Decimal | None) -> Decimal:
    """Ставка ИПН/КПН как доля. maslikhat_rate — в ПРОЦЕНТАХ (как в БД: NUMERIC 2..6),
    базовая 4%. Вне диапазона 2–6% → кламп."""
    c = KZ_2026
    if maslikhat_rate is None:
        return c.ipn_rate_default
    r = Decimal(str(maslikhat_rate)) / 100  # проценты → доля
    return max(c.ipn_rate_min, min(r, c.ipn_rate_max))


@dataclass
class Calc910:
    period: str                    # 'H1-2026' / 'H2-2026'
    taxpayer_kind: str             # 'ip' | 'too'
    turnover: Decimal              # облагаемый оборот за полугодие
    rate: Decimal                  # применённая ставка
    income_tax: Decimal            # ИПН (ИП) или КПН (ТОО) с оборота
    income_tax_name: str           # 'ИПН' | 'КПН'
    social: dict                   # соцплатежи ИП за себя за 6 мес (для ИП)
    lines: dict = field(default_factory=dict)  # черновой построчный вид


def calc_910(
    *,
    turnover: Decimal,
    period: str,
    taxpayer_kind: str = "ip",
    maslikhat_rate: Decimal | None = None,
    birth_date: date | None = None,
    declared_social_base: Decimal | None = None,
    months: int = 6,
) -> Calc910:
    """Полный расчёт 910.00 за полугодие."""
    turnover = Decimal(str(turnover or 0))
    rate = effective_rate(maslikhat_rate)
    income_tax = _round(turnover * rate)
    tax_name = "КПН" if taxpayer_kind == "too" else "ИПН"

    # Соцплатежи «за себя» — только для ИП (у ТОО директор идёт через 200.00, не сюда)
    social = social_for_period(months, declared_base=declared_social_base, birth_date=birth_date) \
        if taxpayer_kind == "ip" else {}

    lines = {
        "turnover": str(turnover),
        "rate_percent": str(rate * 100),
        f"{tax_name.lower()}_with_turnover": str(income_tax),
    }
    if social:
        lines["social_total"] = str(social["total"])

    return Calc910(
        period=period,
        taxpayer_kind=taxpayer_kind,
        turnover=turnover,
        rate=rate,
        income_tax=income_tax,
        income_tax_name=tax_name,
        social=social,
        lines=lines,
    )


@dataclass
class SnrLimitStatus:
    ytd_turnover: Decimal
    limit: Decimal
    share: Decimal          # 0..1+
    zone: str               # 'green' | 'yellow' | 'red'
    message: str


def snr_limit_status(ytd_turnover: Decimal) -> SnrLimitStatus:
    """Светофор лимита СНР (600 000 МРП/год). Красный = риск слёта с упрощёнки."""
    limit = snr_income_limit_kzt()
    ytd = Decimal(str(ytd_turnover or 0))
    share = (ytd / limit) if limit else Decimal(0)
    if share < Decimal("0.8"):
        zone, msg = "green", "Запас по лимиту СНР"
    elif share < 1:
        zone, msg = "yellow", "Приближение к лимиту СНР — следите за оборотом"
    else:
        zone, msg = "red", "Лимит СНР превышен — обязателен переход на ОУР"
    return SnrLimitStatus(ytd_turnover=ytd, limit=limit, share=share, zone=zone, message=msg)
