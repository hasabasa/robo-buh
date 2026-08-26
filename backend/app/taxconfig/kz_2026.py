"""Налоговые константы РК на 2026 год. ЕДИНСТВЕННОЕ место, где живут числа.

Сверено веб-поиском 18.08.2026 (НК РК № 214-VIII от 18.07.2025, Закон о бюджете
№ 239-VIII от 08.12.2025). Поля, помеченные VERIFY, требуют финальной сверки с
первоисточником (текст НК / официальные правила заполнения ФНО) до продакшна —
см. «Открытые вопросы» в плане продукта.
"""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class TaxYearKZ:
    year: int

    # --- Базовые показатели (Закон № 239-VIII от 08.12.2025) ---
    mrp: Decimal = Decimal("4325")        # МРП
    mzp: Decimal = Decimal("85000")       # МЗП

    # --- СНР «упрощённая декларация» ---
    ipn_rate_default: Decimal = Decimal("0.04")   # ИПН 4% с оборота
    ipn_rate_min: Decimal = Decimal("0.02")       # маслихат может −50%
    ipn_rate_max: Decimal = Decimal("0.06")       # маслихат может +50%
    social_tax_abolished: bool = True             # соцналог на упрощёнке отменён с 2026
    snr_income_limit_mrp: int = 600_000           # лимит СНР: 600 000 МРП/год
    # НДС на упрощёнке НЕ применяется (освобождение, ст. 99 НК — VERIFY по тексту НК)
    vat_applicable_on_snr: bool = False

    # --- Соцплатежи ИП «за себя» (ежемесячно, база по умолчанию 1 МЗП) ---
    opv_rate: Decimal = Decimal("0.10")           # ОПВ 10%, база 1–50 МЗП
    opv_base_max_mzp: int = 50
    opvr_rate: Decimal = Decimal("0.035")         # ОПВР 3,5% — только р. после 01.01.1975
    opvr_birthdate_cutoff: str = "1975-01-01"
    so_rate: Decimal = Decimal("0.05")            # СО 5%, база 1–7 МЗП
    so_base_max_mzp: int = 7
    vosms_fixed: Decimal = Decimal("5950")        # ВОСМС: 1,4 × МЗП × 5% = 5 950 ₸/мес,
                                                  # платится даже при нулевом доходе

    # --- Сроки ---
    # 910.00: H1 — сдача до 15.08, уплата до 25.08; H2 — до 15.02, до 25.02 (след. год)
    # 200.00: ежеквартально, сдача до 15 числа 2-го месяца после квартала (VERIFY)
    # соцплатежи: ежемесячно до 25 числа следующего месяца

    # --- Пеня ---
    penalty_base_rate_multiplier: Decimal = Decimal("1.25")  # 1,25 × базовая ставка НБРК
    # базовая ставка НБРК — живёт в БД/конфиге, меняется решениями НБРК (не константа года)

    # --- Зарплатный блок для 200.00 (по работникам, ОУР) — CONFIRMED 2026 ---
    # Сверено 26.08.2026 по mybuh (Налоги с зарплаты 2026) + pro1c + uchet, НК 214-VIII.
    # Финальная привязка строк — по официальным Правилам заполнения 200.00 v2026.
    # ИПН у источника (удерживается у работника), прогрессия:
    ipn_source_rate_low: Decimal = Decimal("0.10")     # 10% базовая
    ipn_source_rate_high: Decimal = Decimal("0.15")    # 15% сверх порога
    ipn_source_threshold_mrp: int = 8500               # порог 15% ≈ 8500 МРП/год (≈36,7 млн ₸)
    ipn_standard_deduction_mrp: int = 30               # базовый вычет 30 МРП/мес (14 МРП ОТМЕНЁН)
    ipn_deduction_year_cap_mrp: int = 360              # лимит вычета 360 МРП/год
    # База ИПН = оклад − ОПВ − ВОСМС − вычет(30 МРП)
    # Удержания С РАБОТНИКА:
    opv_employee_rate: Decimal = Decimal("0.10")       # ОПВ 10%, база до 50 МЗП
    vosms_employee_rate: Decimal = Decimal("0.02")     # ВОСМС 2%, база до 20 МЗП
    # Платежи РАБОТОДАТЕЛЯ:
    opvr_employer_rate: Decimal = Decimal("0.035")     # ОПВР 3,5%, база до 50 МЗП
    so_employer_rate: Decimal = Decimal("0.05")        # СО 5%, база 1–7 МЗП
    oosms_employer_rate: Decimal = Decimal("0.03")     # ООСМС 3%, база до 40 МЗП
    social_tax_employer_rate: Decimal = Decimal("0.06")  # соцналог 6% (ТОО на ОУР)
    # ⚠️ 2026: взаимозачёт соцналога и соцотчислений ОТМЕНЁН.
    opv_base_max_mzp_emp: int = 50
    so_base_max_mzp_emp: int = 7
    vosms_base_max_mzp_emp: int = 20
    oosms_base_max_mzp_emp: int = 40

    # --- ОУР: КПН (100.00) и НДС (300.00) — CONFIRMED 2026 ---
    kpn_rate: Decimal = Decimal("0.20")                # КПН 20% с налогооблагаемого дохода
    # КПН: годовая 100.00 (срок ~31 марта след. года); авансовые — расчёт до декларации
    # ОТМЕНЁН, за 1 кв. считает УГД (1/12 прошлого периода), уплата до 25 числа.
    # ⚠️ Вычет по КПН: расходы на покупку у лиц НА УПРОЩЁНКЕ в вычеты НЕ включаются (НК-2026).
    vat_rate: Decimal = Decimal("0.16")                # НДС 16% (было 12%)
    vat_rate_reduced: Decimal = Decimal("0.05")        # льготная 5% (отд. категории, →10%)
    vat_registration_threshold_mrp: int = 10_000       # порог обязательной постановки на НДС
    # НДС: квартальная 300.00, срок до 15 числа 2-го мес. после квартала.
    # НДС к уплате = исходящий (с оборота) − входящий (к зачёту по полученным ЭСФ).


KZ_2026 = TaxYearKZ(year=2026)


def social_min_monthly(has_opvr: bool) -> Decimal:
    """Минимальные соцплатежи ИП за себя в месяц (база 1 МЗП).

    ОПВ 8 500 + ОПВР 2 975 (если р. после 01.01.1975) + СО 4 250 + ВОСМС 5 950
    = 21 675 ₸/мес (с ОПВР) или 18 700 ₸/мес (без).
    """
    c = KZ_2026
    total = c.mzp * c.opv_rate + c.mzp * c.so_rate + c.vosms_fixed
    if has_opvr:
        total += c.mzp * c.opvr_rate
    return total


def snr_income_limit_kzt() -> Decimal:
    """Лимит СНР в тенге: 600 000 МРП ≈ 2 595 000 000 ₸ (2026)."""
    return KZ_2026.mrp * KZ_2026.snr_income_limit_mrp
