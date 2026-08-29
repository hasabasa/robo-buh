"""Генератор XML формы 200.00 (ИПН у источника + соцплатежи по работникам, ПРОВИЗОРНЫЙ).

⚠️ Как и 910.00: официального МАШИННОГО шаблона СОНО под НК-2026 в открытом доступе нет,
поэтому к точным `field_200_00_NNN` НЕ привязываемся. Эмитим СЕМАНТИЧЕСКИЕ элементы
(ipn/opv/opvr/so/vosms/oosms/social_tax) — значения расчёта верны (движок payroll_200,
ставки kz_2026), меняется только обёртка. Привязка к XSD ИСНА — оргтрек (Smart Bridge)
или публикация шаблона 200.00 v2026 на kgd.gov.kz.

Форма квартальная (налоговый агент). Разбивка помесячная (3 месяца квартала); наш расчёт
исходит из постоянных окладов, поэтому месяц = квартальный итог / 3.
"""

from __future__ import annotations

from decimal import Decimal

from lxml import etree

SCHEMA_VERSION = "200.00"

# налоговые составляющие 200.00 (агрегаты из calc_200_quarter)
_COMPONENTS = [
    ("ipn", "ИПН у источника (удержан с работников)"),
    ("social_tax", "Социальный налог (работодатель)"),
    ("so", "Социальные отчисления (СО)"),
    ("opv", "ОПВ (удержаны с работников)"),
    ("opvr", "ОПВР (работодатель)"),
    ("vosms", "ВОСМС (удержаны с работников)"),
    ("oosms", "ООСМС (работодатель)"),
]


def _dec(x) -> Decimal:
    return Decimal(str(x or 0))


def _quarter_line(parent, code: str, quarter_total: Decimal, months: int = 3) -> None:
    """Строка с помесячной разбивкой (I–III) + Итого за квартал. Месяцы равные."""
    el = etree.SubElement(parent, "line", code=code)
    per_month = (quarter_total / months) if months else Decimal(0)
    acc = Decimal(0)
    for m in range(1, months + 1):
        me = etree.SubElement(el, "m", n=str(m))
        # последний месяц добирает копейки округления, чтобы сумма месяцев = итогу
        v = (quarter_total - acc) if m == months else per_month.quantize(Decimal("1"))
        me.text = str(int(v))
        acc += Decimal(int(v))
    tot = etree.SubElement(el, "total")
    tot.text = str(int(quarter_total))


def build_200_xml(
    calc: dict,
    *,
    iin_bin: str,
    name: str,
    year: int,
    quarter: int,
    is_ip: bool,
    ugd_code: str | None = None,
    declaration_kind: str = "regular",
) -> bytes:
    """Собирает XML 200.00 из свода calc_200_quarter. Возвращает UTF-8 bytes."""
    root = etree.Element("declaration", form="200.00", version=SCHEMA_VERSION)

    hdr = etree.SubElement(root, "header")
    etree.SubElement(hdr, "iinBin").text = iin_bin
    etree.SubElement(hdr, "name").text = name or ""
    etree.SubElement(hdr, "taxPeriod", quarter=str(quarter), year=str(year))
    etree.SubElement(hdr, "legalForm").text = "ip" if is_ip else "too"
    etree.SubElement(hdr, "declarationKind").text = declaration_kind
    etree.SubElement(hdr, "residency").text = "resident"
    etree.SubElement(hdr, "currency").text = "398"  # KZT
    etree.SubElement(hdr, "employees").text = str(int(calc.get("employees", 0)))
    if ugd_code:
        etree.SubElement(hdr, "ugdCode").text = ugd_code

    # --- Исчисленные суммы по работникам (помесячно + итог квартала) ---
    sect = etree.SubElement(root, "section", name="payroll")
    for key, title in _COMPONENTS:
        _quarter_line(sect, f"payroll.{key}", _dec(calc.get(key)))
        sect[-1].set("title", title)  # человекочитаемая подпись (для сверки, не для ФЛК)

    # --- Итоги ---
    totals = etree.SubElement(root, "section", name="totals")
    etree.SubElement(totals, "line", code="withheld_from_employees").text = \
        str(int(_dec(calc.get("employee_withheld_total"))))
    etree.SubElement(totals, "line", code="paid_by_employer").text = \
        str(int(_dec(calc.get("employer_paid_total"))))
    etree.SubElement(totals, "line", code="total_to_budget").text = \
        str(int(_dec(calc.get("total_to_budget"))))

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True)


def flk_200(calc: dict) -> tuple[list[str], list[str]]:
    """Локальный ФЛК: арифметика свода должна биться. → (ошибки, предупреждения)."""
    errors, warns = [], []
    withheld = _dec(calc.get("ipn")) + _dec(calc.get("opv")) + _dec(calc.get("vosms"))
    employer = (_dec(calc.get("opvr")) + _dec(calc.get("so")) +
                _dec(calc.get("oosms")) + _dec(calc.get("social_tax")))
    if withheld != _dec(calc.get("employee_withheld_total")):
        errors.append("Сумма удержаний с работников не сходится (ИПН+ОПВ+ВОСМС ≠ итог).")
    if employer != _dec(calc.get("employer_paid_total")):
        errors.append("Сумма платежей работодателя не сходится (ОПВР+СО+ООСМС+соцналог ≠ итог).")
    if withheld + employer != _dec(calc.get("total_to_budget")):
        errors.append("Итог в бюджет ≠ удержания + платежи работодателя.")
    if _dec(calc.get("employees")) == 0:
        warns.append("Нет работников в периоде — декларация пустая.")
    return errors, warns
