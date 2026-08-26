"""Налоговый движок НДС (форма 300.00, ОУР): исходящий − входящий = к уплате.

Чистый расчёт. НК 214-VIII/2026: ставка 16%. НДС к уплате = исходящий НДС (с облагаемого
оборота) − входящий НДС к зачёту (по полученным ЭСФ). Превышение зачёта переносится на
следующий период (или к возврату). Входной НДС зачитывается только по валидным ЭСФ.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from ..taxconfig.kz_2026 import KZ_2026


def _r(x: Decimal) -> Decimal:
    return Decimal(str(x)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def vat_from_net(net: Decimal, rate: Decimal | None = None) -> Decimal:
    """НДС сверху цены без НДС: net × 16%."""
    r = rate if rate is not None else KZ_2026.vat_rate
    return _r(Decimal(str(net)) * r)


def vat_from_gross(gross: Decimal, rate: Decimal | None = None) -> Decimal:
    """НДС в цене с НДС (extract): gross × 16/116."""
    r = rate if rate is not None else KZ_2026.vat_rate
    return _r(Decimal(str(gross)) * r / (1 + r))


@dataclass
class Vat300:
    period: str                 # 'Q1-2026'..'Q4-2026'
    taxable_turnover: Decimal   # облагаемый оборот (без НДС)
    output_vat: Decimal         # исходящий НДС (начислено с реализации)
    input_vat_creditable: Decimal  # входящий НДС к зачёту (по ЭСФ)
    vat_payable: Decimal        # к уплате в бюджет (≥0)
    vat_carry_forward: Decimal  # превышение зачёта → на след. период (≥0)
    rate: Decimal
    lines: dict = field(default_factory=dict)


def calc_vat_300(
    *,
    period: str,
    taxable_turnover: Decimal = Decimal(0),
    output_vat: Decimal | None = None,
    input_vat_creditable: Decimal = Decimal(0),
    rate: Decimal | None = None,
) -> Vat300:
    """Расчёт 300.00 за квартал.

    output_vat — если None, считается как taxable_turnover × ставка (НДС сверху).
    """
    r = rate if rate is not None else KZ_2026.vat_rate
    turnover = Decimal(str(taxable_turnover or 0))
    out_vat = _r(Decimal(str(output_vat))) if output_vat is not None else _r(turnover * r)
    in_vat = _r(Decimal(str(input_vat_creditable or 0)))

    diff = out_vat - in_vat
    payable = diff if diff > 0 else Decimal(0)
    carry = -diff if diff < 0 else Decimal(0)

    return Vat300(
        period=period,
        taxable_turnover=turnover,
        output_vat=out_vat,
        input_vat_creditable=in_vat,
        vat_payable=payable,
        vat_carry_forward=carry,
        rate=r,
        lines={
            "output_vat": str(out_vat),
            "input_vat_creditable": str(in_vat),
            "vat_payable": str(payable),
            "vat_carry_forward": str(carry),
        },
    )


def quarter_bounds(year: int, q: int):
    """Границы квартала (date, date)."""
    from datetime import date
    starts = {1: (1, 1), 2: (4, 1), 3: (7, 1), 4: (10, 1)}
    ends = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}
    return date(year, *starts[q]), date(year, *ends[q])
