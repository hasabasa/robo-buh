"""Тест генератора XML 200.00 и локального ФЛК."""
from decimal import Decimal
from lxml import etree

from app.tax.payroll_200 import calc_200_quarter
from app.tax.xml_200 import build_200_xml, flk_200


def _calc():
    return calc_200_quarter([Decimal("400000"), Decimal("350000")])


def test_flk_passes_on_engine_output():
    errors, _ = flk_200(_calc())
    assert errors == []


def test_flk_catches_broken_totals():
    calc = _calc(); calc["total_to_budget"] = "1"   # заведомо неверный итог
    errors, _ = flk_200(calc)
    assert any("бюджет" in e.lower() for e in errors)


def test_xml_structure_and_monthly_sum():
    calc = _calc()
    xml = build_200_xml(calc, iin_bin="111111111111", name="ТОО Тест",
                        year=2026, quarter=3, is_ip=False, ugd_code="620501")
    root = etree.fromstring(xml)
    assert root.get("form") == "200.00"
    assert root.findtext(".//iinBin") == "111111111111"
    assert root.find(".//taxPeriod").get("quarter") == "3"
    # для каждой строки: сумма 3 месяцев == total
    for line in root.findall(".//section[@name='payroll']/line"):
        months = sum(int(m.text) for m in line.findall("m"))
        assert months == int(line.findtext("total")), line.get("code")
    # итог в бюджет присутствует и положителен
    tot = root.xpath("//line[@code='total_to_budget']/text()")
    assert tot and int(tot[0]) > 0
