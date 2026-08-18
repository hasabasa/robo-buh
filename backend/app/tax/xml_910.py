"""Генератор XML формы 910.00 (ПРОВИЗОРНЫЙ — до официального шаблона под НК-2026).

⚠️ ВАЖНО (сверено по официальному машинному шаблону СОНО form_910_00_v27_r133 от
30.12.2025, лежит в docs/knowledge/sono/910.00/):
  • Официальный опубликованный шаблон действует 01.01.2023–31.12.2026 и считает налог по
    СТАРОМУ режиму: 910.00.005 = 001×3%, 008 = ИПН, 009 = СОЦНАЛОГ (½/½), 010 = ИТОГ дохода
    за полугодие, а соцплатежи ИП — в строках 011–025 помесячно. Версии под НК-2026 (4%,
    соцналог отменён) на сегодня НЕТ. Поэтому к field_910_00_NNN НЕ привязываемся.
  • Достоверно совпадают только 910.00.001 (доход), 002 (к уменьшению), 003 (база),
    004 (налог к уплате) — по бумажному бланку 2026. Их и эмитим кодами строк.
  • Соцплатежи ИП эмитим СЕМАНТИЧЕСКИМИ элементами (opv/opvr/so/vosms), НЕ кодами
    910.00.005–010 (это был бы неверный маппинг — в реальном бланке там налог/итог дохода).

Точная привязка к официальным field_910_00_NNN — когда КГД опубликует шаблон 910.00 под
НК-2026 (вотчер на kgd.gov.kz/ru/content/fno-na-2026-god-1) и/или после WSDL/XSD из
Smart Bridge (оргтрек Фазы 5). Значения расчёта при этом не меняются — только обёртка.
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

    # --- Соцплатежи ИП «за себя», только для ИП ---
    # Эмитим СЕМАНТИЧЕСКИМИ кодами (не 910.00.005–010 — в реальном бланке там налог/итог
    # дохода). Точные field_910_00_NNN для соцплатежей (011–025) привяжем по шаблону НК-2026.
    if is_ip and calc.social:
        m = calc.social["monthly"]
        base = _social_base(calc)                      # доход для соц.базы (мес.)
        soc = etree.SubElement(root, "section", name="social")
        _monthly_line(soc, "social.income_base", base) # доход-база для соц.платежей
        _monthly_line(soc, "social.so", m.so)          # СО
        _monthly_line(soc, "social.opv", m.opv)        # ОПВ
        _monthly_line(soc, "social.opvr", m.opvr)      # ОПВР
        _monthly_line(soc, "social.vosms", m.vosms)    # ВОСМС

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True)


def _social_base(calc: Calc910) -> Decimal:
    """Месячная база соц.платежей (от неё считались взносы). Минимум — 1 МЗП."""
    from ..taxconfig.kz_2026 import KZ_2026
    return KZ_2026.mzp
