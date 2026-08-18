"""Генератор XML формы 910.00 по официальной структуре бланка КГД (коды строк 001–010).

Структура сверена по официальному бланку 910.00/910.01 (cdb.kz, ред. 2025→2026):
  Раздел 1 — шапка (ИИН/БИН, период, ОПФ, резидентство, УГД, виды деятельности);
  Раздел «Исчисленные налоги» — 910.00.001..004;
  Раздел «Соцплатежи за ИП» — 910.00.005..010, помесячно I–VI + Итого VII.

⚠️ Имена XML-элементов и namespace — ПРОВИЗОРНЫЕ (по кодам строк). Точная привязка к
официальному XSD ИСНА делается при получении схемы через Smart Bridge (оргтрек Фазы 5).
Значения и построчная логика при этом не меняются — меняется только «обёртка».
"""

from __future__ import annotations

from decimal import Decimal

from lxml import etree

from .simplified_910 import Calc910

SCHEMA_VERSION = "910.00"  # версия формы; при привязке к XSD ИСНА уточнить


def _line(parent, code: str, value) -> None:
    """Элемент строки: <line code="910.00.001">value</line>."""
    el = etree.SubElement(parent, "line", code=code)
    el.text = str(int(Decimal(str(value or 0))))


def _monthly_line(parent, code: str, per_month: Decimal, months: int = 6) -> None:
    """Помесячная строка (I–VI) + Итого (VII). Наш расчёт — равные месяцы."""
    el = etree.SubElement(parent, "line", code=code)
    total = Decimal(0)
    for m in range(1, months + 1):
        me = etree.SubElement(el, "m", n=str(m))
        me.text = str(int(per_month))
        total += per_month
    tot = etree.SubElement(el, "total")
    tot.text = str(int(total))


def build_910_xml(
    calc: Calc910,
    *,
    iin_bin: str,
    name: str,
    year: int,
    half: int,
    is_ip: bool,
    ugd_code: str | None = None,
    oked_codes: list[str] | None = None,
    declaration_kind: str = "regular",   # regular=очередная/первоначальная
) -> bytes:
    """Собирает XML 910.00 из расчёта. Возвращает UTF-8 bytes."""
    root = etree.Element("declaration", form="910.00", version=SCHEMA_VERSION)

    # --- Раздел 1: шапка ---
    hdr = etree.SubElement(root, "header")
    etree.SubElement(hdr, "iinBin").text = iin_bin
    etree.SubElement(hdr, "name").text = name or ""
    etree.SubElement(hdr, "taxPeriod", half=str(half), year=str(year))
    etree.SubElement(hdr, "legalForm").text = "ip" if is_ip else "too"
    etree.SubElement(hdr, "declarationKind").text = declaration_kind
    etree.SubElement(hdr, "residency").text = "resident"
    etree.SubElement(hdr, "currency").text = "398"  # KZT
    if ugd_code:
        etree.SubElement(hdr, "ugdCode").text = ugd_code
    if oked_codes:
        acts = etree.SubElement(hdr, "activities")
        for c in oked_codes[:12]:  # ячейки A–L
            etree.SubElement(acts, "oked").text = c

    # --- Раздел «Исчисленные налоги» (001–004) ---
    taxes = etree.SubElement(root, "section", name="taxes")
    reduction = Decimal(0)  # 910.00.002: расходы по работникам >24000 МРП — вне MVP (0)
    income_for_tax = calc.turnover - reduction
    _line(taxes, "910.00.001", calc.turnover)          # Доход
    _line(taxes, "910.00.002", reduction)              # к уменьшению
    _line(taxes, "910.00.003", income_for_tax)         # = 001 − 002
    _line(taxes, "910.00.004", calc.income_tax)        # ИПН/КПН к уплате

    # --- Раздел «Соцплатежи за ИП» (005–010), только для ИП ---
    if is_ip and calc.social:
        m = calc.social["monthly"]
        base = _social_base(calc)                      # доход для соц.базы (мес.)
        soc = etree.SubElement(root, "section", name="social")
        _monthly_line(soc, "910.00.005", base)         # доход для СО
        _monthly_line(soc, "910.00.006", m.so)         # СО
        _monthly_line(soc, "910.00.007", base)         # доход для ОПВ
        _monthly_line(soc, "910.00.008", m.opv)        # ОПВ
        _monthly_line(soc, "910.00.009", m.opvr)       # ОПВ работодателя (ОПВР) — VERIFY привязку для ИП за себя
        _monthly_line(soc, "910.00.010", m.vosms)      # ВОСМС

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True)


def _social_base(calc: Calc910) -> Decimal:
    """Месячная база соц.платежей (от неё считались взносы). Минимум — 1 МЗП."""
    from ..taxconfig.kz_2026 import KZ_2026
    return KZ_2026.mzp
