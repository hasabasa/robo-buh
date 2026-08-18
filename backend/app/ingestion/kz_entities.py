"""Извлечение казахстанских финансовых сущностей из текста выписки/назначения платежа.

Регэкспы ИИН/БИН/ИИК/БИК/даты портированы из cube-translator (core/entity_filter.py,
авторский движок владельца) и расширены финансовыми полями (КНП, КБе, сумма).

Используется двумя путями:
  1. текстовый слой выписок (MT940 поле :86:, 1CClientBankExchange, PDF с текстом);
  2. фолбэк-разбор ответа OCR, если vision вернул сырой текст, а не структуру.
"""

from __future__ import annotations

import re

# ИИН и БИН оба 12 цифр — различаем по контексту (13-я цифра БИН = 4/5/6), но на уровне
# регэкспа это одно и то же: 12 цифр подряд. Тип уточняем по метке рядом.
RE_IIN_BIN = re.compile(r"\b\d{12}\b")
# ИИК (казахстанский IBAN): KZ + 2 контрольные + 16 буквенно-цифровых
RE_IIK = re.compile(r"\bKZ\d{2}[A-Z0-9]{16}\b")
# БИК банка РК
RE_BIK = re.compile(r"\b[A-Z]{4}KZ[A-Z0-9]{2}\b")
RE_DATE = re.compile(r"\b(\d{2})[.\-/](\d{2})[.\-/](\d{4})\b")
# КНП — код назначения платежа, 3 цифры; ловим у метки, чтобы не путать с суммами
RE_KNP = re.compile(r"\bКНП[\s:]*?(\d{3})\b", re.IGNORECASE)
# КБе — код бенефициара, 2 цифры у метки
RE_KBE = re.compile(r"\bКБе[\s:]*?(\d{2})\b", re.IGNORECASE)
# Сумма в тенге: 1 234 567,89 / 1234567.89 (разделители — пробел/неразрывный пробел)
RE_AMOUNT = re.compile(r"\b\d{1,3}(?:[  ]\d{3})*(?:[.,]\d{2})?\b")


def _digit13(bin_iin: str) -> int | None:
    return int(bin_iin[4]) if len(bin_iin) == 12 else None


def classify_12(code: str) -> str:
    """Отличает БИН от ИИН по 5-й цифре (у БИН это 4/5/6 — тип юрлица). Иначе — ИИН."""
    d = _digit13(code)
    return "bin" if d in (4, 5, 6) else "iin"


def extract(text: str) -> dict[str, list[str]]:
    """Возвращает все найденные сущности по типам (без дедупа порядка — как в тексте)."""
    codes = RE_IIN_BIN.findall(text)
    return {
        "iin": [c for c in codes if classify_12(c) == "iin"],
        "bin": [c for c in codes if classify_12(c) == "bin"],
        "iik": RE_IIK.findall(text),
        "bik": RE_BIK.findall(text),
        "date": [f"{d}.{m}.{y}" for d, m, y in RE_DATE.findall(text)],
        "knp": RE_KNP.findall(text),
        "kbe": RE_KBE.findall(text),
    }


def parse_amount(raw: str) -> float | None:
    """'1 234 567,89' → 1234567.89. Возвращает None, если не число."""
    s = raw.replace(" ", "").replace(" ", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None
