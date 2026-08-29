"""Тесты генераторов XML 300.00 (НДС) и 100.00 (КПН) + локальный ФЛК."""
from lxml import etree
from app.tax.xml_300 import build_300_xml, flk_300
from app.tax.xml_100 import build_100_xml, flk_100

VAT = {"period": "Q1-2026", "taxable_turnover": "10000000", "output_vat": "1600000",
       "input_vat_creditable": "560000", "vat_payable": "1040000", "vat_carry_forward": "0",
       "rate": "0.16"}
KPN = {"year": 2026, "gross_income": "10000000", "deductions": "3500000", "non_deductible": "0",
       "taxable_income": "6500000", "kpn": "1300000", "kpn_payable": "1300000",
       "kpn_overpaid": "0", "loss_carry_forward": "0"}


def test_300_flk_ok_and_xml():
    assert flk_300(VAT)[0] == []
    root = etree.fromstring(build_300_xml(VAT, iin_bin="111111111111", name="ТОО",
                                          year=2026, quarter=1, is_ip=False))
    assert root.get("form") == "300.00"
    assert root.xpath("//line[@code='vat.payable']/text()")[0] == "1040000"


def test_300_flk_catches_bad_payable():
    bad = {**VAT, "vat_payable": "999"}
    assert any("уплате" in e.lower() for e in flk_300(bad)[0])


def test_300_flk_rejects_payable_and_carry_together():
    bad = {**VAT, "input_vat_creditable": "1600000", "vat_payable": "1040000",
           "vat_carry_forward": "0"}
    assert flk_300(bad)[0]  # payable должен был обнулиться → ошибка


def test_100_flk_ok_and_xml():
    assert flk_100(KPN)[0] == []
    root = etree.fromstring(build_100_xml(KPN, iin_bin="111111111111", name="ТОО",
                                          year=2026, is_ip=False))
    assert root.get("form") == "100.00"
    assert root.xpath("//line[@code='kpn.tax']/text()")[0] == "1300000"


def test_100_flk_catches_wrong_tax():
    bad = {**KPN, "kpn": "1"}
    assert any("кпн" in e.lower() for e in flk_100(bad)[0])
