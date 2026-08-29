"""Генератор XML формы 300.00 (НДС, квартальная, ПРОВИЗОРНЫЙ).

Как и 910/200: офиц. машинного шаблона под НК-2026 нет → семантические коды `vat.*`,
к `field_300_00_NNN` не привязываемся. Значения — из движка vat_300 (ставка 16% 2026).
"""

from __future__ import annotations

from decimal import Decimal

from lxml import etree

SCHEMA_VERSION = "300.00"


def _dec(x) -> Decimal:
    return Decimal(str(x or 0))


def _line(parent, code: str, value, title: str = "") -> None:
    el = etree.SubElement(parent, "line", code=code)
    if title:
        el.set("title", title)
    el.text = str(int(_dec(value)))


def build_300_xml(calc: dict, *, iin_bin: str, name: str, year: int, quarter: int,
                  is_ip: bool, ugd_code: str | None = None,
                  declaration_kind: str = "regular") -> bytes:
    """Собирает XML 300.00 из свода compute_vat_300. Возвращает UTF-8 bytes."""
    root = etree.Element("declaration", form="300.00", version=SCHEMA_VERSION)

    hdr = etree.SubElement(root, "header")
    etree.SubElement(hdr, "iinBin").text = iin_bin
    etree.SubElement(hdr, "name").text = name or ""
    etree.SubElement(hdr, "taxPeriod", quarter=str(quarter), year=str(year))
    etree.SubElement(hdr, "legalForm").text = "ip" if is_ip else "too"
    etree.SubElement(hdr, "declarationKind").text = declaration_kind
    etree.SubElement(hdr, "residency").text = "resident"
    etree.SubElement(hdr, "currency").text = "398"  # KZT
    etree.SubElement(hdr, "vatRate").text = str(calc.get("rate", "0.16"))
    if ugd_code:
        etree.SubElement(hdr, "ugdCode").text = ugd_code

    sect = etree.SubElement(root, "section", name="vat")
    _line(sect, "vat.taxable_turnover", calc.get("taxable_turnover"), "Облагаемый оборот (без НДС)")
    _line(sect, "vat.output", calc.get("output_vat"), "НДС начисленный (исходящий)")
    _line(sect, "vat.input_credit", calc.get("input_vat_creditable"), "НДС в зачёт (входящий)")
    _line(sect, "vat.payable", calc.get("vat_payable"), "НДС к уплате")
    _line(sect, "vat.carry_forward", calc.get("vat_carry_forward"), "Превышение НДС к переносу")

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True)


def flk_300(calc: dict) -> tuple[list[str], list[str]]:
    """Локальный ФЛК НДС: к уплате/перенос выводятся из исходящий−входящий."""
    errors, warns = [], []
    out, inp = _dec(calc.get("output_vat")), _dec(calc.get("input_vat_creditable"))
    payable, carry = _dec(calc.get("vat_payable")), _dec(calc.get("vat_carry_forward"))
    diff = out - inp
    if payable != max(Decimal(0), diff):
        errors.append("НДС к уплате ≠ max(0, исходящий − входящий).")
    if carry != max(Decimal(0), -diff):
        errors.append("Превышение НДС к переносу ≠ max(0, входящий − исходящий).")
    if payable > 0 and carry > 0:
        errors.append("Одновременно и НДС к уплате, и превышение к переносу — недопустимо.")
    return errors, warns
