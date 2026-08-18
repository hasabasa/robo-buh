"""Соцплатежи ИП «за себя»: ОПВ, ОПВР, СО, ВОСМС. Чистый расчёт, без БД.

Все ставки/базы — из taxconfig.kz_2026. База по умолчанию 1 МЗП (минимум), но ИП вправе
заявить больше — тогда база клампится к законным пределам каждого платежа.
Считается помесячно; платится до 25 числа следующего месяца.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from ..taxconfig.kz_2026 import KZ_2026


def _round(x: Decimal) -> Decimal:
    return x.quantize(Decimal("1"), rounding=ROUND_HALF_UP)  # тенге, до целого


def _clamp(base: Decimal, lo_mzp: int, hi_mzp: int) -> Decimal:
    mzp = KZ_2026.mzp
    return max(mzp * lo_mzp, min(base, mzp * hi_mzp))


def has_opvr(birth_date: date | None) -> bool:
    """ОПВР платят только рождённые после 01.01.1975."""
    if birth_date is None:
        return False
    cutoff = date.fromisoformat(KZ_2026.opvr_birthdate_cutoff)
    return birth_date >= cutoff


@dataclass
class SocialMonthly:
    opv: Decimal
    opvr: Decimal
    so: Decimal
    vosms: Decimal

    @property
    def total(self) -> Decimal:
        return self.opv + self.opvr + self.so + self.vosms


def social_monthly(
    *,
    declared_base: Decimal | None = None,
    birth_date: date | None = None,
) -> SocialMonthly:
    """Соцплатежи ИП за себя за один месяц.

    declared_base — заявленный доход-база; None → 1 МЗП (минимальный вариант).
    """
    c = KZ_2026
    base = declared_base if declared_base and declared_base > 0 else c.mzp

    opv = _round(_clamp(base, 1, c.opv_base_max_mzp) * c.opv_rate)
    so = _round(_clamp(base, 1, c.so_base_max_mzp) * c.so_rate)
    opvr = _round(_clamp(base, 1, c.opv_base_max_mzp) * c.opvr_rate) if has_opvr(birth_date) else Decimal(0)
    vosms = c.vosms_fixed  # фиксировано 5 950 ₸, база 1,4 МЗП

    return SocialMonthly(opv=opv, opvr=opvr, so=so, vosms=vosms)


def social_for_period(
    months: int,
    *,
    declared_base: Decimal | None = None,
    birth_date: date | None = None,
) -> dict:
    """Соцплатежи за N месяцев (для полугодия — 6). Возвращает помесячную и итоговую суммы."""
    one = social_monthly(declared_base=declared_base, birth_date=birth_date)
    return {
        "monthly": one,
        "months": months,
        "opv_total": one.opv * months,
        "opvr_total": one.opvr * months,
        "so_total": one.so * months,
        "vosms_total": one.vosms * months,
        "total": one.total * months,
    }
