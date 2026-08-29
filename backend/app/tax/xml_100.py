"""Генератор XML формы 100.00 (КПН, годовая, ПРОВИЗОРНЫЙ).

Как и 910/200/300: семантические коды `kpn.*`, к `field_100_00_NNN` не привязываемся.
Значения — из движка kpn_100 (ставка КПН 20% 2026).
"""

from __future__ import annotations

from decimal import Decimal

from lxml import etree

SCHEMA_VERSION = "100.00"
KPN_RATE = Decimal("0.20")


def _dec(x) -> Decimal:
    return Decimal(str(x or 0))


def _line(parent, code: str, value, title: str = "") -> None:
    el = etree.SubElement(parent, "line", code=code)
    if title:
        el.set("title", title)
    el.text = str(int(_dec(value)))


def build_100_xml(calc: dict, *, iin_bin: str, name: str, year: int,
                  is_ip: bool, ugd_code: str | None = None,
                  declaration_kind: str = "regular") -> bytes:
    """Собирает XML 100.00 из свода compute_kpn_100. Возвращает UTF-8 bytes."""
    root = etree.Element("declaration", form="100.00", version=SCHEMA_VERSION)

    hdr = etree.SubElement(root, "header")
    etree.SubElement(hdr, "iinBin").text = iin_bin
    etree.SubElement(hdr, "name").text = name or ""
    etree.SubElement(hdr, "taxPeriod", year=str(year))
    etree.SubElement(hdr, "legalForm").text = "ip" if is_ip else "too"
    etree.SubElement(hdr, "declarationKind").text = declaration_kind
    etree.SubElement(hdr, "residency").text = "resident"
    etree.SubElement(hdr, "currency").text = "398"  # KZT
    etree.SubElement(hdr, "kpnRate").text = str(KPN_RATE)
    if ugd_code:
        etree.SubElement(hdr, "ugdCode").text = ugd_code

    sect = etree.SubElement(root, "section", name="kpn")
    _line(sect, "kpn.sgd", calc.get("gross_income"), "СГД (совокупный годовой доход)")
    _line(sect, "kpn.deductions", calc.get("deductions"), "Вычеты")
    _line(sect, "kpn.non_deductible", calc.get("non_deductible"), "Невычитаемые расходы (справочно)")
    _line(sect, "kpn.taxable", calc.get("taxable_income"), "Налогооблагаемый доход")
    _line(sect, "kpn.tax", calc.get("kpn"), "КПН исчисленный (20%)")
    _line(sect, "kpn.payable", calc.get("kpn_payable"), "КПН к уплате")
    _line(sect, "kpn.overpaid", calc.get("kpn_overpaid"), "КПН к возврату/зачёту")
    _line(sect, "kpn.loss_carry_forward", calc.get("loss_carry_forward"), "Убыток к переносу")

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True)


def flk_100(calc: dict) -> tuple[list[str], list[str]]:
    """Локальный ФЛК КПН: налог = налогооблагаемый доход × 20% (±1 ₸ на округление)."""
    errors, warns = [], []
    taxable = _dec(calc.get("taxable_income"))
    kpn = _dec(calc.get("kpn"))
    expected = (taxable * KPN_RATE) if taxable > 0 else Decimal(0)
    if abs(kpn - expected) > 1:
        errors.append(f"КПН {kpn} ≠ налогооблагаемый доход × 20% ({expected}).")
    if taxable <= 0 and kpn != 0:
        errors.append("Налогооблагаемого дохода нет, а КПН начислен.")
    if _dec(calc.get("loss_carry_forward")) > 0 and kpn > 0:
        errors.append("Одновременно убыток к переносу и КПН к уплате — недопустимо.")
    return errors, warns
