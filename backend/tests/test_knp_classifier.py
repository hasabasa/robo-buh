"""Тесты классификатора доход/не-доход по КНП."""

from app.ingestion.knp_classifier import classify_by_knp


def test_income_knp_credit():
    c = classify_by_knp("710", "credit")
    assert c.is_income is True and c.classified_by == "knp_rule"


def test_income_service_range():
    assert classify_by_knp("855", "credit").is_income is True   # 851–862 услуги


def test_debit_never_income():
    # даже доходный КНП на расходе — не доход
    assert classify_by_knp("710", "debit").is_income is False


def test_own_transfer_not_income():
    assert classify_by_knp("342", "credit").is_income is False


def test_tax_range_not_income():
    assert classify_by_knp("911", "credit").is_income is False


def test_unknown_knp_goes_to_review():
    c = classify_by_knp("999", "credit")
    assert c.is_income is None and c.classified_by == "unknown"


def test_missing_knp_credit_review():
    # приход без КНП — не угадываем, на сверку
    assert classify_by_knp(None, "credit").is_income is None


def test_ambiguous_cash_deposit_review():
    # 331 (внесение наличных) намеренно не в правилах → на сверку
    assert classify_by_knp("331", "credit").is_income is None
