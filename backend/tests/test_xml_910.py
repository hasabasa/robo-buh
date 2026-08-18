"""Тест генератора XML 910.00: структура строк, арифметика, ФЛК."""

from decimal import Decimal

from lxml import etree

from app.tax.flk import check_910
from app.tax.simplified_910 import calc_910
from app.tax.xml_910 import build_910_xml


def _calc_ip():
    return calc_910(turnover=Decimal("1020000"), period="H1-2026", taxpayer_kind="ip",
                    birth_date=__import__("datetime").date(2000, 12, 1))


def test_xml_wellformed_and_lines():
    calc = _calc_ip()
    xml = build_910_xml(calc, iin_bin="001201000056", name="ИП Тест", year=2026, half=1,
                        is_ip=True, ugd_code="6001")
    root = etree.fromstring(xml)

    lines = {el.get("code"): el for el in root.iter("line")}
    # налоговый раздел
    assert lines["910.00.001"].text == "1020000"                 # доход
    assert lines["910.00.003"].text == "1020000"                 # = 001 - 002
    assert lines["910.00.004"].text == "40800"                   # ИПН 4%
    # соцраздел присутствует и помесячный
    assert "910.00.008" in lines                                  # ОПВ
    opv = lines["910.00.008"]
    months = opv.findall("m")
    assert len(months) == 6 and months[0].text == "8500"          # ОПВ 8500/мес
    assert opv.find("total").text == "51000"                      # 8500 × 6


def test_flk_passes_valid():
    calc = _calc_ip()
    r = check_910(calc, iin_bin="001201000056", ugd_code="6001")
    assert r.ok and not r.errors


def test_flk_catches_bad_iin():
    calc = _calc_ip()
    r = check_910(calc, iin_bin="123", ugd_code="6001")
    assert not r.ok and any("ИИН" in e for e in r.errors)


def test_too_has_no_social_section():
    calc = calc_910(turnover=Decimal("1000000"), period="H1-2026", taxpayer_kind="too")
    xml = build_910_xml(calc, iin_bin="260440029440", name="ТОО", year=2026, half=1, is_ip=False)
    root = etree.fromstring(xml)
    sections = [s.get("name") for s in root.iter("section")]
    assert "social" not in sections                              # у ТОО соцраздел за себя не заполняется
