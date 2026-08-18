"""Юнит-тест извлечения казахстанских финансовых сущностей (офлайн, детерминированный)."""
from app.ingestion.kz_entities import extract, parse_amount


def test_extract_from_purpose():
    t = ("Перевод от ТОО Ромашка БИН 180540021234 на ИИК KZ75125KZT1001300335, "
         "ИИН плательщика 950115300123, КНП 710, КБе 17, сумма 1 234 567,89 от 15.03.2026")
    e = extract(t)
    assert e["bin"] == ["180540021234"]
    assert e["iin"] == ["950115300123"]
    assert e["iik"] == ["KZ75125KZT1001300335"]
    assert e["knp"] == ["710"]
    assert e["kbe"] == ["17"]
    assert "15.03.2026" in e["date"]


def test_parse_amount():
    assert parse_amount("1 234 567,89") == 1234567.89
    assert parse_amount("500") == 500.0
    assert parse_amount("нечисло") is None
